#!/usr/bin/env python3
"""Build deterministic auto-only d-i initrds from pinned Canonical inputs."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

SOURCE=Path(__file__).resolve().parents[1]
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(path,expected):
    if sha(path)!=expected:raise ValueError('SHA256 mismatch: '+str(path))
def newc(files):
    out=bytearray()
    for i,(name,data,mode) in enumerate(files+[('TRAILER!!!',b'',0)],1):
        fields=(i,mode,0,0,1,0,len(data),0,0,0,0,len(name)+1,0)
        out+=('070701'+''.join(f'{x:08x}' for x in fields)).encode()
        out+=name.encode()+b'\0';out+=b'\0'*(-len(out)%4)
        out+=data;out+=b'\0'*(-len(out)%4)
    return bytes(out)
def download(url,path):
    if not url.startswith('https://'):raise ValueError('HTTPS source required')
    with urllib.request.urlopen(url,timeout=90) as r,path.open('wb') as f:
        if not r.url.startswith('https://'):raise ValueError('insecure redirect')
        shutil.copyfileobj(r,f)
def kernel_abi(initrd):
    data=gzip.decompress(initrd.read_bytes());position=0;abis=set()
    while data[position:position+6]==b'070701':
        fields=[int(data[position+6+i*8:position+14+i*8],16) for i in range(13)]
        start=position+110;name=data[start:start+fields[11]-1].decode()
        match=re.match(r'(?:\./)?lib/modules/([^/]+)(?:/|$)',name)
        if match:abis.add(match[1])
        start=(start+fields[11]+3)&~3;position=(start+fields[6]+3)&~3
        if name=='TRAILER!!!':break
    if len(abis)!=1:raise ValueError('Cannot determine unique vendor kernel ABI: '+repr(abis))
    return abis.pop()
def build(inputs,output,module,fetch):
    config=json.loads((SOURCE/'config/ubuntu-legacy-autoinstall.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True,exist_ok=True);records=[]
    for v in config['versions']:
        directory=inputs/v['version'];directory.mkdir(parents=True,exist_ok=True)
        for name,key in (('linux','kernel_sha256'),('initrd.gz','initrd_sha256')):
            p=directory/name
            if fetch and not p.exists():download(v['origin']+'/'+name,p)
            verify(p,v[key])
        abi=kernel_abi(directory/'initrd.gz')
        if abi!=v['kernel_abi']:raise ValueError('Vendor initrd ABI drift: '+abi)
        files=[(name,(SOURCE/'autoinstall'/source).read_bytes(),mode) for name,source,mode in
               [('preseed.cfg','oneboot-di-preseed.cfg',0o100644),
                ('oneboot-di','oneboot-di',0o100700),('oneboot-disk','oneboot-disk',0o100755)]]
        if 'module_kernel' in v:
            if v['module_kernel']!=abi:raise ValueError('Supplementary module ABI does not match vendor initrd')
            mod=module
            if mod is None:
                deb=inputs/('linux-modules-'+abi+'.deb')
                if fetch and not deb.exists():download(v['module_deb_url'],deb)
                verify(deb,v['module_deb_sha256'])
                with tempfile.TemporaryDirectory(prefix='ob14-module-') as tmp:
                    d=Path(tmp)
                    subprocess.run(['dpkg-deb','-x',str(deb),str(d/'unpacked')],check=True)
                    mod=d/'unpacked/lib/modules'/v['module_kernel']/'kernel/drivers/block/virtio_blk.ko'
                    verify(mod,v['module_sha256']);data=mod.read_bytes()
            else:
                verify(mod,v['module_sha256']);data=mod.read_bytes()
            if b'vermagic='+abi.encode()+b' ' not in data:
                raise ValueError('Supplementary module ELF vermagic differs from vendor kernel ABI')
            files.append(('oneboot-virtio_blk.ko',data,0o100644))
        kernel=output/('ubuntu-'+v['version']+'-vmlinuz')
        initrd=output/('ubuntu-'+v['version']+'-auto-initrd')
        shutil.copyfile(directory/'linux',kernel)
        # Legacy kernels require [plain cpio][original gzip], never the reverse.
        initrd.write_bytes(newc(files)+(directory/'initrd.gz').read_bytes())
        records.append(dict(v,auto_initrd_sha256=sha(initrd),kernel_file=kernel.name,
                            auto_initrd_file=initrd.name,private_credentials_in_asset=False,
                            embedded_files={n:hashlib.sha256(b).hexdigest() for n,b,m in files}))
    (output/'SOURCE-INFO.json').write_text(json.dumps({'license':'GPL-2.0-or-later for OneBoot hooks; upstream Canonical kernel/initrd retained',
        'versions':records,'credential_transport':'private cpio prefix added in RAM by obprofile prepend'},indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.name!='SHA256SUMS'),encoding='ascii')
    print(json.dumps(records,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--module',type=Path)
    p.add_argument('--download',action='store_true');a=p.parse_args()
    build(a.input_root.resolve(),a.output.resolve(),a.module.resolve() if a.module else None,a.download)
