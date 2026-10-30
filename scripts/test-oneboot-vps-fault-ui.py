#!/usr/bin/env python3
"""Exercise the real ISO with denied VPS access and capture opt-in fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

sys.path.insert(0,str(Path(__file__).parent))
from oneboot_test_windows import WindowsVM
api=runpy.run_path(str(Path(__file__).with_name('test-oneboot-v1.4.1-qemu.py')))
def public_seen(p):
    b=p.read_bytes() if p.exists() else b''
    return b'github.com' in b or b'\x06github\x03com' in b
def screen(vm,p):api['screen'](vm.c,p)
def key(vm,s):api['type_text'](vm.c,s)
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--iso',type=Path,required=True);p.add_argument('--firmware',choices=('bios','uefi'),required=True)
    p.add_argument('--case-tag',default='')
    a=p.parse_args();root=a.root.resolve();iso=a.iso.resolve()
    assert root==Path('C:/Projects/_analysis/oneboot141-local-tests').resolve() and iso.parent==root
    assert not a.case_tag or a.case_tag.replace('-','').isalnum()
    case=root/'tests'/('vps-denied-'+a.firmware+('-'+a.case_tag if a.case_tag else ''));case.mkdir(parents=True,exist_ok=True)
    assert not (case/'result.json').exists()
    os.environ['ONEBOOT_TEST_PCAP']='1';records=[]
    with WindowsVM(root,case,a.firmware,1024,iso,False) as vm:
        api['reach_version'](vm,'26')
        for index,version in enumerate(('26','24','22','20','18')):
            if index:key(vm,{'24':'2','22':'3','20':'4','18':'5'}[version]);time.sleep(.6)
            for mode in ('manual','auto'):
                if mode=='manual':key(vm,'m')
                else:
                    api['profile'](vm,'ob141-fault','OneBootTest1!','OneBootTest1!');key(vm,'\n');time.sleep(.5);key(vm,'g')
                time.sleep(8)
                capture=case/(version+'-'+mode+'-vps-failed.ppm');screen(vm,capture)
                assert not public_seen(case/'network.pcap'),'GitHub contacted before operator fallback'
                if index==0 and mode=='manual':
                    time.sleep(15);screen(vm,case/'held-after-23-seconds.ppm')
                    assert not public_seen(case/'network.pcap')
                    key(vm,'d');time.sleep(.8);screen(vm,case/'vps-fetch-details.ppm')
                    api['key'](vm.c,'esc');time.sleep(.7)
                records.append({'version':version,'mode':mode,'no_public_before_choice':True,'capture':capture.name})
                key(vm,'b');time.sleep(.7)
            key(vm,'b');time.sleep(.7)
        # The independent manual net entries also start on the VPS.
        for digit,version in (('6','20'),('7','18')):
            key(vm,digit);time.sleep(8);screen(vm,case/(version+'-net-vps-failed.ppm'))
            assert not public_seen(case/'network.pcap')
            records.append({'version':version,'mode':'manual_net','no_public_before_choice':True})
            key(vm,'b');time.sleep(.5);key(vm,'b');time.sleep(.5)
        before=(case/'network.pcap').read_bytes()
        (case/'before-fallback.pcap').write_bytes(before)
        key(vm,'1');time.sleep(.5);key(vm,'m');time.sleep(8);screen(vm,case/'before-fallback-choice.ppm')
        assert not public_seen(case/'network.pcap')
        key(vm,'f');deadline=time.monotonic()+40
        while time.monotonic()<deadline and not public_seen(case/'network.pcap'):time.sleep(.3)
        assert public_seen(case/'network.pcap'),'Explicit fallback did not contact GitHub'
        screen(vm,case/'after-explicit-fallback.ppm')
    record={'iso_sha256':api['sha'](iso),'firmware':a.firmware,'no_guest_disks':True,
        'pass':True,'captures_require_visual_review':True,'cases':records,
        'github_only_after_explicit_fallback':True,'initial_hold_seconds':23}
    (case/'result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
if __name__=='__main__':main()
