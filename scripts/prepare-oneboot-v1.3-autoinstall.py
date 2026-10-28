#!/usr/bin/env python3
"""Derive the Ubuntu live helpers from the pinned, attributed Flux source."""
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
vendor=root/'vendor/fluxbilling/src'
out=root/'autoinstall'
out.mkdir(exist_ok=True)

def adapt(name):
    text=(vendor/name).read_text().replace('FluxBilling','OneBoot').replace('fluxbilling','oneboot').replace('FLUX','ONEBOOT').replace('flux','oneboot')
    return text

seed=adapt('99fluxseed')
seed=seed.replace("if ! echo \"$C\" | tr ' ' '\\n' | grep -qx autoinstall; then",
    "if ! echo \"$C\" | tr ' ' '\\n' | grep -qx autoinstall || ! echo \"$C\" | tr ' ' '\\n' | grep -qx 'oneboot.autoinstall=1'; then")
seed=seed.replace('H=$(zget oneboothost)\n[ -n "$H" ] || H=onebootserver',
'''PROFILE=${oneboot_profile:-/oneboot-profile}
H=$(sed -n 's/^HOSTNAME=//p' "$PROFILE" 2>/dev/null)
PH=$(sed -n 's/^PASSWORD_HEX=//p' "$PROFILE" 2>/dev/null)
case "$H" in ''|*[!a-zA-Z0-9.-]*|[-.]*|*[-.]) echo 'OneBoot: invalid hostname profile' >&2; exit 1 ;; esac
case "$PH" in ''|*[!0-9a-f]* ) echo 'OneBoot: missing password profile' >&2; exit 1 ;; esac
[ $((${#PH} % 2)) -eq 0 ] || exit 1
''')
assert 'H=$(zget oneboothost)' not in seed
seed=seed.replace('cp "${oneboot_disks:-/oneboot-disks}" "$ONEBOOTROOT/usr/local/sbin/oneboot-disks" 2>/dev/null &&\n\tchmod 755 "$ONEBOOTROOT/usr/local/sbin/oneboot-disks"',
'''cp "${oneboot_disks:-/oneboot-disk}" "$ONEBOOTROOT/usr/local/sbin/oneboot-disks" || exit 1
cp "${oneboot_set_password:-/oneboot-set-password}" "$ONEBOOTROOT/usr/local/sbin/oneboot-set-password" || exit 1
chmod 755 "$ONEBOOTROOT/usr/local/sbin/oneboot-disks" "$ONEBOOTROOT/usr/local/sbin/oneboot-set-password"
LIVE_RUN=${oneboot_run:-/run}
mkdir -p "$LIVE_RUN"
# initramfs-tools moves this tmpfs to the live system's /run at switch-root.
cp "$PROFILE" "$LIVE_RUN/oneboot-profile" || exit 1
chmod 600 "$LIVE_RUN/oneboot-profile"''')
assert 'oneboot_set_password' in seed
seed=seed.replace('t=$(sh /usr/local/sbin/oneboot-disks) || t=/dev/oneboot-no-fixed-disk-found; sed -i',
    'set -e; t=$(sh /usr/local/sbin/oneboot-disks); sed -i')
lines=seed.splitlines()
for i,line in enumerate(lines):
    if 'curtin in-target --target=/target -- bash -c' in line and 'onebootpass=' in line:
        lines[i]='      bash /usr/local/sbin/oneboot-set-password'
    if 'curtin in-target' in line and 'PermitRootLogin' in line:
        lines[i]='      curtin in-target --target=/target -- sh -c \'mkdir -p /etc/ssh/sshd_config.d; printf "PermitRootLogin yes\\nPasswordAuthentication yes\\n" > /etc/ssh/sshd_config.d/00-oneboot-access.conf\''
seed='\n'.join(lines)+'\n'
# The inherited legacy sources.list expression used | both as the sed
# separator and as regex alternation, aborting Ubuntu 22 late-commands.
broken=r'''sed -i -E "s|^# *(deb .*(-updates|-security|-backports).*)|\\1|"'''
fixed=r'''sed -i -E "s~^# *(deb .*(-updates|-security|-backports).*)~\\1~"'''
assert broken in seed
seed=seed.replace(broken,fixed)
seed=re.sub(r'# onebootpass is deliberately NOT read here\..*?(?=CIDR=)',
    '# Credentials stay in a private RAM profile, outside the archived YAML.\n',seed,flags=re.S)
