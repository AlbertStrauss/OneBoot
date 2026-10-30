#!/usr/bin/env python3
"""Restore VPS-first Ubuntu boot and require a key before public fallback."""
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'scripts/prepare-oneboot-v1.4-menu.py')],check=True)
text=(root/'src/oneboot-v1.4.ipxe.in').read_text(encoding='utf-8')
cfg=json.loads((root/'config/ubuntu-download-policy-v1.4.1.json').read_text())
legacy=json.loads((root/'config/ubuntu-legacy-autoinstall.json').read_text())
text=text.replace('set oneboot_version 1.4','set oneboot_version 1.4.1',1)
def block(label,body):
    global text
    text,n=re.subn(r'^:'+re.escape(label)+r'\n.*?(?=^:|\Z)',lambda _:':'+label+'\n'+body+'\n',text,count=1,flags=re.M|re.S)
    assert n==1,label
for v in cfg['modern']:
    block('boot_ubuntu_'+v['key'],f'''set ubuntu_version {v['version']}
set ubuntu_series {v['series']}
set ubuntu_iso_hash {v['iso_sha256']}
set ubuntu_name Ubuntu Server {v['version']} LTS
set ubuntu_backend casper
goto ubuntu_install_mode''')
for v in cfg['legacy_full']:
    major=v['version'][:2];key=major+'04'
    origin=next(x['origin'] for x in legacy['versions'] if x['version'].startswith(major))
    variables=f'''set ubuntu_version {v['version']}
set ubuntu_series {major}.04
set ubuntu_iso_hash {v['iso_sha256']}
set ubuntu_name Ubuntu Server {v['version']} LTS
set ubuntu_net_version {major}.04
set ubuntu_net_suite {'bionic' if major=='18' else 'focal'}
set ubuntu_net_origin {origin}
set ubuntu_backend legacy'''
    block('boot_ubuntu_'+key+'_live',variables+'\ngoto ubuntu_install_mode')
    block('boot_ubuntu_'+key+'_net',variables+'''\nset ubuntu_mode manual_net
clear ubuntu_auto_args
obprofile clear ||
goto ubuntu_vps_start''')
text=text.replace('iseq ${ubuntu_backend} di && item','iseq ${ubuntu_backend} legacy && item')
text=text.replace('item --menu ubuntu_mode --gap -- Manual asks',
    'item --menu ubuntu_mode --gap -- VPS first. Public fallback only after you select it.\nitem --menu ubuntu_mode --gap -- Manual asks',1)
start=text.index(':ubuntu_auto_go\n');end=text.index(':download_failed\n',start)
common='${nic} ${nic_mac} ${validated_ip}/${input_prefix} ${validated_gateway} ${validated_dns}'
def transfer(command,operation,url):
    return command+' || oberror '+operation+' '+url+' '+common+' || goto ubuntu_source_failed'
