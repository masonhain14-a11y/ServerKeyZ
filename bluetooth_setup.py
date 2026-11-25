"""ServerKeyZ Bluetooth setup and explicit pairing approval (Linux/BlueZ)."""
import errno
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time

ADAPTER = 'org.bluez.Adapter1'
DEVICE = 'org.bluez.Device1'
AGENT = 'org.bluez.Agent1'
AGENT_PATH = '/org/serverkeyz/agent'
HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
DROPIN = Path('/run/systemd/system/bluetooth.service.d/99-serverkeyz-runtime.conf')


def command(*args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(f'{" ".join(args)} failed: {(p.stderr or p.stdout).strip()}')
    return p.stdout


def keyboard_class(value):
    return int(value) & 0x1ffc == 0x0540


def set_class(index, value):
    major, minor = (value >> 8) & 0x1f, value & 0xfc
    command('btmgmt', '--index', str(index), 'class', str(major), str(minor))


def read_class(index):
    info = command('btmgmt', '--index', str(index), 'info')
    match = re.search(r'\bclass\s+0x([0-9a-f]+)', info, re.I)
    if not match:
        raise RuntimeError('Unable to read Bluetooth device class: '+info.strip())
    return int(match[1], 16)


def restore_runtime():
    if DROPIN.exists():
        DROPIN.unlink()
        command('systemctl', 'daemon-reload')
        command('systemctl', 'restart', 'bluetooth.service')


def resolve_conflict(stack):
    # Only override the stock Debian/Ubuntu service. Never erase custom flags.
    effective = command('systemctl', 'show', '-p', 'ExecStart', '--value', 'bluetooth.service')
    match = re.search(r'path=(/[^ ;]+/bluetoothd) ; argv\[\]=([^;]+) ;', effective)
    if not match or match[2].strip() != match[1]:
        raise RuntimeError('HID ports busy and Bluetooth uses a customized ExecStart. Cannot safely override it; see README.')
    if DROPIN.exists():
        raise RuntimeError(f'Stale ServerKeyZ override {DROPIN}; stop other instances or use --restore-bluetooth.')
    print('HID ports occupied. Temporarily disabling the BlueZ input plugin; Bluetooth devices may disconnect.', flush=True)
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    with DROPIN.open('x') as f:
        f.write('[Service]\nExecStart=\nExecStart='+match[1]+' --noplugin=input\n')
    stack.callback(restore_runtime)
    command('systemctl', 'daemon-reload')
    command('systemctl', 'restart', 'bluetooth.service')


def prompt(message, timeout=25):
    if not sys.stdin.isatty():
        return ''
    print(message, end='', flush=True)
    if not select.select([sys.stdin], [], [], timeout)[0]:
        print('\nApproval timed out.', flush=True)
        return ''
    return sys.stdin.readline().strip()


class PairingPolicy:
    """Only one explicitly approved host per launch; no wildcard auto-trust."""
    def __init__(self, adapter_path, peer=None):
        self.adapter_path = adapter_path
        self.peer = peer
        self.approved = None
        self.pairing_open = True

    def allowed(self, path, address):
        return (str(path).startswith(self.adapter_path+'/') and
                (self.peer is None or self.peer == address) and
                (self.approved is None or self.approved == address))

    def approve(self, path, address, label, ask=prompt):
        if not self.allowed(path, address):
            return False
        if self.approved == address:
            return True
        # --peer explicitly selects a host, but fresh pairing still needs the
        # interactive confirmation/passkey supplied by the agent.
        if not self.pairing_open:
            return False
        if ask(f'Allow {label} ({address}) to use ServerKeyZ? [y/N] ').lower() != 'y':
            return False
        self.approved = address
        return True

    def cancel(self):
        if self.pairing_open:
            self.approved = None


def make_agent(dbus, bus, policy, device_info):
    import dbus.service
    class Agent(dbus.service.Object):
        def reject(self):
            raise dbus.exceptions.DBusException('Pairing not approved', name='org.bluez.Error.Rejected')

        def approve(self, path):
            info = device_info(path)
            address = str(info.get('Address', '')).upper()
            label = str(info.get('Alias', 'Bluetooth host'))
            if not address or not policy.approve(path, address, label):
                self.reject()
            return address

        @dbus.service.method(AGENT, in_signature='', out_signature='')
        def Release(self):
            pass

        @dbus.service.method(AGENT, in_signature='o', out_signature='s')
        def RequestPinCode(self, device):
            self.approve(device)
            pin = prompt('Enter the PIN shown by the receiving device: ')
            if not pin or len(pin) > 16:
                policy.cancel(); self.reject()
            return pin

        @dbus.service.method(AGENT, in_signature='os', out_signature='')
        def DisplayPinCode(self, device, pincode):
            self.approve(device)
            print(f'Pairing PIN: {pincode}. Enter it on the receiving device.', flush=True)

        @dbus.service.method(AGENT, in_signature='o', out_signature='u')
        def RequestPasskey(self, device):
            self.approve(device)
            pin = prompt('Enter the six-digit code shown by the receiving device: ')
            if not re.fullmatch(r'[0-9]{6}', pin):
                policy.cancel(); self.reject()
            return dbus.UInt32(int(pin))

        @dbus.service.method(AGENT, in_signature='ouq', out_signature='')
        def DisplayPasskey(self, device, passkey, entered):
            self.approve(device)
            if int(entered) == 0:
                print(f'Pairing code: {int(passkey):06d}. Enter it on the receiving device.', flush=True)

        @dbus.service.method(AGENT, in_signature='ou', out_signature='')
        def RequestConfirmation(self, device, passkey):
            self.approve(device)
            if prompt(f'Does the receiving device show {int(passkey):06d}? [y/N] ').lower() != 'y':
                policy.cancel(); self.reject()

        @dbus.service.method(AGENT, in_signature='o', out_signature='')
        def RequestAuthorization(self, device):
            self.approve(device)

        @dbus.service.method(AGENT, in_signature='os', out_signature='')
        def AuthorizeService(self, device, uuid):
            if str(uuid).lower() != HID_UUID:
                self.reject()
            self.approve(device)

        @dbus.service.method(AGENT, in_signature='', out_signature='')
        def Cancel(self):
            policy.cancel()
            print('Bluetooth pairing canceled.', flush=True)
    return Agent(bus, AGENT_PATH)


def restore_adapter(props, previous, dbus, index, original_class):
    # Keep recovery best-effort so an adapter removal never blocks cleanup.
    for name, value in [('Discoverable', dbus.Boolean(False)), ('Pairable', dbus.Boolean(False)),
                        ('Alias', previous['Alias']), ('DiscoverableTimeout', previous['DiscoverableTimeout']),
                        ('PairableTimeout', previous['PairableTimeout'])]:
        try: props.Set(ADAPTER, name, value)
        except dbus.DBusException as e: print(f'Warning: restoring {name}: {e}', file=sys.stderr)
    try: set_class(index, original_class)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e: print(f'Warning: restoring class: {e}', file=sys.stderr)
    for name in ('Pairable', 'Discoverable', 'Powered'):
        try: props.Set(ADAPTER, name, previous[name])
        except dbus.DBusException as e: print(f'Warning: restoring {name}: {e}', file=sys.stderr)