seed=re.sub(r'  # Choose the install disk by the rule every automated entry shares, and -.*?(?=  early-commands:)',
    '  # Select one eligible fixed disk. Stop on active holders; no all-disk wipe.\n'
    '  # Subiquity re-reads this YAML after early-commands set the exact path.\n',seed,flags=re.S)
seed=seed.replace('[ -n "$NS2" ] || NS2=1.1.1.1','[ -n "$NS2" ] || NS2=$NS1')
seed=seed.replace('addresses: [8.8.8.8, 1.1.1.1]','addresses: [ $NS1, $NS2 ]')
seed=seed.replace('      onebootnic:\n        match:', '      onebootnic:\n        dhcp4: false\n        dhcp6: false\n        match:')
seed=re.sub(r'(?m)^(\s*)via: \$GW$',r'\1via: $GW\n\1on-link: true',seed)
# Passwords ride a private RAM image, not the kernel command line. The original
# first-boot log scrub is retained as a harmless compatibility backstop.
assert 'bash /usr/local/sbin/oneboot-set-password' in seed
assert 'PASSWORD_HEX=' in seed and 'onebootpass=' not in '\n'.join(l for l in seed.splitlines() if 'curtin in-target' in l)
(out/'99onebootseed').write_text(seed)

params=adapt('param.conf').replace('sh /scripts/casper-bottom/99onebootseed',
    'sh /scripts/casper-bottom/99onebootseed || panic "OneBoot: invalid or incomplete autoinstall profile"')
(out/'param.conf').write_text(params)

mirror=adapt('flux-mirror-pick')
mirror=mirror.replace('local idx name\n', '''local idx name
\tcase "${oneboot_origin_url##*/}" in
\t    *-latest-live-server-amd64.iso) ;;
\t    *) printf '%s/%s/%s' "$1" "$2" "${oneboot_origin_url##*/}"; return 0 ;;
\tesac
''',1)
mirror=mirror.replace('case "$URL" in\n\t\t*-latest-live-server-amd64.iso) ;;',
    'case "$URL" in\n\t\t*-live-server-amd64.iso) ;;')
mirror=mirror.replace('series=${series%%-latest-*}', '''series=${series%%-live-server-amd64.iso}
\tseries=${series%-latest}
\t# A fixed point release (24.04.4) belongs under the series directory (24.04).
\tcase "$series" in *.*.*) series=${series%.*} ;; esac''')
mirror=mirror.replace('UUID=""','UUID=$(cat "${oneboot_confdir:-/conf}/uuid.conf" 2>/dev/null)')
assert 'series=${series%.*}' in mirror
(out/'oneboot-mirror-pick').write_text(mirror)

# Reuse only Flux's eligibility/description rules. No wipe, release, discard,
# unmount, or RAID teardown code is imported into this selector.
disk=adapt('flux-disks')
start=disk.index('S=${oneboot_sys:-/sys}')
end=disk.index('# under <sysfs dir>')
disk='#!/bin/sh\n# Adapted from FluxBilling src/flux-disks (GPL-2.0-or-later).\n'+disk[start:end]
disk=re.sub(r'# 16 MiB.*?EDGE=32768\n','',disk,flags=re.S)
disk+='''
command -v udevadm >/dev/null 2>&1 && udevadm settle --timeout=60 >/dev/null 2>&1
for b in "$S"/block/*; do
    [ -e "$b" ] || continue
    n=${b##*/}
    eligible "$n" || continue
    # Fail on a busy first disk rather than selecting another disk or
    # dismantling a storage stack that may span other disks.
    for part in "$b" "$b"/"$n"*; do
        [ -d "$part" ] || continue
        for holder in "$part"/holders/*; do
            [ -e "$holder" ] || continue
            say "first disk $(describe "$n") has an active storage holder; use manual installation"
            exit 1
        done
    done
    say "install disk: $(describe "$n"); only this disk may be partitioned"
    node "$n"
    exit 0
done
say 'no eligible fixed install disk found; no target selected'
exit 1
'''
assert not any(x in disk for x in ('wipefs','blkdiscard','dd if=','mdadm','dmsetup'))
(out/'oneboot-disk').write_text(disk)
for p in out.iterdir():
    if p.is_file():p.chmod(0o755)
print('Prepared attributed Ubuntu autoinstall, diagnostics, fixed mirror picker and single-disk selector.')
