#!/usr/bin/env python3
"""Build/verify the sole bootstrap override; never edit a source ISO or initrd."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path('/srv/oneboot')
VERSIONS = ('9.2-1', '8.4-1', '7.4-1')
INSERT = '''            root=/dev/ram0)
                # OneBoot: select kernel ramfs, then use normal RAM ISO discovery.
                # Proxmox filters root= out of the installed system's boot options.
            ;;
'''
ANCHOR = '            root=/dev/mapper/*)\n'

def original_init(version):
    decoder = subprocess.Popen(['gzip', '-dc', str(ROOT / 'assets/proxmox' / version / 'initrd-pxe.img')], stdout=subprocess.PIPE)
    try:
        result = subprocess.run(['cpio', '--quiet', '-i', '--to-stdout', 'init'], stdin=decoder.stdout, capture_output=True, check=True)
        decoder.stdout.close()
        if decoder.wait() != 0:
            raise RuntimeError('gzip failed')
        return result.stdout
    finally:
        if decoder.poll() is None:
            decoder.terminate()
            decoder.wait()

def make_override(source):
    text = source.decode()
    assert text.startswith('#!/bin/sh\n') and text.count(ANCHOR) == 1
    patched = text.replace(ANCHOR, INSERT + ANCHOR)
    assert patched.replace(INSERT, '') == text
    subprocess.run(['sh', '-n'], input=patched, text=True, check=True)
    # Execute only the command-line parser, never the full boot script.
    parser = re.search(r'^parse_cmdline\(\) \{\n.*?^\}', patched, re.M | re.S).group()
    assert parser.count('$(cat /proc/cmdline)') == 1
    parser = parser.replace('$(cat /proc/cmdline)', '$ONEBOOT_TEST_CMDLINE')
    for value, expected in [('root=/dev/ram0 ro quiet', '|'),
                            ('root=/dev/mapper/pve-root', '|/dev/mapper/pve-root'),
                            ('root=/dev/sda1', '/dev/sda1|')]:
        command = 'ONEBOOT_TEST_CMDLINE=$1\n' + parser + '\nparse_cmdline\nprintf "%s|%s" "$root" "$lvm2root"\n'
        result = subprocess.run(['sh', '-c', command, 'test', value], capture_output=True, text=True, check=True)
        assert result.stdout == expected, (value, result.stdout)
    return patched.encode()

def upstream_target(version, cmdline):
    sqfs = ROOT / 'staging/proxmox-regression' / version / 'pve-installer.squashfs'
    path = 'usr/share/perl5/Proxmox/Install/Config.pm'
    source = subprocess.check_output(['unsquashfs', '-cat', str(sqfs), path]).decode()
    function = re.search(r'^sub parse_kernel_cmdline \{.*?(?=^(?:my )?sub init_cfg)', source, re.M | re.S).group()
    code = '''package Proxmox::Install::RunEnv; sub get { return $ARGV[0]; }
package Proxmox::Install::ISOEnv; sub get { return {product => 'pve'}; }
package main;
''' + function + '\nprint parse_kernel_cmdline({})->{target_cmdline};\n'
    return subprocess.check_output(['perl', '-e', code, cmdline]).decode()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    stage = ROOT / 'staging/proxmox-oneboot-bootstrap'
    if not args.verify:
        stage.mkdir(mode=0o750, parents=True, exist_ok=True)
    records, hashes = {}, []
    old = 'initrd=initrd.magic rootfstype=ramfs ro ramdisk_size=16777216 rw quiet splash=silent'
    new = 'root=/dev/ram0 ro ramdisk_size=16777216 rw quiet splash=silent'
    for version in VERSIONS:
        original = original_init(version)
        override = make_override(original)
        record = {'original_init_sha256': hashlib.sha256(original).hexdigest(),
                  'override_sha256': hashlib.sha256(override).hexdigest()}
        if not version.startswith('7.'):
            record['old_target_cmdline'] = upstream_target(version, old)
            record['new_target_cmdline'] = upstream_target(version, new)
            # Native EFI adds the image name as argv[0] to the kernel command line.
            record['new_uefi_target_cmdline'] = upstream_target(version, 'linux26 ' + new)
            assert 'rootfstype=ramfs' in record['old_target_cmdline']
            assert record['new_target_cmdline'] == ''
            assert record['new_uefi_target_cmdline'] == 'linux26'
            assert 'rootfstype=' not in record['new_uefi_target_cmdline']
            assert 'initrd=' not in record['new_uefi_target_cmdline']
        asset = ROOT / 'assets/proxmox' / version / 'init-oneboot-v1.0'
        if args.verify:
            assert asset.read_bytes() == override, str(asset)
        else:
            (stage / f'{version}.init').write_bytes(override)
        hashes.append(f'{record["override_sha256"]}  proxmox/{version}/init-oneboot-v1.0\n')
        records[version] = record
        print(f'PASS {version}: exact bootstrap-only diff; parser and target-command-line regression checks')
    if not args.verify:
        (ROOT / 'src/config/proxmox-oneboot-bootstrap.sha256').write_text(''.join(hashes))
        (stage / 'regression.json').write_text(json.dumps(records, indent=2) + '\n')

if __name__ == '__main__':
    main()
