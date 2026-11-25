import unittest
import xml.etree.ElementTree as ET
from hid import State, reports, REPORT_MAP
from serverkeyz import sdp, control, input_packet, release

class FakeSocket:
    def __init__(self): self.sent=[]
    def send(self,p): self.sent.append(p); return len(p)

class HidTests(unittest.TestCase):
    def test_empty(self): self.assertEqual(reports(set()),(bytes(8),bytes(2)))
    def test_letter_modifier(self): self.assertEqual(reports({30,42})[0],bytes([2,0,4,0,0,0,0,0]))
    def test_numbers(self): self.assertEqual(reports({2,11})[0][2:4],bytes([30,39]))
    def test_hotkey(self):
        for chord in [(125,29,56),(126,97,100),(125,97,56)]:
            st=State()
            for key in chord: self.assertFalse(st.update(key,1))
            self.assertTrue(st.update(43,1)); self.assertFalse(st.remote)
            self.assertEqual(st.output(),reports(set()))
            for key in (*chord,43): st.update(key,0)
            self.assertTrue(st.ready())
            for key in chord: st.update(key,1)
            self.assertTrue(st.update(43,1)); self.assertTrue(st.remote)
            self.assertEqual(st.output(),reports(set()))
            for key in (*chord,43): st.update(key,0)
            self.assertTrue(st.ready())
            st.update(30,1); self.assertEqual(st.output(),reports({30}))
    def test_normal_backslash(self):
        st=State(); st.update(29,1); self.assertFalse(st.update(43,1)); self.assertIn(49,st.output()[0]); st.update(43,0); self.assertNotIn(49,st.output()[0])
    def test_local_input_never_forwarded(self):
        st=State(remote=False); st.update(30,1); st.update(115,1)
        self.assertEqual(st.output(),reports(set()))
    def test_chord_repeat_is_latched(self):
        st=State()
        for key in (125,29,56,43): st.update(key,1)
        self.assertFalse(st.update(43,2)); self.assertFalse(st.update(43,1))
        st.update(43,0); self.assertFalse(st.update(43,1)); self.assertFalse(st.remote)
        self.assertFalse(st.ready())
        for key in (125,29,56,43): st.update(key,0)
        self.assertTrue(st.ready())
    def test_disconnect_disarms(self):
        st=State(); st.update(30,1); st.disconnect()
        self.assertFalse(st.remote); self.assertEqual(st.output(),reports(set()))
        st.update(30,0)
        for key in (125,29,56,43): st.update(key,1)
        self.assertTrue(st.remote); self.assertEqual(st.output(),reports(set()))
    def test_wait_for_other_held_keys(self):
        st=State()
        for key in (30,125,29,56,43): st.update(key,1)
        for key in (125,29,56,43): st.update(key,0)
        self.assertFalse(st.ready()); st.update(30,0); self.assertTrue(st.ready())
    def test_rollover(self): self.assertEqual(reports(set(range(2,9)))[0][2:],bytes([1]*6))
    def test_volume(self): self.assertEqual(reports({115})[1],b'\xe9\x00')
    def test_repeat(self):
        st=State(); st.update(30,1); st.update(30,2); self.assertEqual(st.keys,{30}); st.update(30,0); self.assertEqual(st.keys,set())
    def test_sdp(self):
        root=ET.fromstring(sdp('ServerKeyZ & "Test"'))
        self.assertEqual(root.find("attribute[@id='0x0100']/text").get('value'),'ServerKeyZ & "Test"')
        self.assertEqual(root.find("attribute[@id='0x0206']//text").get('value'),REPORT_MAP.hex())
    def test_packet_release(self):
        s=FakeSocket(); input_packet(s,1,reports({30})[0]); release(s)
        self.assertEqual(s.sent,[b'\xa1\x01\x00\x00\x04'+bytes(5), b'\xa1\x01'+bytes(8),b'\xa1\x02'+bytes(2)])
    def test_control(self):
        s=FakeSocket(); self.assertTrue(control(s,b'\x41\x01',reports({30})))
        self.assertEqual(s.sent[-1],b'\xa1\x01'+reports({30})[0]); self.assertTrue(control(s,b'\x71',reports(set())))
        self.assertEqual(s.sent[-1],b'\x00'); self.assertFalse(control(s,b'\x15',reports(set())))

if __name__=='__main__': unittest.main()
