# ServerKeyZ

Turn a Linux server’s physical keyboard into a Bluetooth Classic HID keyboard. Switch between local and wireless input using **Super + Ctrl + Alt + `\`**. No companion app required on a compatible receiving device.

**v0.4 — automatic Bluetooth setup.** Designed for Debian 13 / Ubuntu with BlueZ 5, systemd and a BR/EDR-capable adapter. Hardware pairing is not yet validated; this is an experimental release.

## Installation

```bash
git clone https://github.com/masonhain14-a11y/ServerKeyZ.git
cd ServerKeyZ
sudo bash install.sh
sudo serverkeyz
```

Already installed? Stop the running app with Ctrl+C in its launch terminal, then:

```bash
cd ~/ServerKeyZ
git pull
sudo bash install.sh
sudo serverkeyz
```

The installer installs distribution dependencies and copies the app to `/usr/local/lib/ServerKeyZ` and the launcher to `/usr/local/bin/serverkeyz`. Run it once per update. Keep the existing repository MIT LICENSE when uploading this update.

## Connect a device

1. Run `sudo serverkeyz` in an interactive SSH terminal (or on the server with a wired keyboard).
2. Wait for the message `Bluetooth keyboard ServerKeyZ is discoverable`.
3. Open Bluetooth settings on the device you want to control and select **ServerKeyZ**.
4. Approve the named device in the same server terminal by entering `y` when prompted. Follow any PIN/passkey instructions in the terminal and on the receiving device. If pairing succeeds but the first HID connection fails, select Connect again on the receiving device.
5. `REMOTE MODE` confirms both HID channels connected and keyboard forwarding is active. Test in a harmless text editor.

No separate `bluetoothctl`, `btmgmt`, agent, trust or discovery commands are normally needed. A host must be paired and explicitly approved; only the approved host can receive input during that launch. Discovery and pairing close after a successful HID connection or 180 seconds, whichever comes first. Restart the app to open a new pairing window. Use `--pair-timeout 300` for a longer window. A previously paired device may still require approval when restarting the app. Pairing requires an interactive terminal, not an unattended daemon.

## Controls

| Command or shortcut | Function |
| --- | --- |
| `sudo serverkeyz` | Auto-select keyboard, configure Bluetooth and start |
| Super + Ctrl + Alt + backslash | Toggle local / wireless input on physical server keyboard |
| Ctrl+C in SSH | Stop app and release keyboard |
| `sudo serverkeyz --list` | List eligible keyboards |
| `sudo serverkeyz --device /dev/input/event0` | Override keyboard selection |
| `sudo serverkeyz --adapter hci1` | Use another adapter |
| `sudo serverkeyz --peer AA:BB:CC:DD:EE:FF` | Restrict pairing and input to one host |
| `sudo serverkeyz --restore-bluetooth` | Clear stale app-created temporary service override (stop app first) |

The app prioritizes a unique built-in PS/2 keyboard or a single eligible keyboard. If ambiguous, specify a device. Keyboard event numbers may change after reboot. Local input is available while waiting for a host. The hotkey requires releasing all keys before the mode switches; modifier key presses before the final backslash may have already reached the receiver. The chord also reaches the local OS in local mode. A host disconnect returns input to local mode and disarms forwarding; reconnect the host and toggle to re-enable it. The app remains running. No key logging.

## Automatic Bluetooth configuration

On launch ServerKeyZ starts BlueZ, powers the selected adapter, registers the Classic HID SDP service and pairing agent, sets the alias and keyboard device class, and opens discovery. It verifies the kernel device class, BlueZ HID UUID, pairable and discoverable flags before reporting ready. Normal exit restores the previous adapter settings where possible and unregisters the agent and profile. Bluetooth bonds/trust established with your approval remain in BlueZ.

If the HID ports are occupied, the app attempts to temporarily disable the BlueZ `input` plugin using a runtime systemd drop-in. It does so only for a standard bluetoothd service without custom flags. It then restarts BlueZ and retries. **This may disconnect existing Bluetooth devices and temporarily disable normal Bluetooth keyboard/mouse input to the server.** Use SSH or a wired keyboard. On exit, the runtime drop-in is removed and BlueZ is restarted. Earlier manually installed overrides are preserved, not replaced or removed. A customized service or an unrelated process occupying the ports may require investigation. `--restore-bluetooth` removes only the app’s own runtime override if left after an abnormal stop. It does not remove any older persistent override. A power loss or SIGKILL may prevent normal settings cleanup.

## Troubleshooting

- Not discoverable: copy the entire output of `sudo serverkeyz`, including verification errors. The checks confirm local adapter state, not actual radio visibility on the Mac. Try refreshing Bluetooth settings on the receiving device once after startup. Restart the app if discovery has timed out.
- A previously paired device that will not reconnect: forget ServerKeyZ on the receiving device and restart ServerKeyZ. If still failing, the old bond on the server may also need removal; do not remove unrelated devices.
- If the app reports an occupied port and customized service, inspect `systemctl cat bluetooth.service`. The app refuses to overwrite customized daemon options automatically. For this server the previously created `/etc/systemd/system/bluetooth.service.d/serverkeyz.conf` already disables the input plugin; leave it in place while testing.
- Bluetooth adapter supports Classic HID transport, but macOS/other hosts may still reject an incomplete HID implementation. Report protocol is implemented, not boot protocol; keyboard LEDs and idle rate are not synchronized. BLE-only receivers are not supported.
- A Samsung soundbar is generally not a keyboard host. Some TVs may accept keyboard volume/media keys, but routing to a soundbar is model-dependent.
- Emergency recovery: stop the app from SSH using Ctrl+C or `sudo pkill -TERM -f '/usr/local/lib/ServerKeyZ/serverkeyz.py'`. Linux releases the physical keyboard when the device file closes. For stale temporary service overrides, use `sudo serverkeyz --restore-bluetooth`.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

Unit tests cover keyboard selection, HID reports, shortcut behavior, disconnect safety, pairing approval policy, keyboard classification and reversible service override logic. These do not exercise physical Bluetooth radios, actual macOS pairing, live BlueZ D-Bus calls or live systemd service restarts.

## References

- [BlueZ Adapter API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst)
- [BlueZ Agent API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Agent.rst)
- [BlueZ ProfileManager API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.ProfileManager.rst)
- [BlueZ management interface](https://github.com/bluez/bluez/wiki/MGMT)
