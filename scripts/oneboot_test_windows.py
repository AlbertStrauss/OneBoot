"""Windows backend for the disposable OneBoot qualification VMs.

Uses only project files and loopback ports; no physical disks, adapters, or
Windows settings are changed. QEMU is the checksum-verified portable build.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import msvcrt
import os
from pathlib import Path
import re
import runpy
import shutil
import socket
import subprocess
import sys
import threading
import time

QEMU=Path('C:/Projects/.tools/qemu-portable')
sys.path.insert(0,'C:/Projects/.tools/oneboot-test-python')
qmp=runpy.run_path(str(Path(__file__).with_name('test-qemu-boot.py')))['qmp_command']

def ioctl(f,code,source=None,outsize=0):
    call=ctypes.WinDLL('kernel32',use_last_error=True).DeviceIoControl
    call.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,
                   wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.LPVOID]
    call.restype=wintypes.BOOL
    source=ctypes.create_string_buffer(source) if source else None
    output=ctypes.create_string_buffer(outsize) if outsize else None
    count=wintypes.DWORD()
    if not call(msvcrt.get_osfhandle(f.fileno()),code,source,len(source)-1 if source else 0,
                output,outsize,ctypes.byref(count),None):raise ctypes.WinError(ctypes.get_last_error())
    return output.raw[:count.value] if output else b''

def make_sparse(f):ioctl(f,0x900c4)

def resize_sparse(f,size):
    # The Windows CRT _chsize_s used by file.truncate writes zeroes across
    # the extension. SetEndOfFile preserves the NTFS sparse allocation.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetFilePointerEx.argtypes=[wintypes.HANDLE,ctypes.c_longlong,wintypes.LPVOID,wintypes.DWORD]
    kernel.SetEndOfFile.argtypes=[wintypes.HANDLE]
    handle=msvcrt.get_osfhandle(f.fileno())
    if not kernel.SetFilePointerEx(handle,size,None,0) or not kernel.SetEndOfFile(handle):
        raise ctypes.WinError(ctypes.get_last_error())
    f.seek(0)

def sparse_signature(p):
    import struct
    spans=[];size=p.stat().st_size
    with p.open('rb') as f:
        allocated=ioctl(f,0x940cf,struct.pack('<qq',0,size),65536)
        for start,length in struct.iter_unpack('<qq',allocated):
            f.seek(start)
            digest=hashlib.sha256(f.read(length)).hexdigest() if length<256*1024**2 else 'unexpected-large-extent'
            spans.append((start,length,digest))
    return {'bytes':size,'spans':spans}

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class WindowsVM:
    def __init__(self,root,case,firmware,memory,iso=None,disks=False,acceleration=None,nic='virtio-net-pci'):
        self.root=root;self.case=case;self.firmware=firmware;self.memory=memory;self.iso=iso;self.disks=disks
        self.acceleration=acceleration;self.nic=nic
        self.cpu='max'
        self.machine='q35' if firmware=='uefi' else os.environ.get('ONEBOOT_TEST_BIOS_MACHINE','pc')
        assert self.machine in ('pc','q35')
        self.hpet='on' if firmware=='uefi' else os.environ.get('ONEBOOT_TEST_BIOS_HPET','on')
        assert self.hpet in ('on','off')
        self.icount=os.environ.get('ONEBOOT_TEST_TCG_ICOUNT','') if firmware=='bios' else ''
        assert self.icount in ('','auto')
        self.tcg_thread='single' if self.icount else os.environ.get('ONEBOOT_TEST_TCG_THREAD','multi')
        assert self.tcg_thread in ('single','multi')
    def __enter__(self):
        self.port=port();self.qmp_port=port();self.serial_port=port()
        assert len({self.port,self.qmp_port,self.serial_port})==3
        cmd=[str(QEMU/'qemu-system-x86_64.exe'),'-L',str(QEMU/'share'),
             '-machine',self.machine+',hpet='+self.hpet,'-accel',
             self.acceleration or ('whpx,kernel-irqchip=off' if self.firmware=='uefi' else 'tcg,thread='+self.tcg_thread),
             '-cpu',self.cpu,'-smp','2','-m',str(self.memory),'-boot','order=d' if self.iso else 'order=c',
             '-netdev',f'user,id=n,hostfwd=tcp:127.0.0.1:{self.port}-:22',
             '-device',self.nic+',netdev=n,mac=52:54:00:12:34:56','-device','virtio-rng-pci',
             '-display','none','-chardev',f'socket,id=ser,host=127.0.0.1,port={self.serial_port},server=on,wait=off',
             '-serial','chardev:ser','-qmp',f'tcp:127.0.0.1:{self.qmp_port},server=on,wait=off','-no-reboot']
        if self.icount:cmd+=['-icount','shift='+self.icount+',align=off,sleep=on']
        if self.iso:cmd+=['-cdrom',str(self.iso)]
        if self.firmware=='uefi':
            variables=self.case/'OVMF_VARS.fd'
            if not variables.exists():shutil.copyfile(self.root/'firmware/OVMF_VARS_4M.fd',variables)
            cmd+=['-drive','if=pflash,format=raw,readonly=on,file='+str(self.root/'firmware/OVMF_CODE_4M.fd'),
                  '-drive','if=pflash,format=raw,file='+str(variables)]
        if self.disks:cmd+=['-drive','if=virtio,format=qcow2,file='+str(self.case/'target.qcow2'),
                            '-drive','if=virtio,format=raw,file='+str(self.case/'other.raw')]
        self.stderr=(self.case/('qemu-install.log' if self.iso else 'qemu-firstboot.log')).open('w')
        self.p=subprocess.Popen(cmd,stdout=self.stderr,stderr=self.stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+30
        while True:
            if self.p.poll() is not None:
                self.stderr.close();raise RuntimeError('QEMU exited: '+(self.case/('qemu-install.log' if self.iso else 'qemu-firstboot.log')).read_text())
            try:self.c=socket.create_connection(('127.0.0.1',self.qmp_port),timeout=2);break
            except OSError:
                if time.monotonic()>deadline:self.p.terminate();raise TimeoutError('QMP TCP')
                time.sleep(.2)
        self.c.settimeout(30);self.c.recv(8192);qmp(self.c,'qmp_capabilities')
        self.serial=socket.create_connection(('127.0.0.1',self.serial_port),timeout=5);self.serial.settimeout(1)
        self.serial_log=(self.case/('installer.serial' if self.iso else 'firstboot.serial')).open('wb',buffering=0)
        self.closing=False
        self.reader=threading.Thread(target=self.read_serial,daemon=True);self.reader.start()
        metadata={'pid':self.p.pid,'qmp_port':self.qmp_port,'serial_port':self.serial_port,'ssh_port':self.port,
            'cpu':self.cpu,'memory_mb':self.memory,'firmware':self.firmware,'network_model':self.nic,'machine':self.machine,
            'hpet':self.hpet,'icount':self.icount,'qemu_command':cmd}
        (self.case/'control.json').write_text(json.dumps(metadata))
        (self.case/('control-install.json' if self.iso else 'control-firstboot.json')).write_text(json.dumps(metadata))
        return self
    def read_serial(self):
        while not self.closing:
            try:
                data=self.serial.recv(65536)
                if not data:break
                self.serial_log.write(data)
            except TimeoutError:pass
            except OSError:break
    def handle_requests(self):
        request=self.case/'diagnostic-request.json'
        if not request.exists():return
        data=json.loads(request.read_text());request.unlink()
        if 'extend_seconds' in data:
            seconds=int(data['extend_seconds']);assert 0<seconds<=3600
            self.observation_extension=seconds
            with (self.case/'observation-extensions.jsonl').open('a') as log:
                log.write(json.dumps({'seconds':seconds,'time':time.time()})+'\n')
        if 'serial' in data:self.serial.sendall(data['serial'].encode())
        for keys in data.get('keys',[]):qmp(self.c,'human-monitor-command',{'command-line':'sendkey '+keys})
        if data.get('screenshot'):qmp(self.c,'screendump',{'filename':str(self.case/Path(data['screenshot']).name)})
    def __exit__(self,*args):
        if self.p.poll() is None:
            try:qmp(self.c,'quit')
            except Exception:self.p.terminate()
        try:self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
        self.closing=True;self.serial.close();self.reader.join(timeout=3)
        self.serial_log.close();self.c.close();self.stderr.close()

def ssh_check(vm,password,hostname,version):
    import paramiko
    transport_log=logging.getLogger('paramiko.transport')
    transport_log.addHandler(logging.NullHandler());transport_log.propagate=False
    def connect(username):
        client=paramiko.SSHClient();client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect('127.0.0.1',port=vm.port,username=username,password=password,
                           allow_agent=False,look_for_keys=False,timeout=5,auth_timeout=10,banner_timeout=10)
            return client
        except Exception:client.close();raise
    deadline=time.monotonic()+360;last=None
    while time.monotonic()<deadline:
        try:root=connect('root');break
        except Exception as error:last=error;time.sleep(5)
    else:raise RuntimeError('First-boot SSH failed: '+str(last))
    command='hostname; . /etc/os-release; echo "$VERSION_ID"; id -u; ip -4 -o addr show; ip -4 route show; findmnt -n -o SOURCE /; lsblk -nr -o NAME,FSTYPE,MOUNTPOINT; echo APT_ACTIVE; grep -hE "^(deb |Suites:)" /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true; echo APT_CONFIG_CHECK; apt-get --print-uris update >/dev/null'
    _,stdout,stderr=root.exec_command(command,timeout=30);output=stdout.read().decode();error=stderr.read().decode()
    assert stdout.channel.recv_exit_status()==0,error
    root.close();lines=output.splitlines()
    assert lines[0]==hostname and lines[1].startswith(version+'.04') and lines[2]=='0',output
    assert '10.0.2.15/24' in output and 'default via 10.0.2.2' in output and '/dev/vda' in output,output
    assert any(line.startswith('default via 10.0.2.2 ') and 'proto static' in line
               for line in lines),output
    assert re.search(r'(^deb .* \S+-security\s|^Suites:.*\S+-security\b)',output,re.M),output
    user=connect('user');_,stdout,stderr=user.exec_command('id -un; id -Gn',timeout=20)
    account=stdout.read().decode();error=stderr.read().decode()
    assert stdout.channel.recv_exit_status()==0 and 'sudo' in account,error+account
    user.close();(vm.case/'installed-system.txt').write_text(output+'\nUser login:\n'+account)
    return {'root_password_login':True,'user_password_login':True,'static_network':True,'hostname':hostname,'version':lines[1],'apt_configuration_valid':True}
