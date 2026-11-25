# ServerKeyZ

A small Linux command-line app that turns one physical keyboard connected to your server into a Bluetooth Classic HID keyboard. It forwards real key presses to a compatible paired phone, computer, tablet or TV. No companion app is required on the receiving device.

**Version 0.2 — hardware validation pending.** Intended for Debian/Ubuntu with BlueZ 5 and a Bluetooth Classic (BR/EDR) capable adapter. Not a BLE-only keyboard, Windows or macOS server app. No Samsung-specific control protocol is implemented.

## Behavior

- Local keyboard remains usable while waiting for a host. Bluetooth mode is initially requested, but activates only after a paired, trusted host opens both encrypted HID channels and all physical keys are released.
- **Super (Windows) + Ctrl + Alt + backslash (`\`)** toggles between local and Bluetooth mode. Hold the three modifiers, press the physical backslash key, then release all keys. Left/right modifiers work. Holding the chord or repeating backslash cannot cause multiple toggles until all keys are released.
- Bluetooth to local: remote key reports are cleared immediately and no more typing is forwarded. After releasing the keys, the physical keyboard is ungrabbed and works normally on the server. The Bluetooth connection and app remain active.
- Local to Bluetooth: the same shortcut requests remote mode; the keyboard is grabbed only after all keys are released and a trusted host is connected. If none is connected yet, it waits with local input intact. Because local mode does not grab or replace your physical keyboard, the shortcut also reaches the server's desktop/console in local mode. Avoid assigning the same chord to another local action.
- The backslash that triggers the shortcut is never forwarded; modifiers pressed before the final key may already have reached the remote host. Remote mode forwards standard keyboard and media reports only while enabled.
- A host disconnect or failed HID write releases the physical keyboard and switches to local mode. The app keeps listening; press the shortcut to request Bluetooth mode again. Ctrl+C in the launching SSH terminal, SIGTERM, or a fatal input error stops the app and releases the physical keyboard. No service auto-starts or auto-restarts it.
- Standard keys, navigation, function keys, keypad, modifiers, volume/mute and basic playback media keys are supported. Actual media key behavior and layouts are determined by the receiving host. Consumer report carries one media usage at a time. Separate media-key event devices aren't forwarded.
- Only a paired and explicitly trusted BlueZ device may receive input. Use `--peer` to restrict it to one particular device (recommended). No keystrokes are logged, saved or accepted from the network. Keep your server unlocked only when you intend to forward input.

## 1. Install

Upload the contents of this directory to your own GitHub repository. On the server:

```sh
git clone https://github.com/YOUR-USERNAME/ServerKeyZ.git
cd ServerKeyZ
sudo ./install.sh
```

The installer installs distribution packages and copies the program under `/usr/local/lib/ServerKeyZ/` and a launcher to `/usr/local/bin/serverkeyz`. It does not change Bluetooth configuration or restart services. On other Linux distributions, install equivalent packages (`bluez`, Python 3, `evdev`, `dbus-python`, PyGObject/GLib) and run `sudo python3 serverkeyz.py` from the source directory.

Check your server:

```sh
cat /etc/os-release
bluetoothctl list
sudo btmgmt info
sudo serverkeyz --list
```

Confirm that the controller supports BR/EDR. For a reliable keyboard path, use:

```sh
ls -l /dev/input/by-id/*-event-kbd
```

Choose the entry that matches the intended keyboard; otherwise use an event device from `--list`. Event numbers can change after reboot. The app does not grab all input devices. Keep an SSH session open for recovery.

### Upgrade from 0.1

Replace the old repository contents with the 0.2 release, then on the server stop the old app (Ctrl+C in its SSH terminal), and run:

```sh
cd ServerKeyZ
git pull
sudo ./install.sh
```

Relaunch using the same `--device` and optional `--peer` arguments. Existing BlueZ pairing and configuration are not changed by the installer.

## 2. Bluetooth setup (Classic HID conflict)

Linux BlueZ commonly claims the Classic HID ports (PSMs 17 and 19) for its own host role. ServerKeyZ needs these ports for the opposite role. If launch fails to bind either port or reports a duplicate HID profile, disable only the BlueZ `input` plugin. **This is a system-wide change: it can prevent ordinary Bluetooth keyboards/mice from working on the server; restarting Bluetooth disconnects active Bluetooth devices. Use a wired keyboard and SSH.** If you depend on server Bluetooth peripherals, do not make this change without a recovery plan.

Inspect your service first:

```sh
systemctl cat bluetooth.service
```

Find the effective `ExecStart` path and existing arguments. For example, if it is `/usr/libexec/bluetooth/bluetoothd`, create a dedicated drop-in with that path:

```sh
sudo mkdir -p /etc/systemd/system/bluetooth.service.d
sudoedit /etc/systemd/system/bluetooth.service.d/90-serverkeyz.conf
```

Put the following in that file, using the actual executable path and preserving any existing required daemon options. If your daemon already has a `--noplugin` list, add `input` to that list instead of replacing it.

```ini
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd --noplugin=input
```

Then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart bluetooth.service
bluetoothctl power on
```

To undo only this change:

```sh
sudo rm /etc/systemd/system/bluetooth.service.d/90-serverkeyz.conf
sudo systemctl daemon-reload
sudo systemctl restart bluetooth.service
```

On a dedicated adapter, `btmgmt --index hci0 class 5 64` may help a host identify the peripheral as a keyboard. This changes the adapter's advertised device class; it is optional, may be overridden by BlueZ, and should not be used blindly on a shared adapter. Check the actual controller and use `--adapter hci1` if needed. The input plugin change is still global.

## 3. Start and pair

In an SSH terminal (replace the example keyboard path with yours):

```sh
sudo serverkeyz --device /dev/input/event3
```

The app registers the HID service, but does not make the adapter discoverable itself. In a second SSH terminal, use the interactive BlueZ shell:

```text
bluetoothctl
power on
system-alias ServerKeyZ
agent KeyboardDisplay
default-agent
pairable on
discoverable on
```

If using a non-default adapter, use `list` then `select <controller-MAC>` before those commands. Keep the shell open for pairing prompts. In the receiving device's Bluetooth settings, select **ServerKeyZ** and follow the pairing/passkey prompts in both devices. If a passkey is displayed by the receiving device, enter it in the agent prompt as requested, not by sending blind keystrokes.

In the BlueZ shell, run `devices`, then `info <HOST-MAC>` and `trust <HOST-MAC>` for the device you just approved. `Paired: yes` and `Trusted: yes` must both be present. Initial HID connection can be rejected before trust is set: reconnect from the receiving device after trust is set. Do not trust unknown devices. Turn off discovery and pairing after setup:

```text
discoverable off
pairable off
quit
```

For normal use, restart the app with the known host address:

```sh
sudo serverkeyz --device /dev/input/event3 --peer AA:BB:CC:DD:EE:FF
```

Replace both examples. Connect from the host Bluetooth settings. `REMOTE MODE` in the server terminal confirms both HID channels opened and keyboard capture succeeded. Release all physical keys during activation. Press Super+Ctrl+Alt+backslash on the selected physical keyboard to toggle to local mode. Release the keys, then press the same shortcut again to return to Bluetooth mode. The app stays running in both modes. To quit completely, press Ctrl+C in the launching SSH terminal.

## Troubleshooting / limitations

- `Address already in use` or profile registration conflict: see step 2. Don't kill unrelated Bluetooth processes.
- App is waiting: confirm the host supports Bluetooth Classic keyboards, pairing/trust are complete, the selected adapter is correct, and initiate connection from the host. Some hosts only support BLE HID or require different HID negotiation/reconnection behavior. This is not a complete HID conformance implementation (report protocol only; no boot protocol, keyboard LED synchronization, or host idle-rate support).
- A target may not appear as a keyboard if the Bluetooth device class is not appropriate. See the optional class note in step 2.
- A Samsung soundbar usually is not a general-purpose keyboard host; this app is for targets which explicitly support Bluetooth HID keyboards, e.g. some Samsung TVs. Even a TV may not route keyboard media keys to its soundbar. Compatibility is model-dependent.
- Recovery from SSH: `sudo pkill -TERM -f '/usr/local/lib/ServerKeyZ/serverkeyz.py'`. Linux releases an evdev grab when the process/file descriptor closes. If all else fails, from a different keyboard or SSH terminate the process. No service auto-restarts it.
- To uninstall the app, remove `/usr/local/bin/serverkeyz` and `/usr/local/lib/ServerKeyZ/` (only those paths), and undo the optional Bluetooth drop-in as above. The alias and pairing/trust state are separate BlueZ settings; change/remove them manually if desired.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

These test report encoding, release packets, SDP XML, both shortcut directions, held-key suppression and disconnect disarming without Bluetooth hardware. Real adapter pairing, host compatibility and latency still need on-device testing. First test with a harmless text editor on a compatible host and SSH available, including both shortcut directions, held keys, and disconnect/reconnect recovery.

## Technical references

- [BlueZ ProfileManager API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.ProfileManager.rst)
- [BlueZ profile implementation](https://kernel.googlesource.com/pub/scm/bluetooth/bluez.git/+/refs/tags/5.85/src/profile.c)
- [Classic HID keyboard emulator architecture](https://github.com/SySS-Research/bluetooth-keyboard-emulator)
