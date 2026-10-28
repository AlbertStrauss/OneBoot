#!/usr/bin/env python3
"""Exercise generated profiles and first-disk protection without real disks."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
import yaml

SOURCE=Path(__file__).resolve().parents[1]
HELPERS=SOURCE/'autoinstall'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='oneboot-profile-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.live=self.root/'live';(self.live/'etc').mkdir(parents=True)
        self.functions=self.root/'functions';self.functions.write_text('log_begin_msg() { :; }; log_end_msg() { :; }\n')
        self.profile=self.root/'profile'
        self.password='Visible pw $;"&/: + !'
        self.profile.write_text('HOSTNAME=server-01\nPASSWORD_HEX='+self.password.encode().hex()+'\n')
        self.cmdline=self.root/'cmdline'
        self.cmdline.write_text('autoinstall oneboot.autoinstall=1 BOOTIF=01-52-54-00-12-34-56 onebootcidr=31 ip=192.0.2.10::192.0.2.11:255.255.255.254:::none:192.0.2.53')
        self.env=dict(os.environ,oneboot_root=str(self.live),oneboot_profile=str(self.profile),
            oneboot_casper_functions=str(self.functions),oneboot_cmdline=str(self.cmdline),
            oneboot_disks=str(HELPERS/'oneboot-disk'),oneboot_set_password=str(HELPERS/'oneboot-set-password'),oneboot_run=str(self.root/'initramfs-run'))
    def seed(self):
        return subprocess.run(['sh',str(HELPERS/'99onebootseed')],env=self.env,stdin=subprocess.DEVNULL,capture_output=True,text=True)
    def test_auto_profile_has_only_one_disk_and_static_network(self):
        r=self.seed();self.assertEqual(r.returncode,0,r.stderr)
        seed=self.live/'var/lib/cloud/seed/nocloud'
        raw=(seed/'user-data').read_text();d=yaml.safe_load(raw)['autoinstall']
        self.assertEqual(d['storage']['layout'],{'name':'direct','match':{'path':'@ZDISK@'}})
        self.assertEqual(d['interactive-sections'],[])
        self.assertEqual(d['identity']['hostname'],'server-01')
        self.assertEqual(d['identity']['password'],'!')
        self.assertNotIn(self.password,raw);self.assertNotIn(self.password.encode().hex(),raw)
        for network in (d['network'],yaml.safe_load((seed/'network-config').read_text())):
            n=network['ethernets']['onebootnic']
            self.assertFalse(n['dhcp4']);self.assertFalse(n['dhcp6'])
            self.assertEqual(n['addresses'],['192.0.2.10/31'])
            self.assertEqual(n['nameservers']['addresses'],['192.0.2.53','192.0.2.53'])
        self.assertEqual((self.root/'initramfs-run/oneboot-profile').stat().st_mode&0o777,0o600)
        self.assertFalse((self.live/'run/oneboot-profile').exists())
    def test_manual_creates_no_seed_even_with_profile_present(self):
        self.cmdline.write_text('BOOTIF=01-52-54-00-12-34-56 onebootcidr=24')
        self.assertEqual(self.seed().returncode,0)
        self.assertFalse((self.live/'var/lib/cloud/seed').exists())
        self.assertFalse((self.live/'run/oneboot-profile').exists())
    def test_both_auto_authorizations_required(self):
        self.cmdline.write_text('autoinstall')
        self.assertEqual(self.seed().returncode,0)
        self.assertFalse((self.live/'var/lib/cloud/seed').exists())
    def test_missing_credentials_fail_before_seed(self):
        self.profile.unlink();self.assertNotEqual(self.seed().returncode,0)
        self.assertFalse((self.live/'var/lib/cloud/seed').exists())
    def test_password_special_characters_arrive_only_on_stdin(self):
        bindir=self.root/'bin';bindir.mkdir();sink=self.root/'sink'
        curtin=bindir/'curtin'
        curtin.write_text('#!/bin/sh\ncase "$*" in *chpasswd) cat > "$ONEBOOT_SINK" ;; *) : ;; esac\n');curtin.chmod(0o755)
        chpasswd=bindir/'chpasswd'
        chpasswd.write_text('#!/bin/sh\n[ "$1" = --root ] && [ "$2" = /target ] || exit 90\ncat > "$ONEBOOT_SINK"\n');chpasswd.chmod(0o755)
        env=dict(self.env,PATH=str(bindir)+':'+os.environ['PATH'],oneboot_live_profile=str(self.profile),ONEBOOT_SINK=str(sink))
        r=subprocess.run(['bash',str(HELPERS/'oneboot-set-password')],env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(sink.read_text(),f'root:{self.password}\nuser:{self.password}\n')
        self.assertNotIn(self.password,r.stdout+r.stderr);self.assertFalse(self.profile.exists())

    def check_restored_repositories(self,deb822):
        self.assertEqual(self.seed().returncode,0)
        config=yaml.safe_load((self.live/'var/lib/cloud/seed/nocloud/user-data').read_text())['autoinstall']
        actual=next(c for c in config['late-commands'] if 'VERSION_CODENAME' in c)
        command=shlex.split(actual)[-1]
        target=self.root/'apt-target';etc=target/'etc';(etc/'apt/sources.list.d').mkdir(parents=True)
        (etc/'os-release').write_text('VERSION_CODENAME=jammy\n')
        if deb822:
            source=etc/'apt/sources.list.d/ubuntu.sources'
            source.write_text('Types: deb\nURIs: http://archive.ubuntu.com/ubuntu/\nSuites: jammy\nComponents: main\n')
        else:
            source=etc/'apt/sources.list'
            source.write_text('deb http://archive.ubuntu.com/ubuntu jammy main\n'+''.join(
                f'# deb http://archive.ubuntu.com/ubuntu jammy-{pocket} main\n'
                for pocket in ('updates','security','backports'))+'# retain unrelated operator comment\n')
        # Execute the actual generated late-command against fixture /etc paths.
        # Never run curtin or alter host /etc during this regression test.
        command=command.replace('/etc/',str(etc)+'/')
        r=subprocess.run(['sh','-c',command],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        result=source.read_text()
        for pocket in ('updates','security','backports'):self.assertIn('jammy-'+pocket,result)
        if deb822:self.assertIn('Suites: jammy jammy-updates jammy-security jammy-backports\n',result)
        else:
            self.assertNotIn('# deb ',result)
            self.assertIn('# retain unrelated operator comment',result)

    def test_restore_legacy_apt_repositories(self):self.check_restored_repositories(False)
    def test_restore_deb822_apt_repositories(self):self.check_restored_repositories(True)

    def fake_disk(self,name,size=2000000,removable=0,ro=0,usb=False,busy=False):
        sys=self.root/'sys';dev=self.root/'dev'
        (sys/'block').mkdir(parents=True,exist_ok=True);dev.mkdir(exist_ok=True)
        actual=sys/('devices/usb1' if usb else 'devices/pci1')/name
        actual.mkdir(parents=True);(sys/'block'/name).symlink_to(actual,target_is_directory=True)
        for n,value in [('size',size),('removable',removable),('ro',ro)]: (actual/n).write_text(str(value))
        (actual/'holders').mkdir()
        if busy:(actual/'holders/dm-0').write_text('active')
        (dev/name).write_bytes(b'sentinel-'+name.encode())
    def choose_disk(self):
        env=dict(os.environ,oneboot_sys=str(self.root/'sys'),oneboot_dev=str(self.root/'dev'),oneboot_kmsg=str(self.root/'kmsg'))
        return subprocess.run(['sh',str(HELPERS/'oneboot-disk')],env=env,capture_output=True,text=True)
    def test_first_disk_selected_even_when_second_is_larger_and_no_writes(self):
        self.fake_disk('sda',size=1000000);self.fake_disk('sdb',size=99999999)
        before={p:p.read_bytes() for p in (self.root/'dev').iterdir()}
        r=self.choose_disk();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),str(self.root/'dev/sda'))
        self.assertEqual(before,{p:p.read_bytes() for p in (self.root/'dev').iterdir()})
    def test_usb_readonly_empty_and_virtual_disks_excluded(self):
        self.fake_disk('loop0');self.fake_disk('sda',usb=True);self.fake_disk('sdb',ro=1);self.fake_disk('sdc',size=0);self.fake_disk('sdd')
        self.assertEqual(self.choose_disk().stdout.strip(),str(self.root/'dev/sdd'))
    def test_nvme_is_first_in_kernel_name_order(self):
        self.fake_disk('sda');self.fake_disk('nvme0n1')
        self.assertEqual(self.choose_disk().stdout.strip(),str(self.root/'dev/nvme0n1'))
    def test_busy_first_disk_stops_instead_of_touching_another(self):
        self.fake_disk('sda',busy=True);self.fake_disk('sdb')
        r=self.choose_disk();self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')
    def test_no_eligible_disks_stop(self):
        self.fake_disk('sda',removable=1)
        self.assertNotEqual(self.choose_disk().returncode,0)
    def test_fixed_and_latest_ubuntu_mirror_paths(self):
        for filename,series in [('ubuntu-22.04.5-live-server-amd64.iso','22.04'),('ubuntu-24.04.4-live-server-amd64.iso','24.04'),('ubuntu-26.04-live-server-amd64.iso','26.04')]:
            script='. "$1"; URL="https://releases.ubuntu.com/pin/$2"; wget() { return 99; }; oneboot_probe_into() { echo 1; }; oneboot_probe() { echo 100; }; oneboot_say() { :; }; oneboot_mirror_pick; printf "%s\\n" "$oneboot_mirror_url"'
            r=subprocess.run(['sh','-c',script,'oneboot-test',str(HELPERS/'oneboot-mirror-pick'),filename],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertTrue(r.stdout.strip().endswith('/'+series+'/'+filename),r.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
