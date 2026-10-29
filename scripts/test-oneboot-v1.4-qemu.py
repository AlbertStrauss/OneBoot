#!/usr/bin/env python3
"""Final-ISO UI and disposable two-disk installation qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import socket
import subprocess
import tempfile
import time

BASE=runpy.run_path(str(Path(__file__).with_name('test-qemu-boot.py')))
qmp=BASE['qmp_command']
KEYS={'.':'dot','/':'slash','\n':'ret',' ':'spc','-':'minus','_':'shift-minus',
 ':':'shift-semicolon',';':'semicolon','!':'shift-1','@':'shift-2','#':'shift-3',
 '$':'shift-4','%':'shift-5','^':'shift-6','&':'shift-7','*':'shift-8','(':'shift-9',')':'shift-0',
 '+':'shift-equal','=':'equal',"'":'apostrophe','"':'shift-apostrophe','\\':'backslash','|':'shift-backslash'}
def key(c,k):
    result=qmp(c,'human-monitor-command',{'command-line':'sendkey '+k})
    assert 'error' not in result,result
    time.sleep(.13)
def type_text(c,text):
    for ch in text:key(c,KEYS.get(ch,('shift-'+ch.lower()) if ch.isupper() else ch))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def screen(c,path):qmp(c,'screendump',{'filename':str(path)})
def header(p):
    magic,size,maximum,data=p.read_bytes().split(b'\n',3)
    width,height=map(int,size.split())
    return size,data[:width*min(height,160)*3]
def sparse_signature(p):
    if os.name=='nt':
        from oneboot_test_windows import sparse_signature as signature
        return signature(p)
    spans=[]
    with p.open('rb') as f:
        pos=0;size=p.stat().st_size
        while pos<size:
            try:start=os.lseek(f.fileno(),pos,os.SEEK_DATA)
            except OSError:break
            end=os.lseek(f.fileno(),start,os.SEEK_HOLE)
            f.seek(start);spans.append((start,end-start,hashlib.sha256(f.read(end-start)).hexdigest()));pos=end
    return {'bytes':size,'spans':spans}

class VM:
    def __init__(self,root,case,firmware,memory,iso=None,disks=False):
        self.root=root;self.case=case;self.firmware=firmware;self.memory=memory;self.iso=iso;self.disks=disks
    def __enter__(self):
        if os.name=='nt':
            from oneboot_test_windows import WindowsVM
            acceleration=os.environ.get('ONEBOOT_TEST_UEFI_ACCEL') if self.firmware=='uefi' else None
            assert acceleration in (None,'whpx,kernel-irqchip=off','tcg,thread=multi','tcg,thread=single')
            self.impl=WindowsVM(self.root,self.case,self.firmware,self.memory,self.iso,self.disks,acceleration=acceleration)
            return self.impl.__enter__()
        self.control=tempfile.TemporaryDirectory(prefix='ob14-qmp-')
        self.sock=Path(self.control.name)/'qmp'
        self.memory_file=self.case/'guest-memory'
        port=socket.socket();port.bind(('127.0.0.1',0));self.port=port.getsockname()[1];port.close()
        cmd=['qemu-system-x86_64','-machine','q35' if self.firmware=='uefi' else 'pc',
             '-enable-kvm','-cpu','host','-m',str(self.memory),'-boot','order=d' if self.iso else 'order=c',
             '-netdev',f'user,id=n,hostfwd=tcp:127.0.0.1:{self.port}-:22',
             '-device','virtio-net-pci,netdev=n,mac=52:54:00:12:34:56',
             '-device','virtio-rng-pci','-display','none','-serial','file:'+str(self.case/('installer.serial' if self.iso else 'firstboot.serial')),
             '-qmp','unix:'+str(self.sock)+',server=on,wait=off','-no-reboot']
        if self.iso:cmd+=['-cdrom',str(self.iso)]
        if self.memory>2048:
            cmd+=['-object',f'memory-backend-file,id=mem,size={self.memory}M,mem-path={self.memory_file},share=on','-numa','node,memdev=mem']
        if self.firmware=='uefi':
            variables=self.case/'OVMF_VARS.fd'
            if not variables.exists():shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd',variables)
            cmd+=['-drive','if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
                  '-drive','if=pflash,format=raw,file='+str(variables)]
        if self.disks:
            cmd+=['-drive','if=virtio,format=qcow2,file='+str(self.case/'target.qcow2'),
                  '-drive','if=virtio,format=raw,file='+str(self.case/'other.raw')]
        self.stderr=(self.case/('qemu-install.log' if self.iso else 'qemu-firstboot.log')).open('w')
        self.p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=self.stderr)
        deadline=time.monotonic()+30
        while not self.sock.exists():
            if self.p.poll() is not None:raise RuntimeError('QEMU exited before QMP')
            if time.monotonic()>deadline:raise TimeoutError('QMP socket')
            time.sleep(.1)
        self.c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.c.settimeout(30);self.c.connect(str(self.sock))
        self.c.recv(8192);qmp(self.c,'qmp_capabilities')
        return self
    def __exit__(self,*args):
        if hasattr(self,'impl'):return self.impl.__exit__(*args)
        if self.p.poll() is None:
            try:qmp(self.c,'quit')
            except Exception:self.p.terminate()
        try:self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
        self.c.close();self.stderr.close();self.control.cleanup();self.memory_file.unlink(missing_ok=True)

def reach_version(vm,version):
    reference=vm.root/'reference.ppm'
    expected=header(reference)
    deadline=time.monotonic()+150
    capture=vm.case/'startup.ppm'
    while time.monotonic()<deadline:
        screen(vm.c,capture)
        if header(capture)==expected:break
        time.sleep(2)
    else:raise TimeoutError('OneBoot startup header')
    type_text(vm.c,'0');time.sleep(1)
    type_text(vm.c,'10.0.2.15/24\n');key(vm.c,'ctrl-u');type_text(vm.c,'10.0.2.2\n')
    key(vm.c,'ctrl-u');type_text(vm.c,'10.0.2.3\n');time.sleep(1)
    type_text(vm.c,'c');time.sleep(.6);type_text(vm.c,'u');time.sleep(.6)
    type_text(vm.c,{'18':'5','20':'4','22':'3','24':'2','26':'1'}[version]);time.sleep(.7)

def profile(vm,hostname,password,confirm):
    type_text(vm.c,'a');time.sleep(.5)
    type_text(vm.c,hostname+'\n'+password+'\n'+confirm)

def ssh_check(vm,password,hostname,version):
    if os.name=='nt':
        from oneboot_test_windows import ssh_check as check
        result=check(vm,password,hostname,version)
        import paramiko
        client=paramiko.SSHClient();client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect('127.0.0.1',port=vm.port,username='root',password=password,look_for_keys=False,allow_agent=False,timeout=10)
        _,out,err=client.exec_command('set -e; getent ahostsv4 archive.ubuntu.com; systemctl is-active ssh systemd-networkd',timeout=30)
        output=out.read().decode();error=err.read().decode()
        status=out.channel.recv_exit_status();client.close()
        assert status==0,error+output
        (vm.case/'installed-dns-services.txt').write_text(output,encoding='utf-8')
        result['dns_resolution']=True;result['ssh_network_services_active']=True
        return result
    askpass=vm.case/'askpass'
    askpass.write_text('#!/bin/sh\nprintf "%s\\n" "$ONEBOOT_TEST_PASSWORD"\n');askpass.chmod(0o700)
    env=dict(os.environ,SSH_ASKPASS=str(askpass),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0',ONEBOOT_TEST_PASSWORD=password)
    opts=['ssh','-p',str(vm.port),'-o','ConnectTimeout=5','-o','PreferredAuthentications=password',
        '-o','PubkeyAuthentication=no','-o','NumberOfPasswordPrompts=1',
        '-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(vm.case/'guest-known-hosts')]
    command='hostname; . /etc/os-release; echo "$VERSION_ID"; id -u; ip -4 -o addr show; ip -4 route show; findmnt -n -o SOURCE /; lsblk -nr -o NAME,FSTYPE,MOUNTPOINT; echo APT_ACTIVE; grep -hE "^(deb |Suites:)" /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true'
    deadline=time.monotonic()+360;r=None
    while time.monotonic()<deadline:
        r=subprocess.run(opts+['root@127.0.0.1',command],env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20)
        if r.returncode==0:break
        time.sleep(5)
    assert r and r.returncode==0,(r.stderr if r else 'no SSH result')
    lines=r.stdout.splitlines()
    assert lines[0]==hostname,lines
    assert lines[1].startswith(version+'.04'),lines
    assert lines[2]=='0',lines
    assert '10.0.2.15/24' in r.stdout and 'default via 10.0.2.2' in r.stdout,r.stdout
    assert '/dev/vda' in r.stdout,r.stdout
    assert re.search(r'(^deb .* \S+-security\s|^Suites:.*\S+-security\b)',r.stdout,re.M),r.stdout
    user=subprocess.run(opts+['user@127.0.0.1','id -un; id -Gn'],env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20)
    assert user.returncode==0 and 'sudo' in user.stdout,user.stderr+user.stdout
    (vm.case/'installed-system.txt').write_text(r.stdout+'\nUser login:\n'+user.stdout)
    return {'root_password_login':True,'user_password_login':True,'static_network':True,'hostname':hostname,'version':lines[1]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--firmware',choices=('bios','uefi'),required=True)
    parser.add_argument('--version',choices=('18','20','22','24','26'),default='24')
    parser.add_argument('--mode',choices=('mode','visible','review','mismatch','empty','manual','auto'),required=True)
    parser.add_argument('--iso',type=Path)
    parser.add_argument('--case-tag',default='')
    args=parser.parse_args();root=args.root.resolve()
    if os.name=='nt':assert root==Path('C:/Projects/_analysis/oneboot14-local-tests').resolve()
    else:assert root.parent==Path('/srv/oneboot/staging') and root.name.startswith('oneboot-v1.4-autoinstall-')
    name=args.firmware+'-ubuntu'+args.version+'-'+args.mode
    assert re.fullmatch(r'[a-zA-Z0-9_-]{0,32}',args.case_tag)
    if args.case_tag:name+='-'+args.case_tag
    case=root/'tests'/name;case.mkdir(parents=True,exist_ok=True)
    iso=root/'oneboot-v1.4.iso' if os.name=='nt' else root/'releases/v1.4/oneboot-v1.4.iso'
    if args.iso:
        iso=args.iso.resolve();assert iso.parent==root and iso.suffix=='.iso'
    record={'iso_sha256':sha(iso),'firmware':args.firmware,'version':args.version,'mode':args.mode,'pass':False,
            'guest_disk_files':[] if args.mode not in ('manual','auto') else ['target.qcow2','other.raw']}
    password='OneBootTest1!';hostname='ob14-'+args.version+'-'+args.firmware
    full=args.mode in ('manual','auto')
    if full:
        assert not (case/'target.qcow2').exists(),'Keep earlier failed disks for inspection; choose a fresh case'
        image_tool='C:/Projects/.tools/qemu-portable/qemu-img.exe' if os.name=='nt' else 'qemu-img'
        subprocess.run([image_tool,'create','-f','qcow2',str(case/'target.qcow2'),'24G'],check=True,stdout=subprocess.DEVNULL)
        other=case/'other.raw'
        with other.open('wb') as f:
            if os.name=='nt':
                from oneboot_test_windows import make_sparse,resize_sparse
                make_sparse(f)
                resize_sparse(f,64*1024**3)
            else:f.truncate(64*1024**3)
            f.seek(32768);f.write(b'ONEBOOT-SECOND-DISK-DO-NOT-TOUCH'*100)
            f.seek(64*1024**3-8192);f.write(b'ONEBOOT-SENTINEL-END'*100)
        before=sparse_signature(other);record['other_disk_before']=before
    memory=((4096 if args.version in ('18','20') else 8192) if os.name=='nt' else 5120) if full else 1024
    try:
        with VM(root,case,args.firmware,memory,iso,full) as vm:
            reach_version(vm,args.version)
            screen(vm.c,case/'mode.ppm')
            if args.mode not in ('mode','manual'):
                profile(vm,hostname,'' if args.mode=='empty' else password,
                    'Different1!' if args.mode=='mismatch' else '' if args.mode=='empty' else password)
                screen(vm.c,case/'visible-password.ppm')
                if args.mode!='visible':
                    type_text(vm.c,'\n');time.sleep(1);screen(vm.c,case/'profile-result.ppm')
            if args.mode=='auto':type_text(vm.c,'g')
            elif args.mode=='manual':type_text(vm.c,'m')
            if full:
                deadline=time.monotonic()+(5400 if os.name=='nt' and args.firmware=='bios' else 1800);checkpoint=0
                start=time.monotonic()
                while vm.p.poll() is None and time.monotonic()<deadline:
                    time.sleep(15)
                    if vm.p.poll() is not None:break
                    if hasattr(vm,'handle_requests'):vm.handle_requests()
                    deadline+=getattr(vm,'observation_extension',0)
                    vm.observation_extension=0
                    screen(vm.c,case/f'progress-{checkpoint:03}.ppm');checkpoint+=1
                    print('PROGRESS '+name+' '+str(checkpoint),flush=True)
                    if (case/'stop-observation').exists():break
                    serial=(case/'installer.serial').read_text(errors='replace')
                    if 'Kernel panic - not syncing:' in serial:raise RuntimeError(serial[-3500:])
                    if 'INSTALL FAILED' in serial:raise RuntimeError(serial[-2500:])
                    if 'An error occurred. Press enter to start a shell' in serial:raise RuntimeError(serial[-3500:])
                    if time.monotonic()-start>300 and 'Linux version' not in serial:
                        raise RuntimeError('Linux did not start; inspect the final iPXE transfer screen')
                if args.mode=='auto':
                    assert vm.p.poll() is not None,'Installer did not reboot within observation window'
                    assert vm.p.returncode==0,'QEMU exited abnormally: '+str(vm.p.returncode)
                    record['installer_exit_code']=vm.p.returncode
                else:screen(vm.c,case/'manual-installer.ppm')
            record['menu_capture_completed']=True
        if args.mode=='auto':
            with VM(root,case,args.firmware,1536,None,True) as vm:
                record['installed']=ssh_check(vm,password,hostname,args.version)
                screen(vm.c,case/'firstboot.ppm')
        if full:
            after=sparse_signature(case/'other.raw');record['other_disk_after']=after
            assert before==after,'Secondary disk changed'
            record['second_disk_unchanged']=True
            if args.mode=='manual':
                extents=json.loads(subprocess.check_output([image_tool,'map','--output=json',str(case/'target.qcow2')],text=True))
                assert all(not extent.get('data') for extent in extents),'Manual installer wrote guest disk sectors'
                record['manual_target_unwritten']=True
            (case/'target.qcow2').unlink();(case/'other.raw').unlink()
        record['pass']=True
        assistance=case/'startup-assistance.json'
        if assistance.exists():
            record['startup_assistance']=json.loads(assistance.read_text())
            record['unattended_startup_pass']=False
        elif args.mode=='auto':record['unattended_startup_pass']=True
    except Exception as error:
        record['error']=str(error)
        raise
    finally:
        if full and (case/'other.raw').exists():
            after=sparse_signature(case/'other.raw');record['other_disk_after']=after
            record['second_disk_unchanged']=before==after
        (case/'result.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
