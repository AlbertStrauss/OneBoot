#!/usr/bin/env python3
"""Build the small Ubuntu autoinstall candidate in its own staging directory."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

source=Path(__file__).resolve().parents[1]
root=Path(os.environ['ONEBOOT_PROJECT_ROOT']).resolve()
assert root.name.startswith('oneboot-v1.3-autoinstall-') and root.parent==Path('/srv/oneboot/staging')
for name in ('prepare-oneboot-v1.3-autoinstall.py','prepare-oneboot-v1.3-menu.py'):
    subprocess.run(['python3',str(source/'scripts'/name)],check=True)
ipxe=root/'toolchain/ipxe'
shutil.copyfile(source/'ipxe/oneboot_ubuntu_cmd.c',ipxe/'src/hci/commands/oneboot_ubuntu_cmd.c')
local=ipxe/'src/config/local'
local.mkdir(exist_ok=True)
shutil.copyfile(source/'config/ipxe-usb-v1.3.h',local/'usb.h')
root_names=('ISRG_Root_X1','ISRG_Root_X2','DigiCert_Global_Root_CA','DigiCert_Global_Root_G2',
    'USERTrust_RSA_Certification_Authority','USERTrust_ECC_Certification_Authority',
    'Sectigo_Public_Server_Authentication_Root_R46','Sectigo_Public_Server_Authentication_Root_E46',
    'Amazon_Root_CA_1','Amazon_Root_CA_2','Amazon_Root_CA_3','Amazon_Root_CA_4',
    'Starfield_Services_Root_Certificate_Authority_-_G2','GlobalSign_Root_CA')
certs=[Path('/etc/ssl/certs')/(name+'.pem') for name in root_names]
assert all((Path('/etc/ssl/certs')/(name+'.pem')).exists() for name in
    ('ISRG_Root_X1','DigiCert_Global_Root_G2','USERTrust_RSA_Certification_Authority',
     'Sectigo_Public_Server_Authentication_Root_R46'))
trust=source/'config/ubuntu-live-ca.crt'
trust.write_bytes(b''.join(p.read_bytes() for p in certs if p.exists()))
cert_dir=source/'config/ubuntu-live-certs';cert_dir.mkdir(exist_ok=True)
certificate_files=[]
for p in certs:
    if p.exists():
        target=cert_dir/p.name;target.write_bytes(p.read_bytes());certificate_files.append(str(target))
# iPXE's build helpers process one certificate per input file. A concatenated
# PEM bundle would silently contribute only its first root.
trust_list=','.join(certificate_files)

# Cache only immutable baseline assets. Changes to any asset's inode, size or
# modification time, any pinned manifest, or any baseline verifier invalidate it.
records=[]
for p in sorted((root/'assets').rglob('*')):
    if p.is_file():
        st=p.stat();records.append((str(p.relative_to(root/'assets')),st.st_ino,st.st_size,st.st_mtime_ns))
baseline_scripts=('build-oneboot-v1.0-vps.sh','verify-oneboot-v1.0-scope.py',
    'verify-oneboot-download-diagnostics.py','verify-proxmox-initrds-vps.sh','prepare-proxmox-bootstrap.py')
for p in sorted((source/'config').glob('*.sha256'))+[source/'scripts'/n for n in baseline_scripts]:
    records.append((str(p.relative_to(source)),hashlib.sha256(p.read_bytes()).hexdigest()))
signature=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
memo=root/'baseline-assets-verified.json'
reuse=memo.exists() and json.loads(memo.read_text()).get('signature')==signature

script=(source/'scripts/build-oneboot-v1.0-vps.sh').read_text()
script=script.replace('readonly RELEASE_VERSION="1.0"','readonly RELEASE_VERSION="1.3"',1)
script=script.replace('${SOURCE_ROOT}/src/oneboot-v1.0.ipxe.in','${SOURCE_ROOT}/src/oneboot-v1.3.ipxe.in')
script=script.replace('cleanup() {','''cleanup() {
  if [[ -f "${work_dir}/efi_console.c.original" ]]; then
    install -m 0644 "${work_dir}/efi_console.c.original" "${IPXE_ROOT}/src/interface/efi/efi_console.c"
  fi''',1)
script=script.replace('ipxe_config_patched=1\n','''ipxe_config_patched=1
sed -i '/^PROVIDE_REQUIRING_SYMBOL();$/a REQUIRE_OBJECT ( oneboot_ubuntu_cmd );' "${ipxe_config_source}"
install -m 0644 "${IPXE_ROOT}/src/interface/efi/efi_console.c" "${work_dir}/efi_console.c.original"
patch -d "${IPXE_ROOT}" -p1 --fuzz=0 < "${SOURCE_ROOT}/vendor/fluxbilling/src/efi-console-ilo4.patch"
''',1)
helpers=','.join('${SOURCE_ROOT}/autoinstall/'+n for n in
    ('99onebootseed','param.conf','oneboot-mirror-pick','oneboot-disk','oneboot-set-password'))
script=script.replace('readonly embedded_files="${embedded_script},${SOURCE_ROOT}/assets/oneboot-background-v1.0.png"',
    'readonly embedded_files="${embedded_script},${SOURCE_ROOT}/assets/oneboot-background-v1.0.png,'+helpers+'"')
script=script.replace('bin/ipxe.lkrn','bin-x86_64-pcbios/ipxe.lkrn')
script=script.replace('EMBED="${embedded_files}"','EMBED="${embedded_files}" CERT="'+trust_list+'" TRUST="'+trust_list+'"')
script=script.replace('-V ONEBOOT_1_0','-V ONEBOOT_1_3')
script=script.replace('OneBoot 1.0\n\nStatus:','OneBoot 1.3\n\nStatus:')
script=script.replace('No installer in this ISO receives an unattended disk policy.',
    'Ubuntu 22/24/26 offer optional autoinstall after explicit Go; only the first eligible disk is selected. Other installers remain interactive.')
script=script.replace('Safety: interactive Ubuntu, AlmaLinux, Debian and Proxmox installers plus recovery tools; no disk automation.',
    'Safety: Ubuntu 22/24/26 support optional first-disk autoinstall after confirmation; other OS paths remain interactive.')
script=script.replace('install -m 0644 "${embedded_script}" "${iso_root}/oneboot.ipxe"',
'''install -m 0644 "${embedded_script}" "${iso_root}/oneboot.ipxe"
install -m 0644 "${SOURCE_ROOT}/vendor/fluxbilling/LICENSE" "${iso_root}/COPYING-FLUXBILLING.txt"
install -m 0644 "${SOURCE_ROOT}/NOTICE-FLUXBILLING.md" "${iso_root}/NOTICE-FLUXBILLING.md"
install -m 0644 "${SOURCE_ROOT}/config/ubuntu-autoinstall.json" "${iso_root}/ubuntu-autoinstall.json"''')
if reuse:
    start=script.index('echo "Verifying pinned Proxmox assets..."')
    end=script.index('background_sha256=',start)
    script=script[:start]+'echo "Reusing verified unchanged baseline assets (inode/size/mtime/manifests checked)."\n'+script[end:]
build=source/'scripts/build-oneboot-v1.3-vps.sh'
build.write_text(script)
subprocess.run(['bash',str(build)],check=True)
memo.write_text(json.dumps({'signature':signature,'baseline_assets_verified':True},indent=2))
