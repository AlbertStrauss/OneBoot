# OneBoot v1.4

Small standalone BIOS/UEFI network bootstrap ISO with static NIC/IP setup,
visible transfer diagnostics and Ubuntu Manual / Auto selection.

Version 1.4 adds classic automatic installation for Ubuntu 18.04 and 20.04,
following the supplied Flux installer backend. Ubuntu 22/24/26 keep their
existing paired live/Subiquity path. The ISO contains OneBoot directly.

Auto asks for hostname and the same visible password twice, then requires
explicit Go. It installs to the first eligible fixed disk, enables the chosen
password for root and `user` over SSH and configures the selected static
network. Other disks are outside its partition layout. Manual remains the
default and starts the ordinary installer.

For Ubuntu 18/20, Auto downloads pinned boot files from the public GitHub boot
release and signed packages from the Ubuntu archive. Manual Full ISO retains
the existing VPS path. The new classic Auto route needs no VPS allowlist entry.

See [the v1.4 guide](docs/ONEBOOT-V1.4-AUTOINSTALL.md) for disk rules, downloads,
credential transport, diagnostics and qualification. The delivered ISO and
evidence identify the exact tested bytes. Physical controller/iLO and legacy
BIOS installation qualification are separate from UEFI virtual-machine tests.

The 22/24/26 implementation and its existing BIOS26 limitation are documented
in [the retained v1.3 guide](docs/ONEBOOT-V1.3-AUTOINSTALL.md).

Ubuntu18 and Ubuntu20 each passed complete unattended UEFI/TCG installation
and a separate cold boot on the final v1.4 ISO, including both SSH logins,
static IPv4/DNS, services and an unchanged larger second disk. The delivered
validation archive records the exact ISO hash, 22 helper checks, ten UI cases
and twelve inherited menu captures. The physical/iLO and legacy BIOS full
install qualification limits are described in the v1.4 guide.

## Source and build

Use `scripts/build-oneboot-v1.4-vps.py` with an isolated
`ONEBOOT_PROJECT_ROOT=/srv/oneboot/staging/oneboot-v1.4-autoinstall-<date>`.
It requires the existing verified OneBoot asset store, pinned iPXE commit
`8958a4a66022640d622dec1ad5f2ddf77adfcd0f` and the listed host build tools.
Large OS images are external verified inputs. The corresponding source
archive includes the pinned iPXE source and public build certificates.

`scripts/prepare-oneboot-v1.4-legacy-assets.py` builds the separate automatic
18/20 initrds from pinned Canonical inputs. The publishing workflow checks
hashes and module ABI and publishes a new immutable boot resource revision.
It contains no per-server credential.

Run the helper checks and actual-ISO verifier described in the v1.4 guide.
Disposable VM tests use virtual disks only; they verify first boot, both SSH
logins, static network, DNS and secondary-disk sentinels.

Flux source is retained at commit
`594deb47a8d6e73d6597168733248fec4f572608`, with its GPL license and attribution
in `vendor/fluxbilling` and `NOTICE-FLUXBILLING.md`.