network='BOOTIF=${bootif} ip=${validated_ip}::${validated_gateway}:${validated_netmask}:::none:${validated_dns}'
policy='oneboot.policy=vps-first-v1 oneboot.source=${ubuntu_source} oneboot.primary=${ubuntu_iso} oneboot.fallback=${ubuntu_fallback_iso} oneboot.iso_sha256=${ubuntu_iso_hash} oneboot.series=${ubuntu_series}'
di='initrd=initrd.magic BOOTIF=${bootif} netcfg/choose_interface=${nic_mac} netcfg/disable_autoconfig=true netcfg/disable_dhcp=true netcfg/get_ipaddress=${validated_ip} netcfg/get_netmask=${validated_netmask} netcfg/get_gateway=${validated_gateway} netcfg/get_nameservers=${validated_dns} netcfg/confirm_static=true mirror/country=manual mirror/http/hostname=archive.ubuntu.com mirror/http/directory=/ubuntu mirror/http/proxy= mirror/suite=${ubuntu_net_suite} apt-setup/security_host=security.ubuntu.com nomodeset modprobe.blacklist=mgag200 console=ttyS0,115200n8 console=tty0'
new='''\
:ubuntu_auto_go
imgfree
obpayload restore || goto ubuntu_local_helpers_failed
obprofile create oneboot_hostname oneboot_password oneboot_confirm || goto ubuntu_profile_invalid
clear oneboot_password
clear oneboot_confirm
set ubuntu_mode auto
set ubuntu_auto_args autoinstall ds=nocloud oneboot.autoinstall=1
goto ubuntu_vps_start

:ubuntu_manual
clear oneboot_password
clear oneboot_confirm
obprofile clear ||
clear ubuntu_auto_args
set ubuntu_mode manual
goto ubuntu_vps_start

:ubuntu_vps_start
set ubuntu_source vps
goto ubuntu_source_start

:ubuntu_fallback_start
set ubuntu_source fallback
goto ubuntu_source_start

:ubuntu_source_start
imgfree
set ubuntu_iso ${base_url}/ubuntu/ubuntu-${ubuntu_version}-live-server-amd64.iso
set ubuntu_fallback_iso https://releases.ubuntu.com/${ubuntu_version}/ubuntu-${ubuntu_version}-live-server-amd64.iso
echo Starting ${ubuntu_name} - ${ubuntu_mode}; selected source: ${ubuntu_source}
iseq ${ubuntu_mode} manual_net && goto ubuntu_di_manual_start ||
iseq ${ubuntu_backend} casper && goto ubuntu_casper_start ||
iseq ${ubuntu_mode} auto && goto ubuntu_di_auto_start ||
iseq ${ubuntu_source} fallback && goto ubuntu_di_manual_start ||
goto ubuntu_legacy_full_start

:ubuntu_casper_start
obpayload restore || goto ubuntu_local_helpers_failed
iseq ${ubuntu_mode} auto || goto ubuntu_casper_profile_ready
obprofile restore || goto ubuntu_local_helpers_failed

:ubuntu_casper_profile_ready
set ubuntu_kernel ${base_url}/ubuntu/${ubuntu_version}/vmlinuz
set ubuntu_initrd ${base_url}/ubuntu/${ubuntu_version}/initrd
iseq ${ubuntu_source} vps && goto ubuntu_casper_fetch ||
set ubuntu_kernel @@LIVE_RELEASE@@/ubuntu-${ubuntu_version}-vmlinuz
set ubuntu_initrd @@LIVE_RELEASE@@/ubuntu-${ubuntu_version}-initrd

:ubuntu_casper_fetch
echo Full ISO downloads into RAM. VPS is primary; fallback is operator selected.
set ob_boot_resource ${ubuntu_kernel}
@@CASPER_KERNEL@@
@@INITRD@@
@@BOOT@@

:ubuntu_legacy_full_start
echo Original interactive Full ISO installation from VPS.
set ubuntu_kernel ${base_url}/ubuntu/${ubuntu_version}/vmlinuz
set ubuntu_initrd ${base_url}/ubuntu/oneboot-v1.4.1/full/${ubuntu_version}/initrd
set ob_boot_resource ${ubuntu_kernel}
@@LEGACY_KERNEL@@
@@INITRD@@
@@BOOT@@

:ubuntu_di_auto_start
obprofile restore || goto ubuntu_local_helpers_failed
set ubuntu_kernel ${base_url}/ubuntu/netboot/${ubuntu_net_version}/linux
set ubuntu_initrd ${base_url}/ubuntu/oneboot-v1.4.1/netboot/${ubuntu_net_version}/auto-initrd
iseq ${ubuntu_source} vps && goto ubuntu_di_auto_fetch ||
set ubuntu_kernel @@DI_RELEASE@@/ubuntu-${ubuntu_net_version}-vmlinuz
set ubuntu_initrd @@DI_RELEASE@@/ubuntu-${ubuntu_net_version}-auto-initrd

:ubuntu_di_auto_fetch
echo Classic Auto: boot files from ${ubuntu_source}; packages from Ubuntu archive.
set ob_boot_resource ${ubuntu_kernel}
@@DI_AUTO_KERNEL@@
@@INITRD@@
obprofile prepend iboot || goto ubuntu_local_helpers_failed
@@BOOT@@

:ubuntu_di_manual_start
obprofile clear ||
set ubuntu_kernel ${base_url}/ubuntu/netboot/${ubuntu_net_version}/linux
set ubuntu_initrd ${base_url}/ubuntu/netboot/${ubuntu_net_version}/initrd.gz
iseq ${ubuntu_source} vps && goto ubuntu_di_manual_fetch ||
set ubuntu_kernel ${ubuntu_net_origin}/linux
set ubuntu_initrd ${ubuntu_net_origin}/initrd.gz

:ubuntu_di_manual_fetch
echo Interactive classic Net installer. Public fallback uses the official Ubuntu archive.
set ob_boot_resource ${ubuntu_kernel}
@@DI_MANUAL_KERNEL@@
@@INITRD@@
@@BOOT@@

:ubuntu_source_failed
imgfree
iseq ${ubuntu_source} vps && echo VPS fetch / boot failed. Public fallback has NOT been tried. || echo The explicitly selected fallback failed.
iseq ${ubuntu_source} vps && set ubuntu_source_label VPS || set ubuntu_source_label Fallback
menu --name ubuntu_fetch_failed Ubuntu ${ubuntu_version} - ${ubuntu_source_label} fetch failed
item --menu ubuntu_fetch_failed --gap -- No installer has started. No automatic switch to public sources.
item --menu ubuntu_fetch_failed --key d ubuntu_source_details Show fetch details - exact URL / error / network
item --menu ubuntu_fetch_failed --key r ubuntu_vps_start Retry VPS
item --menu ubuntu_fetch_failed --key f ubuntu_fallback_start Try fallback - GitHub / official Ubuntu sources
item --menu ubuntu_fetch_failed --key e network_form Edit IP / gateway / DNS
item --menu ubuntu_fetch_failed --key n nic_menu Select another NIC
item --menu ubuntu_fetch_failed --key b ubuntu_install_mode Back to installation mode
choose --menu ubuntu_fetch_failed --default ubuntu_install_mode ubuntu_fetch_choice || goto ubuntu_install_mode
goto ${ubuntu_fetch_choice}

:ubuntu_source_details
oberror --show
prompt --key 0x1b Press Esc to return to Retry VPS / Try fallback... ||
goto ubuntu_source_failed

:ubuntu_live_failed
goto ubuntu_source_failed

:ubuntu_local_helpers_failed
imgfree
echo OneBoot local profile/helper error. No installer was started.
prompt --key 0x1b Press Esc to return to installation mode... ||
goto ubuntu_install_mode

'''
new=new.replace('@@LIVE_RELEASE@@',cfg['boot_release']).replace('@@DI_RELEASE@@',cfg['legacy_boot_release'])
for marker,line in {
 '@@CASPER_KERNEL@@':transfer('kernel --name kboot ${ubuntu_kernel} initrd=initrd.magic boot=casper root=/dev/ram0 '+network+' onebootcidr=${input_prefix} url=${ubuntu_iso} '+policy+' ${ubuntu_auto_args} cloud-config-url=/dev/null console=ttyS0,115200n8 console=tty0 ---','kernel','${ubuntu_kernel}'),
 '@@LEGACY_KERNEL@@':transfer('kernel --name kboot ${ubuntu_kernel} initrd=initrd.magic boot=casper root=/dev/ram0 '+network+' oneboot.iso=${ubuntu_iso} oneboot_legacy=1 oneboot.prefix=${input_prefix} oneboot.dns=${validated_dns} '+policy+' cloud-config-url=/dev/null ---','kernel','${ubuntu_kernel}'),
 '@@DI_AUTO_KERNEL@@':transfer('kernel --name kboot ${ubuntu_kernel} '+di+' netcfg/get_hostname=${oneboot_hostname} netcfg/hostname=${oneboot_hostname} oneboot.prefix=${input_prefix} oneboot.autoinstall=1 auto=true priority=critical locale=en_US.UTF-8 keyboard-configuration/layoutcode=us console-setup/ask_detect=false ---','kernel','${ubuntu_kernel}'),
 '@@DI_MANUAL_KERNEL@@':transfer('kernel --name kboot ${ubuntu_kernel} '+di+' ---','kernel','${ubuntu_kernel}'),
 '@@INITRD@@':transfer('initrd --name iboot ${ubuntu_initrd}','initrd','${ubuntu_initrd}'),
 '@@BOOT@@':transfer('boot','boot','${ob_boot_resource}')}.items():new=new.replace(marker,line)
text=text[:start]+new+text[end:]
assert '@@' not in text.replace('@@BASE_URL@@','')
(root/'src/oneboot-v1.4.1.ipxe.in').write_text(text,encoding='utf-8',newline='\n')
print('Generated v1.4.1: every Ubuntu entry VPS first; no timed/automatic public fallback.')
