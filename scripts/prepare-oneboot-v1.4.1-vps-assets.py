#!/usr/bin/env python3
"""Publish separate legacy helpers; preserve every existing VPS payload byte."""
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source=Path(__file__).resolve().parents[1]
assets=Path('/srv/oneboot/assets/ubuntu')
out=assets/'oneboot-v1.4.1'
assert not (out/'DELIVERED.txt').exists(),'Delivered resources are immutable'
assert not out.exists() or '--refresh-candidate' in sys.argv,'Resource directory already exists'
out.mkdir(mode=0o750,exist_ok=True)
stage=Path(sys.argv[1]).resolve()
assert stage.parent==Path('/srv/oneboot/staging') and stage.name.startswith('oneboot-v1.4.1-autoinstall-')
records=[]
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for version,expected in [('18.04','fdeba3f1f7e6e9eb8b68f7dfd591292d7b77ed682748ec8bd197e13c48e48daf'),('20.04','ab92f6b5755d98cd7928271fde644ea3da3cff1df486eef193613b659f49ff33')]:
    original=Path('/srv/oneboot/staging/oneboot-v1.4-autoinstall-20261029/legacy-boot-r4')/('ubuntu-'+version+'-auto-initrd')
    assert digest(original)==expected
    target=out/'netboot'/version/'auto-initrd';target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(original,target);records.append((expected,target))
for version in ('18.04.6','20.04.6'):
    original=assets/version/'initrd'
    raw=original.read_bytes();offset=0
    while offset<len(raw):
        if raw[offset]==0:offset+=1;continue
        if raw[offset:offset+6] not in (b'070701',b'070702'):break
        h=raw[offset:offset+110];size=int(h[54:62],16);names=int(h[94:102],16)
        offset=(offset+110+names+3)&~3;offset=(offset+size+3)&~3
    assert raw[offset:offset+2]==b'\x1f\x8b'
    with tempfile.TemporaryDirectory(prefix='legacy-full-',dir=stage) as tmp:
        tree=Path(tmp)
        subprocess.run(['cpio','-idmu','--quiet','--no-absolute-filenames'],cwd=tree,input=gzip.decompress(raw[offset:]),check=True)
        script=tree/'scripts/oneboot-legacy-https'
        text=script.read_text();start=text.index('    /opt/oneboot-wget/ld-linux-x86-64.so.2 \\\n')
        end=text.index('    ob_hash=',start)
        text=text[:start]+'''    . /conf/oneboot-mirror-pick
    oneboot_fetch_candidates /run/oneboot-iso/ubuntu.iso.part || return 1
'''+text[end:]
        script.write_text(text)
        shutil.copyfile(source/'autoinstall-v1.4.1/oneboot-mirror-pick',tree/'conf/oneboot-mirror-pick')
        for p in tree.rglob('*'):os.utime(p,(0,0),follow_symlinks=False)
        names=sorted(str(p.relative_to(tree)) for p in tree.rglob('*'))
        cpio=subprocess.run(['cpio','--null','-o','-H','newc','--owner=0:0','--reproducible'],cwd=tree,input=('\0'.join(names)+'\0').encode(),stdout=subprocess.PIPE,check=True).stdout
    target=out/'full'/version/'initrd';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw[:offset]+gzip.compress(cpio,compresslevel=6,mtime=0));records.append((digest(target),target))
manifest=''.join(h+'  ubuntu/'+str(p.relative_to(assets))+'\n' for h,p in records)
(source/'config/ubuntu-vps-policy-assets.sha256').write_text(manifest)
asset_owner=assets.stat().st_uid
asset_group=assets.stat().st_gid
for p in [out]+list(out.rglob('*')):
    # Match the existing asset store's web-readable group, not the private
    # staging/toolchain group. Otherwise Nginx returns 403 for enabled clients.
    os.chown(p,asset_owner,asset_group,follow_symlinks=False)
    if p.is_file():p.chmod(0o440)
    else:p.chmod(0o750)
print(manifest)
