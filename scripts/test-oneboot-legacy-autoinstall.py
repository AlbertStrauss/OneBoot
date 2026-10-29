#!/usr/bin/env python3
"""Exercise the actual legacy hooks, secret transport and disk failure gate."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]
class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='oneboot14-hooks-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.target=self.root/'target'
        for directory in ('etc/ssh','etc/apt','etc/netplan','etc/network'):(self.target/directory).mkdir(parents=True,exist_ok=True)
        (self.target/'etc/ssh/sshd_config').write_text('# Keep this Match block\nPermitRootLogin prohibit-password\nMatch User example\n    X11Forwarding no\n')
        (self.target/'etc/apt/sources.list').write_text('deb http://archive.ubuntu.com/ubuntu focal main\n')
        (self.target/'etc/os-release').write_text('VERSION_CODENAME=focal\n')
        (self.target/'etc/netplan/01-netcfg.yaml').write_text('network: {version: 2, ethernets: {eth0: {dhcp4: true}}}\n')
        self.password='Visible pw $;"&/: + !'
        self.profile=self.root/'profile';self.profile.write_text('HOSTNAME=ob14-test\nPASSWORD_HEX='+self.password.encode().hex()+'\n')
        self.cmdline=self.root/'cmdline';self.cmdline.write_text('oneboot.autoinstall=1 oneboot.prefix=31 netcfg/get_ipaddress=192.0.2.10 netcfg/get_netmask=255.255.255.254 netcfg/get_gateway=192.0.2.11 netcfg/get_nameservers=192.0.2.53 netcfg/choose_interface=52:54:00:12:34:56')
        self.bin=self.root/'bin';self.bin.mkdir();self.sink=self.root/'password-stdin';self.calls=self.root/'calls'
        self.stub('logger','exit 0')
        self.stub('debconf-set','printf "%s\\n" "$*" >> "$ONEBOOT_CALLS"')
        self.stub('udevadm','exit 0')
        self.stub('chroot','printf "%s\\n" "$*" >> "$ONEBOOT_CALLS"; case "$2" in /usr/sbin/chpasswd) cat > "$ONEBOOT_SINK" ;; esac')
        self.env=dict(os.environ,PATH=str(self.bin)+':'+os.environ['PATH'],oneboot_di_profile=str(self.profile),
            oneboot_di_cmdline=str(self.cmdline),oneboot_di_target=str(self.target),oneboot_di_test='1',
            ONEBOOT_CALLS=str(self.calls),ONEBOOT_SINK=str(self.sink))
    def stub(self,name,body):
        p=self.bin/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755);return p
    def run_hook(self,mode):
        return subprocess.run(['sh',str(SOURCE/'autoinstall/oneboot-di'),mode],env=self.env,capture_output=True,text=True)
    def test_late_password_uses_only_stdin_and_profile_is_removed(self):
        r=self.run_hook('late');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.sink.read_text(),f'root:{self.password}\nuser:{self.password}\n')
        self.assertNotIn(self.password,self.calls.read_text()+r.stdout+r.stderr)
        self.assertFalse(self.profile.exists())
        ssh=(self.target/'etc/ssh/sshd_config').read_text()
        self.assertTrue(ssh.startswith('PermitRootLogin yes\nPasswordAuthentication yes\n'))
        self.assertIn('Match User example',ssh)
    def test_target_static_network_and_security_repository(self):
        self.assertEqual(self.run_hook('late').returncode,0)
        import yaml
        n=yaml.safe_load((self.target/'etc/netplan/01-oneboot.yaml').read_text())['network']['ethernets']['onebootnic']
        self.assertEqual(n['addresses'],['192.0.2.10/31']);self.assertFalse(n['dhcp4']);self.assertFalse(n['dhcp6'])
        self.assertEqual(n['match']['macaddress'],'52:54:00:12:34:56');self.assertTrue(n['routes'][0]['on-link'])
        self.assertIn('focal-security',(self.target/'etc/apt/sources.list').read_text())
        self.assertFalse((self.target/'etc/netplan/01-netcfg.yaml').exists())
    def test_missing_go_authorization_stops_before_any_target_change(self):
        self.cmdline.write_text('auto=true');r=self.run_hook('late')
        self.assertNotEqual(r.returncode,0);self.assertFalse(self.calls.exists());self.assertFalse(self.sink.exists())
    def test_bad_profile_stops_before_any_target_change(self):
        self.profile.write_text('HOSTNAME=valid\nPASSWORD_HEX=not-hex\n')
        self.assertNotEqual(self.run_hook('late').returncode,0);self.assertFalse(self.calls.exists())
    def test_selected_disk_is_explicit_for_partman_and_grub(self):
        selector=self.stub('select-disk','printf "/dev/oneboot-test-first\\n"')
        self.env['oneboot_di_disks']=str(selector)
        r=self.run_hook('disk');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.calls.read_text().splitlines(),['partman-auto/disk /dev/oneboot-test-first','grub-installer/bootdev /dev/oneboot-test-first'])
    def test_failed_disk_selector_cannot_fall_back_to_another_disk(self):
        self.env['oneboot_di_disks']=str(self.stub('select-disk','exit 1'))
        self.assertNotEqual(self.run_hook('disk').returncode,0);self.assertFalse(self.calls.exists())
    def test_password_control_bytes_are_rejected(self):
        self.profile.write_text('HOSTNAME=valid\nPASSWORD_HEX=410a42\n')
        self.assertNotEqual(self.run_hook('late').returncode,0);self.assertFalse(self.sink.exists())
    def test_service_enable_is_offline_without_installer_system_bus(self):
        self.stub('chroot','printf "%s\\n" "$*" >> "$ONEBOOT_CALLS"; case "$2" in /usr/sbin/chpasswd) cat > "$ONEBOOT_SINK" ;; systemctl) [ "$3" = --root=/ ] || exit 84 ;; esac')
        r=self.run_hook('late');self.assertEqual(r.returncode,0,r.stderr)
        calls=self.calls.read_text()
        self.assertIn('systemctl --root=/ enable ssh',calls)
        self.assertIn('systemctl --root=/ enable systemd-networkd',calls)
if __name__=='__main__':unittest.main()
