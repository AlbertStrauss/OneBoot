# OneBoot v1.4.1

Standalone BIOS/UEFI bootstrap ISO with static NIC/IP setup and Ubuntu
Manual/Auto selection. This patch restores **VPS first for every Ubuntu entry**.
GitHub and public mirrors are additional, explicitly selected fallback sources.

If a VPS boot fetch fails, the untimed menu offers Show fetch details, Retry VPS,
Try fallback, Edit network, Select NIC and Back. A failed full ISO fetch after
the kernel starts also waits for the operator: r+Enter retries VPS and f+Enter
allows public fallback. No public mirror probe/race runs before that choice.

Manual remains interactive and uses the VPS Full ISO path. Auto retains the
hostname, visible password entered twice, explicit Go, first eligible fixed
disk and chosen root/user password SSH. Ubuntu18/20 Auto uses the classic
preseed installer; Ubuntu22/24/26 use the existing live/Subiquity installer.
The ISO contains OneBoot directly, without netboot.xyz.

See [the v1.4.1 guide](docs/ONEBOOT-V1.4.1-VPS-FIRST.md) for exact source rules,
classic package downloads, legacy manual fallback behavior and validation scope.
The exact ISO passed full unattended Ubuntu24/26 UEFI installation and cold-boot
checks from VPS, interactive Manual boot checks for both, eight policy tests,
and all 24 BIOS/UEFI VPS-failure menu/source tests. See the guide for limits.
Earlier v1.4/v1.3 guides retain historical qualification results; their old
GitHub-first source policy is superseded here.

## Source and build

Build in a new isolated `ONEBOOT_PROJECT_ROOT` named
`/srv/oneboot/staging/oneboot-v1.4.1-autoinstall-<date>` with
`scripts/build-oneboot-v1.4.1-vps.py`. Verified baseline OS assets are external
inputs; existing payloads are not overwritten. The versioned legacy download
handlers are prepared as root by `scripts/prepare-oneboot-v1.4.1-vps-assets.py`,
which preserves the existing asset store owner and web-readable group.

The source archive includes public build inputs, attribution and the pinned
upstream iPXE source. `scripts/verify-oneboot-v1.4.1.py` inspects the actual ISO;
`scripts/test-oneboot-vps-policy.py` executes the gated download policy and C
profile retry; `scripts/test-oneboot-vps-fault-ui.py` records actual-ISO source
failure menus and traffic. Full test runs use disposable virtual disks only.

Flux source remains pinned at `594deb47a8d6e73d6597168733248fec4f572608`, with
its GPL license and attribution in `vendor/fluxbilling` and
`NOTICE-FLUXBILLING.md`. Physical server/controller/iLO qualification is separate
from the recorded VM checks.
