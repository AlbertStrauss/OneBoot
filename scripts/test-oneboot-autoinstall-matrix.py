"""Run/resume the six full disposable-disk qualification cases sequentially."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path('C:/Projects/_analysis/oneboot13-local-tests').resolve()
script=Path(__file__).with_name('test-oneboot-autoinstall-qemu.py')
iso=root/'oneboot-v1.3.iso'
expected=hashlib.sha256(iso.read_bytes()).hexdigest()
cases=[('uefi','24'),('bios','24'),('uefi','22'),('bios','22'),('uefi','26'),('bios','26')]
with (root/'matrix.log').open('a',encoding='utf-8') as log:
    for firmware,version in cases:
        name=firmware+'-ubuntu'+version+'-auto';result=root/'tests'/name/'result.json'
        previous=json.loads(result.read_text()) if result.exists() else {}
        if previous.get('pass') and previous.get('iso_sha256')==expected:
            print('ALREADY QUALIFIED '+name,flush=True);continue
        print('STARTING '+name,flush=True)
        with subprocess.Popen([sys.executable,str(script),'--root',str(root),'--firmware',firmware,
                               '--version',version,'--mode','auto'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               text=True,encoding='utf-8',errors='replace') as process:
            for line in process.stdout:
                print(line,end='',flush=True);log.write(line);log.flush()
            if process.wait()!=0:raise SystemExit('Failed case: '+name)
    records=[json.loads((root/'tests'/(f+'-ubuntu'+v+'-auto')/'result.json').read_text()) for f,v in cases]
    assert all(r['pass'] and r['iso_sha256']==expected and r['second_disk_unchanged']
               and r['installed']['root_password_login'] and r['installed']['user_password_login']
               and r['installed']['static_network'] for r in records)
    assisted=[r['firmware']+'-ubuntu'+r['version']+'-auto' for r in records
              if r.get('startup_assistance') or r.get('unattended_startup_pass') is False]
    (root/'full-install-matrix.json').write_text(json.dumps({'iso_sha256':expected,'pass':True,
      'unattended_startup_pass':not assisted,'assisted_cases':assisted,'cases':records},indent=2))
    print('FUNCTIONAL PASS: six complete installations and cold boots; '+str(6-len(assisted))+
          ' clean unattended startups, '+str(len(assisted))+' assisted startups.',flush=True)
