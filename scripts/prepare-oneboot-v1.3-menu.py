#!/usr/bin/env python3
"""Standalone OneBoot menu with manual/auto choices for Ubuntu 22/24/26."""
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
cfg=json.loads((root/'config/ubuntu-autoinstall.json').read_text())
text=(root/'src/oneboot-v1.0.ipxe.in').read_text()
text=text.replace('set oneboot_version 1.0','set oneboot_version 1.3',1)
text=text.replace('set console_mode text','obpayload || goto shell\nset console_mode text',1)
text=text.replace('Interactive installers - choose version and installation method','Ubuntu 22/24/26: choose Manual or Auto after selecting the version')
for v in cfg['versions']:
    label='boot_ubuntu_'+v['key']
    body=f''':{label}
set ubuntu_version {v['version']}
set ubuntu_name Ubuntu Server {v['version']} LTS
goto ubuntu_install_mode
'''
    text,n=re.subn(r'^:'+label+r'\n.*?(?=^:)',body,text,count=1,flags=re.M|re.S)
    assert n==1

new=r''':ubuntu_install_mode
clear oneboot_password
clear oneboot_confirm
obprofile clear ||
menu --name ubuntu_mode ${ubuntu_name} - installation mode
item --menu ubuntu_mode --gap -- Manual asks Ubuntu's normal installer questions.
item --menu ubuntu_mode --gap -- Auto configures the first eligible fixed disk only.
item --menu ubuntu_mode --key m ubuntu_manual Manual install
item --menu ubuntu_mode --key a ubuntu_auto_form Auto install
item --menu ubuntu_mode --key b os_menu Back to Ubuntu versions
choose --menu ubuntu_mode --default ubuntu_manual ubuntu_mode_choice || goto os_menu
goto ${ubuntu_mode_choice}

:ubuntu_auto_form
clear oneboot_password
clear oneboot_confirm
echo
echo ${ubuntu_name} - Auto install
echo Hostname:
read oneboot_hostname || goto ubuntu_install_mode
echo Password (visible):
read oneboot_password || goto ubuntu_install_mode
echo Confirm password (visible):
read oneboot_confirm || goto ubuntu_install_mode
obprofile check oneboot_hostname oneboot_password oneboot_confirm || goto ubuntu_profile_invalid
goto ubuntu_auto_review

:ubuntu_profile_invalid
prompt Press any key to enter the profile again... ||
goto ubuntu_auto_form

:ubuntu_auto_review
menu --name ubuntu_review Review automatic installation
item --menu ubuntu_review --gap -- OS: ${ubuntu_name}
item --menu ubuntu_review --gap -- Hostname: ${oneboot_hostname}
item --menu ubuntu_review --gap -- NIC: ${nic_mac}
item --menu ubuntu_review --gap -- IPv4: ${validated_ip}/${input_prefix}
item --menu ubuntu_review --gap -- Gateway: ${validated_gateway} - DNS: ${validated_dns}
item --menu ubuntu_review --gap -- Login: root and user (sudo), using the confirmed password
item --menu ubuntu_review --gap -- ERASES the first eligible fixed disk: boot partitions and root.
item --menu ubuntu_review --gap -- Other disks remain outside this installation layout.
item --menu ubuntu_review --key g ubuntu_auto_go Go - erase the first disk and install automatically
item --menu ubuntu_review --key e ubuntu_auto_form Edit hostname / visible password
item --menu ubuntu_review --key b ubuntu_install_mode Back to installation mode
choose --menu ubuntu_review --default ubuntu_install_mode ubuntu_review_choice || goto ubuntu_install_mode
goto ${ubuntu_review_choice}

:ubuntu_auto_go
imgfree
obpayload restore || goto ubuntu_local_helpers_failed
obprofile create oneboot_hostname oneboot_password oneboot_confirm || goto ubuntu_profile_invalid
clear oneboot_password
clear oneboot_confirm
set ubuntu_auto_args autoinstall ds=nocloud oneboot.autoinstall=1
goto ubuntu_live_start

:ubuntu_manual
clear oneboot_password
clear oneboot_confirm
clear ubuntu_auto_args
imgfree
obpayload restore || goto ubuntu_local_helpers_failed
goto ubuntu_live_start

:ubuntu_live_start
set ubuntu_boot_base @@UBUNTU_BOOT_RELEASE@@
set ubuntu_iso https://releases.ubuntu.com/${ubuntu_version}/ubuntu-${ubuntu_version}-live-server-amd64.iso
set ob_boot_resource ${ubuntu_boot_base}/ubuntu-${ubuntu_version}-vmlinuz
echo Starting ${ubuntu_name}. Full ISO downloads into RAM; 8 GiB RAM recommended.
kernel --name kboot ${ob_boot_resource} initrd=initrd.magic root=/dev/ram0 BOOTIF=${bootif} ip=${validated_ip}::${validated_gateway}:${validated_netmask}:::none:${validated_dns} onebootcidr=${input_prefix} url=${ubuntu_iso} ${ubuntu_auto_args} cloud-config-url=/dev/null console=ttyS0,115200n8 console=tty0 --- || oberror kernel ${ob_boot_resource} ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed
initrd --name iboot ${ubuntu_boot_base}/ubuntu-${ubuntu_version}-initrd || oberror initrd ${ubuntu_boot_base}/ubuntu-${ubuntu_version}-initrd ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed
boot || oberror boot ${ob_boot_resource} ${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns} || goto ubuntu_live_failed

:ubuntu_live_failed
imgfree kboot ||
imgfree iboot ||
obprofile clear ||
clear ubuntu_auto_args
oberror --show
prompt --key 0x1b Ubuntu boot failed. Press Esc to choose the installation mode again... ||
goto ubuntu_install_mode

:ubuntu_local_helpers_failed
echo OneBoot could not restore its local Ubuntu helper files. No installer was started.
prompt --key 0x1b Press Esc to return... ||
goto ubuntu_install_mode

'''.replace('@@UBUNTU_BOOT_RELEASE@@',cfg['boot_release'])
text,n=re.subn(r'^:boot_ubuntu\n.*?(?=^:download_failed)',new,text,count=1,flags=re.M|re.S)
assert n==1
(root/'src/oneboot-v1.3.ipxe.in').write_text(text)
print('Generated OneBoot v1.3 Ubuntu manual/auto menu.')
