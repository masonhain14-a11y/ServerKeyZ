#!/usr/bin/env python3
"""Forward one explicitly selected Linux keyboard to a paired Bluetooth HID host."""
import argparse, os, re, select, signal, socket, sys, time
from contextlib import ExitStack
from xml.sax.saxutils import quoteattr
from hid import REPORT_MAP, State, reports

UUID='00001124-0000-1000-8000-00805f9b34fb'
PATH='/org/serverkeyz/keyboard'
BLUEZ='org.bluez'

def sdp(name):
    def a(n, content): return f'<attribute id="0x{n:04x}">{content}</attribute>'
    def v(t,x): return f'<{t} value="{x}"/>'
    def seq(*x): return '<sequence>'+''.join(x)+'</sequence>'
    def proto(psm): return seq(seq(v('uuid','0x0100'),v('uint16',hex(psm))),seq(v('uuid','0x0011')))
    fields=[a(1,seq(v('uuid','0x1124'))),a(4,proto(17)),a(5,seq(v('uuid','0x1002'))),a(6,seq(v('uint16','0x656e'),v('uint16','0x006a'),v('uint16','0x0100'))),a(9,seq(seq(v('uuid','0x1124'),v('uint16','0x0101')))),a(13,seq(proto(19))),a(0x100,'<text value='+quoteattr(name)+'/>'),a(0x206,seq(seq(v('uint8','0x22'),f'<text encoding="hex" value="{REPORT_MAP.hex()}"/>'))),a(0x207,seq(seq(v('uint16','0x0409'),v('uint16','0x0100'))))]
    for n,t,x in [(0x200,'uint16','0x0100'),(0x201,'uint16','0x0111'),(0x202,'uint8','0x40'),(0x203,'uint8','0'),(0x204,'boolean','true'),(0x205,'boolean','false'),(0x208,'boolean','false'),(0x209,'boolean','true'),(0x20a,'boolean','true'),(0x20b,'uint16','0x0100'),(0x20c,'uint16','0x0c80'),(0x20d,'boolean','true'),(0x20e,'boolean','false')]: fields.append(a(n,v(t,x)))
    return '<?xml version="1.0"?><record>'+''.join(fields)+'</record>'

def listen(addr, psm):
    s=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_SEQPACKET,socket.BTPROTO_L2CAP)
    try:
        # Linux SOL_BLUETOOTH=274, BT_SECURITY=4; MEDIUM requires encryption.
        s.setsockopt(274,4,bytes([2,0]))
        s.bind((addr,psm)); s.listen(4); s.setblocking(False)
        return s
    except BaseException:
        s.close(); raise

def send(s, payload):
    if s.send(payload)!=len(payload): raise OSError('Short HID packet')

def input_packet(s, rid, payload): send(s,bytes([0xa1,rid])+payload)

def release(s):
    for rid,payload in enumerate(reports(set()),1):
        try: input_packet(s,rid,payload)
        except OSError: pass

def control(s, packet, current):
    """Basic report-protocol HIDP control handling. False = stop session."""
    op=packet[0]&0xf0; param=packet[0]&0xf
    if op==0x10:  # HID_CONTROL (unplug/reset/suspend)
        return param not in (1,2,3,5)
    if op==0x40:  # GET_REPORT
        rid=packet[1] if len(packet)>1 else 0
        if param==1 and rid in (1,2): send(s,bytes([0xa1,rid])+current[rid-1])
        elif param==2 and rid==1: send(s,b'\xa2\x01\x00')
        else: send(s,b'\x02')
    elif op==0x50: send(s,b'\x00' if param==2 and len(packet)>=3 and packet[1]==1 else b'\x04')
    elif op==0x60: send(s,b'\xa0\x01') # GET_PROTOCOL: report
    elif op==0x70: send(s,b'\x00' if param==1 else b'\x03') # no boot mode
    elif op==0x90: send(s,b'\x03') # SET_IDLE unsupported
    elif op==0x80: send(s,b'\x03') # GET_IDLE unsupported
    elif op!=0xa0: send(s,b'\x03')
    return True

