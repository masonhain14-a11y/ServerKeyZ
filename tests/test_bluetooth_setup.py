import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch, Mock
from bluetooth_setup import PairingPolicy, keyboard_class, set_class, read_class, resolve_conflict, restore_runtime

class BluetoothSetupTests(unittest.TestCase):
    def setUp(self):
        self.path='/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'
        self.address='AA:BB:CC:DD:EE:FF'
        self.p=PairingPolicy('/org/bluez/hci0')
    def test_keyboard_class(self):
        self.assertTrue(keyboard_class(0x400540))
        self.assertTrue(keyboard_class(0x002540))
        self.assertFalse(keyboard_class(0x40010c))
    def test_class_command(self):
        with patch('bluetooth_setup.command') as cmd:
            set_class(0,0x400540)
            cmd.assert_called_once_with('btmgmt','--index','0','class','5','64')
    def test_read_class(self):
        with patch('bluetooth_setup.command',return_value='addr A class 0x400540\n'):
            self.assertEqual(read_class(0),0x400540)
    def test_missing_class(self):
        with patch('bluetooth_setup.command',return_value='no controller'):
            with self.assertRaises(RuntimeError): read_class(0)
    def test_reject_by_default(self):
        self.assertFalse(self.p.approve(self.path,self.address,'Mac',lambda _:''))
        self.assertIsNone(self.p.approved)
    def test_approve_one_host(self):
        self.assertTrue(self.p.approve(self.path,self.address,'Mac',lambda _:'y'))
        self.assertTrue(self.p.approve(self.path,self.address,'Mac',lambda _:'n'))
        self.assertFalse(self.p.approve(self.path,'11:22:33:44:55:66','Other',lambda _:'y'))
    def test_reject_wrong_adapter(self):
        self.assertFalse(self.p.approve(self.path.replace('hci0','hci1'),self.address,'Mac',lambda _:'y'))
    def test_expired_window(self):
        self.p.pairing_open=False
        self.assertFalse(self.p.approve(self.path,self.address,'Mac',lambda _:'y'))
    def test_existing_host_after_window(self):
        self.p.approve(self.path,self.address,'Mac',lambda _:'y')
        self.p.pairing_open=False
        self.assertTrue(self.p.approve(self.path,self.address,'Mac',lambda _:'n'))
    def test_cancel(self):
        self.p.approve(self.path,self.address,'Mac',lambda _:'y')
        self.p.cancel(); self.assertIsNone(self.p.approved)
    def test_peer_allowlist(self):
        p=PairingPolicy('/org/bluez/hci0','11:22:33:44:55:66')
        self.assertFalse(p.approve(self.path,self.address,'Mac',lambda _:'y'))
    def test_runtime_override_reversible(self):
        with tempfile.TemporaryDirectory() as d, patch('bluetooth_setup.DROPIN',Path(d)/'conf'), patch('bluetooth_setup.command') as cmd:
            cmd.return_value='{ path=/usr/libexec/bluetooth/bluetoothd ; argv[]=/usr/libexec/bluetooth/bluetoothd ; ignore_errors=no ; }'
            with ExitStack() as stack:
                resolve_conflict(stack)
                self.assertIn('--noplugin=input',(Path(d)/'conf').read_text())
            self.assertFalse((Path(d)/'conf').exists())
            self.assertEqual(cmd.call_count,5)
    def test_custom_service_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d, patch('bluetooth_setup.DROPIN',Path(d)/'conf'), patch('bluetooth_setup.command') as cmd:
            cmd.return_value='{ path=/usr/libexec/bluetooth/bluetoothd ; argv[]=/usr/libexec/bluetooth/bluetoothd --debug ; }'
            with ExitStack() as stack, self.assertRaisesRegex(RuntimeError,'customized'):
                resolve_conflict(stack)
            self.assertFalse((Path(d)/'conf').exists())

if __name__=='__main__': unittest.main()
