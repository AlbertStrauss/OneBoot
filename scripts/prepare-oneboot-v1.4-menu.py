#!/usr/bin/env python3
"""Extend the qualified 1.3 menu with opt-in legacy Ubuntu automation."""
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'scripts/prepare-oneboot-v1.3-menu.py')],check=True)
text=(root/'src/oneboot-v1.3.ipxe.in').read_text(encoding='utf-8')
text=text.replace('set oneboot_version 1.3','set oneboot_version 1.4',1)
text=text.replace('Ubuntu 22/24/26: choose Manual or Auto','Ubuntu 18/20/22/24/26: choose Manual or Auto')
for version in ('2204','2404','2604'):
    text=text.replace(':boot_ubuntu_'+version+'\n',':boot_ubuntu_'+version+'\nset ubuntu_backend casper\n',1)
for version,key in (('18.04.6','1804'),('20.04.6','2004')):
    body=f''':boot_ubuntu_{key}_live
set ubuntu_version {version}
set ubuntu_net_version {version[:5]}
set ubuntu_net_suite {'bionic' if key=='1804' else 'focal'}
set ubuntu_name Ubuntu Server {version} LTS
set ubuntu_backend di
set ubuntu_legacy_menu ubuntu_install_mode
goto ubuntu_install_mode
'''
    text,n=re.subn(r'^:boot_ubuntu_'+key+r'_live\n.*?(?=^:)',body,text,count=1,flags=re.M|re.S)
    assert n==1
text=text.replace('menu --name ubuntu_mode ${ubuntu_name} - installation mode',
'''menu --name ubuntu_mode ${ubuntu_name} - installation mode
iseq ${ubuntu_backend} di && item --menu ubuntu_mode --gap -- Auto: classic network installer. Manual: original Full ISO. ||''',1)
text=text.replace(':ubuntu_auto_go\nimgfree\n',':ubuntu_auto_go\nimgfree\niseq ${ubuntu_backend} di && goto ubuntu_di_profile ||\n',1)
text=text.replace('clear ubuntu_auto_args\nimgfree\nobpayload restore',
    'clear ubuntu_auto_args\nimgfree\niseq ${ubuntu_backend} di && goto boot_ubuntu_legacy_live ||\nobpayload restore',1)
legacy=r''':ubuntu_di_profile
obprofile create oneboot_hostname oneboot_password oneboot_confirm || goto ubuntu_profile_invalid
clear oneboot_password
clear oneboot_confirm
set ubuntu_di_base @@BOOT_RELEASE@@
set ob_boot_resource ${ubuntu_di_base}/ubuntu-${ubuntu_net_version}-vmlinuz
echo Starting ${ubuntu_name} automatic classic network installer.
echo Packages download from the official Ubuntu archive. Target: first fixed disk only.
kernel --name kboot ${ob_boot_resource} initrd=initrd.magic BOOTIF=${bootif} netcfg/choose_interface=${nic_mac} netcfg/disable_autoconfig=true netcfg/disable_dhcp=true netcfg/get_ipaddress=${validated_ip} netcfg/get_netmask=${validated_netmask} netcfg/get_gateway=${validated_gateway} netcfg/get_nameservers=${validated_dns} netcfg/confirm_static=true netcfg/get_hostname=${oneboot_hostname} netcfg/hostname=${oneboot_hostname} oneboot.prefix=${input_prefix} oneboot.autoinstall=1 mirror/country=manual mirror/http/hostname=archive.ubuntu.com mirror/http/directory=/ubuntu mirror/http/proxy= mirror/suite=${ubuntu_net_suite} apt-setup/security_host=security.ubuntu.com nomodeset modprobe.blacklist=mgag200 auto=true priority=critical locale=en_US.UTF-8 keyboard-configuration/layoutcode=us console-setup/ask_detect=false console=ttyS0,115200n8 console=tty0 --- || oberror kernel ${ob_boot_resource} ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed
initrd --name iboot ${ubuntu_di_base}/ubuntu-${ubuntu_net_version}-auto-initrd || oberror initrd ${ubuntu_di_base}/ubuntu-${ubuntu_net_version}-auto-initrd ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed
obprofile prepend iboot || goto ubuntu_local_helpers_failed
boot || oberror boot ${ob_boot_resource} ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed

'''.replace('@@BOOT_RELEASE@@',json.loads((root/'config/ubuntu-legacy-autoinstall.json').read_text(encoding='utf-8'))['boot_release'])
text=text.replace(':ubuntu_manual\n',legacy+':ubuntu_manual\n',1)
(root/'src/oneboot-v1.4.ipxe.in').write_text(text,encoding='utf-8')
print('Generated OneBoot v1.4 Manual/Auto menu for Ubuntu 18/20/22/24/26.')