def run(args, keyboard, dbus, GLib):
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    bus=dbus.SystemBus(); ctx=GLib.MainContext.default()
    root=dbus.Interface(bus.get_object(BLUEZ,'/'),'org.freedesktop.DBus.ObjectManager')
    adapter_path='/org/bluez/'+args.adapter
    props=dbus.Interface(bus.get_object(BLUEZ,adapter_path),'org.freedesktop.DBus.Properties')
    adapter=props.GetAll('org.bluez.Adapter1')
    if not adapter['Powered']: raise RuntimeError('Adapter is off; use bluetoothctl power on.')
    addr=str(adapter['Address'])
    def authorized(peer):
        for p,ifs in root.GetManagedObjects().items():
            d=ifs.get('org.bluez.Device1',{})
            if str(p).startswith(adapter_path+'/') and str(d.get('Address','')).upper()==peer:
                return bool(d.get('Paired') and d.get('Trusted') and (not args.peer or args.peer==peer))
        return False
    class Profile(dbus.service.Object):
        ended=False
        disconnect_requested=False
        @dbus.service.method('org.bluez.Profile1',in_signature='',out_signature='')
        def Release(self): self.ended=True
        @dbus.service.method('org.bluez.Profile1',in_signature='oha{sv}',out_signature='')
        def NewConnection(self,device,fd,properties):
            os.close(fd.take()) # raw listeners own both HID channels
            raise dbus.exceptions.DBusException('Use HID channels',name='org.bluez.Error.Rejected')
        @dbus.service.method('org.bluez.Profile1',in_signature='o',out_signature='')
        def RequestDisconnection(self,device): self.disconnect_requested=True
    profile=Profile(bus,PATH)
    manager=dbus.Interface(bus.get_object(BLUEZ,'/org/bluez'),'org.bluez.ProfileManager1')
    with ExitStack() as stack:
        for psm in (17,19):
            try: s=listen(addr,psm)
            except OSError as e: raise RuntimeError(f'Cannot bind HID PSM {psm}: {e}. See README BlueZ conflict instructions.') from e
            stack.enter_context(s)
            if psm==17: lc=s
            else: li=s
        manager.RegisterProfile(PATH,UUID,dbus.Dictionary({'Name':args.name,'Role':'server','ServiceRecord':sdp(args.name),'RequireAuthentication':dbus.Boolean(True),'RequireAuthorization':dbus.Boolean(True)},signature='sv'))
        def unregister():
            try: manager.UnregisterProfile(PATH)
            except dbus.DBusException: pass
        stack.callback(unregister)
        print(f'Listening on {args.adapter} ({addr}). Keyboard is local until a trusted host connects.',flush=True)
        print(r'Super + Ctrl + Alt + \ toggles local / Bluetooth mode. Ctrl+C in SSH stops the app.',flush=True)
        channels={}; peer=None; deadline=0; check_at=0
        state=State(keyboard.active_keys()); grabbed=False
        empty=reports(set()); current=empty
        # Drop events from before launch; the keyboard stays local at this point.
        try:
            for _ in keyboard.read(): pass
        except BlockingIOError: pass
        state.keys=set(keyboard.active_keys())

        def ungrab():
            nonlocal grabbed
            if grabbed:
                keyboard.ungrab()
                grabbed=False

        def close_session(disconnected=False):
            nonlocal peer, current
            if li in channels: release(channels[li])
            ungrab()
            for c in channels.values(): c.close()
            channels.clear(); peer=None; current=empty
            if disconnected:
                state.disconnect()
                print('Host disconnected. LOCAL MODE; app is still listening. Toggle to enable Bluetooth again.',flush=True)

        stack.callback(close_session)

        def update_reports(new):
            nonlocal current
            for rid,(old,payload) in enumerate(zip(current,new),1):
                if old!=payload: input_packet(channels[li],rid,payload)
            current=new

        def reconcile():
            nonlocal grabbed, current
            if grabbed and not state.remote and state.ready() and not keyboard.active_keys():
                ungrab()
                print('LOCAL MODE: keyboard restored. Use the same shortcut to enable Bluetooth.',flush=True)
            if not grabbed and state.remote and len(channels)==2 and state.ready() and not keyboard.active_keys():
                keyboard.grab(); grabbed=True
                # Avoid transferring a held key from the local OS to the host.
                if keyboard.active_keys():
                    ungrab(); return
                current=empty
                for rid,payload in enumerate(current,1): input_packet(channels[li],rid,payload)
                print('REMOTE MODE: keyboard is forwarding over Bluetooth.',flush=True)

        while not profile.ended:
            while ctx.pending(): ctx.iteration(False)
            if profile.disconnect_requested:
                profile.disconnect_requested=False
                if channels: close_session(disconnected=True)
            now=time.monotonic()
            if channels and len(channels)<2 and now>deadline:
                close_session()
            if len(channels)==2 and now>=check_at:
                if not authorized(peer): close_session(disconnected=True)
                check_at=now+2
            readable=select.select([keyboard,lc,li,*channels.values()],[],[],0.2)[0]
            # Read the selected physical keyboard even while ungrabbed. Local
            # mode never sends its key events to the remote host.
            if keyboard in readable:
                try: events=list(keyboard.read())
                except BlockingIOError: events=[]
                for ev in events:
                    if ev.type==0 and ev.code==3:
                        raise RuntimeError('Input queue overrun; stopping safely.')
                    if ev.type!=1 or ev.value not in (0,1): continue
                    toggled=state.update(ev.code,ev.value)
                    if toggled:
                        print(('Bluetooth requested; release all keys.' if state.remote else 'Bluetooth disabled; release all keys to restore local input.'),flush=True)
                    if grabbed and len(channels)==2:
                        try: update_reports(state.output())
                        except OSError: close_session(disconnected=True)
            for listener in (lc,li):
                if listener not in readable: continue
                try: c,remote=listener.accept()
                except BlockingIOError: continue
                remote=remote[0].upper()
                try:
                    if not authorized(remote) or (peer is not None and remote!=peer) or listener in channels:
                        print(f'Rejected {remote}: pair and trust selected host first, then reconnect.',flush=True); c.close(); continue
                    c.settimeout(0.5); channels[listener]=c; peer=remote; deadline=time.monotonic()+15
                    if len(channels)==2:
                        print(f'Connected to {peer}. '+('Release all keys to activate remote mode.' if state.remote else 'Local mode remains active until shortcut is pressed.'),flush=True)
                        check_at=0
                except BaseException: c.close(); raise
            for listener,c in list(channels.items()):
                if c not in readable: continue
                try:
                    packet=c.recv(1024)
                    if not packet or (listener is lc and not control(c,packet,current)):
                        close_session(disconnected=True); break
                except OSError:
                    close_session(disconnected=True); break
            try: reconcile()
            except OSError:
                # A Bluetooth write may fail during activation. If grabbing
                # itself failed, exit instead of retrying an unavailable device.
                if not grabbed: raise
                close_session(disconnected=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list',action='store_true',help='List eligible physical keyboard event devices')
    ap.add_argument('--device',help='Path to /dev/input/by-id/...-event-kbd or /dev/input/eventN')
    ap.add_argument('--adapter',default='hci0')
    ap.add_argument('--name',default='ServerKeyZ',help='HID service name; set adapter alias separately')
    ap.add_argument('--peer',type=str.upper,help='Optional allowlist: one host Bluetooth MAC')
    args=ap.parse_args()
    if args.peer and not re.fullmatch(r'([0-9A-F]{2}:){5}[0-9A-F]{2}',args.peer): ap.error('Invalid peer MAC')
    if not re.fullmatch(r'hci[0-9]+',args.adapter): ap.error('Invalid adapter')
    try:
        import evdev
    except ImportError: ap.error('Install python3-evdev (see README).')
    def suitable(d): return {30,43,29,56,125}.issubset(set(d.capabilities().get(1,[]))) or {30,43,97,100,126}.issubset(set(d.capabilities().get(1,[])))
    if args.list:
        for path in evdev.list_devices():
            with evdev.InputDevice(path) as d:
                if suitable(d): print(f'{path}\t{d.name}\t{d.phys}')
        return 0
    if not args.device: ap.error('Choose a keyboard with --list, then provide --device.')
    if os.geteuid()!=0: ap.error('Run with sudo for input and Bluetooth access.')
    try:
        import dbus
        from gi.repository import GLib
        with evdev.InputDevice(args.device) as keyboard:
            if not suitable(keyboard): raise RuntimeError('Selected device does not expose required keyboard keys.')
            run(args,keyboard,dbus,GLib)
    except KeyboardInterrupt: pass
    except (OSError,RuntimeError,ImportError) as e: print(f'Error: {e}',file=sys.stderr); return 1
    finally: print('Local keyboard control restored (app stopped).',flush=True)
    return 0

if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main())
