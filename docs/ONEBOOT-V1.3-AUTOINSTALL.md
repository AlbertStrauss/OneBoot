# OneBoot v1.3 — Ubuntu Manual / Auto

Status: candidate delivered on 2026-10-29 with the BIOS26 startup limitation below.
ISO SHA256: `368bd7603dd7ba5e0182c51b6b1518ec5892dba57905104049b100343ed80473`.

Five clean full Auto installations passed: Ubuntu22 and Ubuntu24 in BIOS/UEFI,
and Ubuntu26 in UEFI. Each included a cold boot without the ISO, chosen root/user
password login, hostname/static routes and unchanged second-disk data.
The original Ubuntu26 BIOS install reached its last late command before the
observer expired. Its preserved target later cold-booted successfully: chosen
root/user passwords, hostname/static routes and APT configuration passed.
Full installation completion was not observed. A subsequent emulated BIOS26
startup failed at netplan apply; an operator service restart did not produce a
completed install. Full/unattended Ubuntu26 BIOS installation remains unqualified.
It needs validation on the actual server hardware. All physical-controller/iLO
qualification remains separate from these disposable VM checks.

Do not replace the production v1.0 ISO or its assets from this candidate.

## Operator flow

OneBoot starts directly, without netboot.xyz. Select the NIC and enter the
usual static IPv4/prefix, gateway and DNS. Select Ubuntu Server 22.04.5,
24.04.4 or 26.04, then choose Manual or Auto. Manual is the default and
starts the ordinary Ubuntu installer without an automatic disk policy.

Auto asks for a hostname and the password twice. Both entries are visible;
empty or different passwords cannot continue. A review screen shows the
selected OS and network, root/user login policy and first-disk erase policy.
The default action returns to the mode menu. Only explicit Go starts Auto.

Auto uses Ubuntu's direct layout on the first eligible fixed disk: firmware
boot partitions and a root filesystem, without a swap file or automatic RAID.
The selector excludes removable/USB, read-only, virtual and SAN-like devices.
Its order is Linux `/sys/block` name order, inherited from the Flux selector;
it does not select the largest disk. Active holders on the first eligible
disk cause a stop instead of dismantling storage or choosing another disk.
It contains no all-disk wipe, RAID teardown or discard operations. Servers
with existing RAID/storage stacks should use Manual for operator review.

The chosen password sets root and the `user` account, which belongs to sudo.
SSH password login is enabled for both, following the supplied Flux workflow.
The password is passed as a private mode-0600 cpio file in RAM, not a kernel
argument or a plaintext field in the archived autoinstall YAML. A late command
creates `user` if needed, applies both passwords and removes the RAM profile.

## Downloads and install behavior

The small ISO contains OneBoot loaders, helpers and the existing artwork.
The Ubuntu kernel/initrd are original matched pairs from the public release:
https://github.com/AlbertStrauss/OneBoot/releases/tag/ubuntu-live-boot-v1.3

The publishing workflow downloads the exact Canonical full ISO, checks its
pinned SHA256, extracts the pair and checks their hashes before publication.
Pinned versions/hashes are in `config/ubuntu-autoinstall.json`. The firmware
loaders use HTTPS and individually embedded public root certificates.

The live initrd downloads the full Ubuntu ISO into RAM. Start with 8 GiB RAM
or more. It measures the Canonical origin and, if needed, four public release
mirrors: RWTH Aachen, Init7, OVH and Lysator. A fixed version always retains
the exact ISO filename; it is never silently replaced with a newer point
release. The initrd's own ISO UUID check is enabled for origin and mirrors.
This is compose matching; it is not a runtime full-ISO SHA256 check.

Known auxiliary-console limit: the serial progress watcher can follow a short
mirror-probe wget process and announce a 0 MB completion prematurely. The main
video console continues showing the real wget progress, and the mount/install
path still waits for the real download. This status-only issue is retained in
the tested candidate; it is not evidence that the ISO finished downloading.

The adapted Flux downloader can resume or use parallel transfers when useful.
Existing OneBoot transfer errors remain visible with resource/network details.
New Ubuntu paths use public GitHub/Ubuntu sources and do not require a VPS
allowlist entry. Other OS paths retain their previous VPS downloads and policy.

Auto suppresses installer self-refresh and security/update pockets during
installation, using the ISO base system. Its late commands restore the normal
installed-system repositories. This avoids making installation completion
depend on downloading a newer installer or security package set.

## Source and qualification

Flux source is pinned at commit
`594deb47a8d6e73d6597168733248fec4f572608`, retained with its GPL license under
`vendor/fluxbilling/`. See `NOTICE-FLUXBILLING.md` for adaptations. The custom
profile commands and first-disk selector are OneBoot changes. BIOS USB policy
and the EFI iLO4 console patch are derived from that pinned source.

Run `scripts/test-oneboot-autoinstall.py` for seed, password, mirror and disk
selection behavior. `scripts/verify-oneboot-v1.3.py` checks the actual hybrid
ISO, embedded helpers, certificates and unchanged other-OS menu blocks.
`scripts/test-oneboot-autoinstall-qemu.py` uses only disposable virtual disks
for full installs, cold boots, SSH logins and secondary-disk integrity.

Current test evidence and qualification limits are recorded in
PROJECT_CONTEXT.md and TESTING.md. Physical server, storage-controller and
Secure Boot qualification is separate from the disposable VM matrix.

## BIOS26 qualification condition

UEFI used WHPX; BIOS used TCG. Ubuntu26 BIOS required instruction-counted
TCG time (HPET on) to pass an early timer panic. Later its initial network apply
returned `Call failed: Connection timed out`; media checks passed and networking
became available. Slow emulation is suspected, not established as the physical
hardware cause. No noapic or timing workaround was added to the product ISO.
The original failure, service-restart attempt and separate late-disk cold boot
are included in evidence. No failed/partial run is counted as a full install pass.

Reproduce the Windows test clock with ONEBOOT_TEST_TCG_ICOUNT=auto. A recorded
startup-assistance.json always prevents classifying the case as a clean unattended
startup, even when the later install/cold-boot checks pass. Earlier partial or
interrupted attempts are not completed installation passes.
