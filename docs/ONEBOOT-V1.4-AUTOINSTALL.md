# OneBoot v1.4 — Ubuntu 18/20 Manual / Auto extension

Status: complete Ubuntu18/20 UEFI virtual-machine qualification, 2026-10-30.
Delivered ISO: 7 MiB, SHA256 `84030a9cd1c1800b958dc6fbc9e97f03285e52a0ec0b6f317c4c7bd0e9690c33`.
Both versions completed Auto without installer input after Go and passed a
separate cold boot without ISO, root/user password SSH, static IPv4/routes,
DNS, active SSH/networkd and APT configuration checks. The first disk was
24 GiB; the protected second disk was 64 GiB and remained unchanged.
22 helper checks, 10 visually reviewed UI cases and 12 inherited BIOS/UEFI
menu captures passed on the final ISO. Evidence accompanies the delivery.

The new full installs used UEFI/TCG. Disposable image files used cache=unsafe
to reduce host flush latency; the separate-process cold boots verify logical
persistence, not power-loss durability. No production cache setting changed.
New legacy BIOS full installs and physical controllers/iLO remain unqualified.
Ubuntu22/24/26 were checked for retained menus and embedded behavior; their
full installations were not rerun in this v1.4 matrix. The v1.3 BIOS26 full
completion/unattended limitation remains applicable.

OneBoot v1.4 adds optional automatic installation for Ubuntu 18.04 and 20.04.
Ubuntu 22/24/26 retain the existing v1.3 live/Subiquity path. OneBoot starts
directly and contains no netboot.xyz selector.

## Operator flow

Select the NIC and enter the static IPv4/prefix, gateway and DNS. Select the
Ubuntu version, then choose Manual or Auto. Manual remains the default.

Auto asks for a hostname and the same visible password twice. Empty or
different passwords cannot continue. The review screen shows the OS, selected
network, root/user account policy and first-disk erase policy. Explicit Go
starts the automatic installer.

Ubuntu 18/20 Auto uses the classic Ubuntu network installer with a local
preseed. This is the backend used by the supplied Flux installer for these
versions. [Canonical documents Subiquity autoinstall for Ubuntu Server 20.04
and later](https://canonical-subiquity.readthedocs-hosted.com/en/latest/intro-to-autoinstall.html).
The 18/20 Manual
choice retains the original Full ISO in RAM path; the separate legacy Manual
Net install entries remain available.

## Disk, identity and network

Auto selects the first eligible fixed disk in Linux `/sys/block` name order,
using the existing OneBoot selector. It excludes removable/USB, read-only and
SAN-like devices. It does not choose the largest disk. The selected disk is
given explicitly to both partman and GRUB.

The new classic layout uses GPT, a small BIOS boot area, an EFI system
partition and the remaining space as an ext4 root partition. Ubuntu may create
its normal swap file inside root. Other disks are outside the layout. No
automatic RAID creation, global MD/LVM removal or erase-all-disks operation
is supplied. A busy first disk, or existing LVM/RAID/encryption on it, stops
before automatic partitioning instead of selecting another disk.

The confirmed password is transported as a mode-0600 cpio file in RAM. Old
4.15/5.4 kernels require the private profile before the vendor gzip initrd;
the `obprofile prepend` command performs this in memory. No per-server
credential is present in the ISO, public boot assets or kernel arguments.

Root and `user` stay locked during the native account setup. The late hook
sets both passwords through chpasswd stdin, enables root/user SSH password
access and removes the private RAM profile. Service unit files are enabled offline with `systemctl --root=/` inside
the target chroot; this does not require the installer to run a system bus.
The root SSH settings are placed
at the top of the main sshd_config so that Ubuntu 18 also applies them.

The installed system uses MAC-matched static netplan settings, with DHCP4 and
DHCP6 disabled, the selected address/prefix, gateway and DNS. The old installer
ifupdown stanza and generated netplan file are replaced for that interface.

## Downloads and update policy

| Path | Boot files | Installation payload |
| --- | --- | --- |
| Ubuntu 18/20 Auto | Public GitHub `ubuntu-legacy-boot-v1.4-r4` | Signed Ubuntu archive packages |
| Ubuntu 18/20 Manual Full ISO | Existing VPS assets | Existing VPS full ISO in RAM |
| Ubuntu 18/20 Manual Net install | Existing VPS netboot assets | Ubuntu archive packages |
| Ubuntu 22/24/26 Manual / Auto | Existing public paired v1.3 boot release | Exact Canonical ISO / configured release mirrors |

Classic boot inputs are pinned in `config/ubuntu-legacy-autoinstall.json`.
The publisher verifies original Canonical kernel/initrd hashes. Ubuntu 20's
classic kernel is 5.4.0-42, distinct from the 20.04.6 Full ISO kernel. Its
supplementary virtio block module comes from the exact pinned Canonical
package. The builder checks the initrd module ABI and module ELF vermagic.

The automatic initrd is a separate asset containing the preseed and OneBoot
hooks before the original vendor gzip. Manual boot assets contain no active
automatic preseed. The publishing workflow refuses to replace an existing
resource revision.

The classic automatic path uses pkgsel/upgrade=none and skips the security
pocket during installation. The late hook restores a normal security
repository in the installed system. The retained 22/24/26 path keeps its
previous installer-refresh/update policy and mirror behavior.

## Diagnostics and scope of validation

Existing OneBoot transfer/boot errors retain resource, NIC and network
details on screen. In the classic installer, Alt+F4 shows the native log and
Alt+F2 opens a diagnostic shell; the log is `/var/log/syslog`. A OneBoot disk
or profile failure logs a STOP and blocks the automatic operation. Installed
system logs normally appear under `/var/log/installer`.

Qualification uses disposable virtual disks only: a smaller first disk and a
larger second disk containing protected sentinels. The checks cover observed
installer reboot, cold boot without the ISO, chosen root/user password login,
hostname, static routes, DNS, APT configuration and unchanged secondary-disk
content/allocation.

The legacy Ubuntu 20 stock initrd itself crashes at PID1 with the tested
Windows WHPX acceleration. The same unmodified inputs proceed under TCG;
the legacy integration tests therefore use UEFI/TCG. This diagnostic control
does not establish behavior on physical controllers or iLO. BIOS full installs
for the new 18/20 path require separate qualification.

The successful Windows full runs set
`ONEBOOT_TEST_UEFI_ACCEL=tcg,thread=multi`. Their disposable image files used
`ONEBOOT_TEST_DISK_CACHE=unsafe`; the backend defaults to writeback when this
test-only option is absent. The evidence records both choices.

Run `scripts/test-oneboot-legacy-autoinstall.py`,
`scripts/test-oneboot-profile-cpio.py` and the existing
`scripts/test-oneboot-autoinstall.py` for helper checks.
`scripts/verify-oneboot-v1.4.py` inspects the actual hybrid ISO and unchanged
other-OS paths. `scripts/test-oneboot-v1.4-qemu.py` runs disposable UI/full
installation checks. The tested artifact and evidence record their hashes.

Flux source remains pinned at
`594deb47a8d6e73d6597168733248fec4f572608`, with attribution and GPL license
under `vendor/fluxbilling` and `NOTICE-FLUXBILLING.md`.
