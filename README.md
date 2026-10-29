# OneBoot

OneBoot v1.3 starts directly into its static NIC/IPv4 configuration and OS menu,
without netboot.xyz. Ubuntu Server 22.04.5, 24.04.4 and 26.04 offer Manual or Auto.
Manual is the default. Auto requires a hostname, the same visible password
twice, and explicit Go. It installs boot/root on the first eligible fixed disk;
it does not create RAID or wipe all disks. Active holders on the first disk
cause a stop for operator review.

The operator's password is used for root and the sudo account `user`, including
SSH. Credentials travel in a private RAM cpio file, outside kernel arguments
and the archived autoinstall YAML. The installer does not have a default password.

**Candidate delivered with a BIOS26 startup limitation.**

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

UEFI used WHPX; BIOS used TCG. Ubuntu26 BIOS required instruction-counted
TCG time (HPET on) to pass an early timer panic. Later its initial network apply
returned `Call failed: Connection timed out`; media checks passed and networking
became available. Slow emulation is suspected, not established as the physical
hardware cause. No noapic or timing workaround was added to the product ISO.
The original failure, service-restart attempt and separate late-disk cold boot
are included in evidence. No failed/partial run is counted as a full install pass.

Thirteen helper regression tests, actual ISO/static checks, visible invalid-password
UI checks, native Manual Ubuntu24 without disk writes, and existing-menu/download-error
compatibility checks passed. Production OneBoot v1.0 and its service policy remain unchanged.

## Boot resources

Original, matched Ubuntu kernel/initrd pairs are published in
[ubuntu-live-boot-v1.3](https://github.com/AlbertStrauss/OneBoot/releases/tag/ubuntu-live-boot-v1.3).
The publishing workflow verifies the exact Canonical ISO SHA256 before extracting
and verifying each pair. Versions and hashes are pinned in
`config/ubuntu-autoinstall.json`.

The full ISO downloads into RAM from Canonical or a measured public Ubuntu
release mirror. Fixed versions retain their exact filename, and the initrd's
compose UUID check stays enabled. This is not a runtime full-ISO SHA256 check.
Allow at least 8 GiB RAM and internet access to the HTTPS boot/download sources.
The loaders are unsigned; use ordinary BIOS/UEFI boot with Secure Boot disabled.

Ubuntu Auto avoids installer self-refresh and update/security pockets during
installation, then restores the installed system's repositories. Other OS
entries retain their existing interactive VPS-backed paths and access policy.

## Source and builds

See `docs/ONEBOOT-V1.3-AUTOINSTALL.md` and `NOTICE-FLUXBILLING.md`. The Ubuntu
helpers are adapted from pinned FluxBilling source with GPL attribution retained.
The first-disk policy, private credential transport and Manual/Auto workflow
are OneBoot adaptations.

`scripts/build-oneboot-v1.3-vps.py` builds in a separate
`/srv/oneboot/staging/oneboot-v1.3-autoinstall-*` root. It requires the existing
pinned OneBoot asset store, the iPXE checkout at
`8958a4a66022640d622dec1ad5f2ddf77adfcd0f`, Linux build tools, xorriso, mtools,
syslinux and current public CA certificates. It does not replace a delivered
production ISO. Full Ubuntu ISOs and the other OS asset store are not in Git.

Validation scripts cover generated profiles and repository restoration,
first-disk selection/protection, actual ISO contents, BIOS/UEFI menus and full
disposable two-disk installs. Windows test helpers use only project disk files
and loopback management ports; their credentials are synthetic VM test data.

The earlier Ubuntu24 split-image mirror under `mirrors/` is historical and is
not used by this autoinstall design.
