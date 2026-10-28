#!/usr/bin/env python3
"""Verify the actual small standalone autoinstall ISO and embedded inputs."""
import hashlib
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile

root=Path(sys.argv[1]).resolve();source=root/'source'
iso=root/'releases/v1.3/oneboot-v1.3.iso'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def command(*args):
    r=subprocess.run(args,check=True,capture_output=True,text=True);return r.stdout+r.stderr
boot=command('xorriso','-indev',str(iso),'-report_el_torito','plain')
assert re.search(r'El Torito boot img : +1 +BIOS +y',boot)
assert re.search(r'El Torito boot img : +2 +UEFI +y',boot)
assert 'GPT' in command('xorriso','-indev',str(iso),'-report_system_area','plain')
assert iso.stat().st_size<16*1024**2
with tempfile.TemporaryDirectory(prefix='ob13-verify-') as tmp:
    d=Path(tmp)
    command('xorriso','-osirrox','on','-indev',str(iso),'-extract','/',str(d))
    subprocess.run(['sha256sum','--check','BOOT-LOADERS.sha256'],cwd=d,check=True)
    script=(d/'oneboot.ipxe').read_text()
    assert script==(source/'src/oneboot-v1.3.ipxe.in').read_text().replace('@@BASE_URL@@','https://93.114.194.66/oneboot')
    assert 'set oneboot_version 1.3' in script and 'netboot.xyz' not in script
    labels=re.findall(r'^:([^\n]+)',script,re.M);assert len(labels)==len(set(labels))
    for label in re.findall(r'\bgoto ([a-zA-Z_][a-zA-Z0-9_]*)',script):assert label in labels,label
    blocks=lambda s:dict(re.findall(r'^:([^\n]+)\n(.*?)(?=^:|\Z)',s,re.M|re.S))
    old=blocks((source/'src/oneboot-v1.0.ipxe.in').read_text().replace('@@BASE_URL@@','https://93.114.194.66/oneboot'))
    new=blocks(script)
    changed={'os_menu','boot_ubuntu_2204','boot_ubuntu_2404','boot_ubuntu_2604','boot_ubuntu'}
    for label,body in old.items():
        if label not in changed:assert new[label].strip()==body.strip(),label
    assert 'read oneboot_password ||' in script and 'read oneboot_confirm ||' in script
    assert '--secret' not in new['ubuntu_auto_form']
    assert 'obprofile check oneboot_hostname oneboot_password oneboot_confirm || goto ubuntu_profile_invalid' in new['ubuntu_auto_form']
    assert 'obprofile create' in new['ubuntu_auto_go'] and 'set ubuntu_auto_args autoinstall' in new['ubuntu_auto_go']
    assert 'clear ubuntu_auto_args' in new['ubuntu_manual']
    kernel=[line for line in script.splitlines() if line.startswith('kernel --name kboot ')][0]
    assert 'oneboot_password' not in kernel and 'PASSWORD_HEX' not in kernel
    for line in script.splitlines():
        if line.startswith(('kernel ','initrd ','boot ||')):assert ' || oberror ' in line,line
    bios=root/'toolchain/ipxe/src/bin-x86_64-pcbios/ipxe.lkrn.tmp'
    efi=d/'EFI/BOOT/BOOTX64.EFI'
    for payload in (bios.read_bytes(),efi.read_bytes()):
        assert script.encode() in payload
        for name in ('99onebootseed','param.conf','oneboot-mirror-pick','oneboot-disk','oneboot-set-password'):
            assert (source/'autoinstall'/name).read_bytes() in payload,name
        for cert in (source/'config/ubuntu-live-certs').glob('*.pem'):
            assert ssl.PEM_cert_to_DER_cert(cert.read_text()) in payload,cert.name
    esp=d/'esp-loader.efi'
    command('mcopy','-i',str(d/'oneboot-esp.img'),'::/EFI/BOOT/BOOTX64.EFI',str(esp))
    assert sha(esp)==sha(efi)
    assert (d/'COPYING-FLUXBILLING.txt').read_bytes()==(source/'vendor/fluxbilling/LICENSE').read_bytes()
    report={'iso_sha256':sha(iso),'iso_bytes':iso.stat().st_size,'standalone':True,
        'bios_uefi_gpt':True,'all_embedded_helpers_verified':True,
        'non_ubuntu_paths_unchanged':True,'visible_password_confirmation':True,
        'credentials_absent_from_kernel_arguments':True,
        'embedded_public_root_certificates':len(list((source/'config/ubuntu-live-certs').glob('*.pem'))),
        'bios_loader_sha256':sha(d/'boot/ipxe.lkrn'),'efi_loader_sha256':sha(efi)}
    (root/'tests').mkdir(exist_ok=True)
    (root/'tests/iso-verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
