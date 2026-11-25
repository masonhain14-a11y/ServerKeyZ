#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(id -u)" -ne 0 ]; then echo 'Run: sudo ./install.sh' >&2; exit 1; fi
if ! command -v apt-get >/dev/null; then echo 'This installer targets Debian/Ubuntu; see README for other Linux systems.' >&2; exit 1; fi
apt-get update
apt-get install -y bluez python3 python3-evdev python3-dbus python3-gi
install -d -m 0755 /usr/local/lib/ServerKeyZ /usr/local/bin
install -m 0755 serverkeyz.py /usr/local/lib/ServerKeyZ/
install -m 0644 hid.py /usr/local/lib/ServerKeyZ/
install -m 0755 serverkeyz /usr/local/bin/serverkeyz
printf '\nInstalled. Next: sudo serverkeyz\nRead README.md for required Bluetooth setup and pairing.\n'
