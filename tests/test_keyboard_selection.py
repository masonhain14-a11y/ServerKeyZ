import unittest
from unittest.mock import patch
from types import SimpleNamespace
from serverkeyz import choose_keyboard, find_keyboards, suitable

BUILTIN = ('/dev/input/event9', 'AT Translated Set 2 keyboard', 'isa0060/serio0/input0')
USB = ('/dev/input/event2', 'USB Keyboard', 'usb-0000:00:14.0/input0')

class SelectionTests(unittest.TestCase):
    def test_single_builtin(self): self.assertEqual(choose_keyboard([BUILTIN]), BUILTIN)
    def test_single_usb(self): self.assertEqual(choose_keyboard([USB]), USB)
    def test_prefer_builtin(self): self.assertEqual(choose_keyboard([USB, BUILTIN]), BUILTIN)
    def test_no_keyboard(self):
        with self.assertRaisesRegex(RuntimeError, 'No eligible'): choose_keyboard([])
    def test_ambiguous(self):
        with self.assertRaisesRegex(RuntimeError, 'Multiple keyboards'): choose_keyboard([USB, ('/dev/input/event5','Other keyboard','usb-other')])
    def test_mixed_modifiers(self):
        self.assertTrue(suitable(SimpleNamespace(capabilities=lambda: {1:[30,43,97,56,125]})))
    def test_not_keyboard(self):
        self.assertFalse(suitable(SimpleNamespace(capabilities=lambda: {1:[30,43]})))
    def test_scan_closes_and_ignores_virtual(self):
        class Device:
            name, phys = BUILTIN[1:]
            closed = False
            def capabilities(self): return {1:[30,43,29,56,125]}
            def close(self): self.closed=True
        d=Device()
        evdev=SimpleNamespace(list_devices=lambda:[BUILTIN[0],USB[0]], InputDevice=lambda path:d)
        with patch('serverkeyz.os.path.realpath',side_effect=lambda p: '/sys/devices/virtual/input/event2' if p.endswith('event2') else '/sys/devices/platform/i8042/serio0/input/event9'):
            self.assertEqual(find_keyboards(evdev), [BUILTIN])
        self.assertTrue(d.closed)
