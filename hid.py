"""Pure HID encoding and hotkey detection (Linux evdev key numbers)."""
# HID keyboard usages are not the same as Linux input codes.
KEYS = dict(zip([30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44], range(4,30)))
KEYS.update(zip(range(2,12), range(30,40)))
KEYS.update({28:40,1:41,14:42,15:43,57:44,12:45,13:46,26:47,27:48,43:49,86:100,39:51,40:52,41:53,51:54,52:55,53:56,58:57,87:68,88:69,99:70,70:71,119:72,110:73,102:74,104:75,111:76,107:77,109:78,106:79,105:80,108:81,103:82,69:83,98:84,55:85,74:86,78:87,96:88,79:89,80:90,81:91,75:92,76:93,77:94,71:95,72:96,73:97,82:98,83:99,127:101})
KEYS.update(zip(range(59,69),range(58,68)))
KEYS.update(zip(range(183,195),range(104,116)))
MODS = {29:1,42:2,56:4,125:8,97:16,54:32,100:64,126:128}
MEDIA = {113:0xe2,114:0xea,115:0xe9,163:0xb5,165:0xb6,164:0xcd,166:0xb7,207:0xb0,201:0xb1}
# Standard 8-byte keyboard report (ID 1); one 16-bit consumer usage (ID 2).
REPORT_MAP = bytes.fromhex('05 01 09 06 A1 01 85 01 05 07 19 E0 29 E7 15 00 25 01 75 01 95 08 81 02 95 01 75 08 81 01 95 05 75 01 05 08 19 01 29 05 91 02 95 01 75 03 91 01 95 06 75 08 15 00 26 FF 00 05 07 19 00 2A FF 00 81 00 C0 05 0C 09 01 A1 01 85 02 15 00 26 FF 03 19 00 2A FF 03 75 10 95 01 81 00 C0')

def escape_pressed(keys, code):
    return code == 43 and bool(keys & {29,97}) and bool(keys & {56,100}) and bool(keys & {125,126})

def reports(keys):
    mod = sum(bit for code, bit in MODS.items() if code in keys)
    ordinary = sorted({KEYS[k] for k in keys if k in KEYS})
    ordinary = [1]*6 if len(ordinary)>6 else ordinary+[0]*(6-len(ordinary))
    media = next((MEDIA[k] for k in sorted(keys) if k in MEDIA),0)
    return bytes([mod,0,*ordinary]), media.to_bytes(2,'little')

class State:
    """Track physical keys and a persistent local/remote preference.

    A chord toggles once, until every key has been released. The physical
    keys remain tracked even when forwarding is disabled.
    """
    def __init__(self, keys=(), remote=True):
        self.keys=set(keys)
        self.remote=remote
        self.latched=False

    def update(self, code, value):
        """Return True only when a fresh shortcut toggles the preference."""
        if value == 1:
            fresh=code not in self.keys
            self.keys.add(code)
            if fresh and not self.latched and escape_pressed(self.keys, code):
                self.remote=not self.remote
                self.latched=True
                return True
        elif value == 0:
            self.keys.discard(code)
            if not self.keys: self.latched=False
        return False

    def ready(self):
        return not self.keys and not self.latched

    def output(self):
        return reports(self.keys if self.remote and not self.latched else set())

    def disconnect(self):
        # Never recapture a keyboard unexpectedly after losing the host.
        self.remote=False
