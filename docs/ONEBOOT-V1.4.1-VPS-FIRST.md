# OneBoot v1.4.1 — VPS first, operator-selected fallback

Qualified patch ISO: SHA256
`8306d1464ef77dc69c6c4db1a113298ab8ed514c15addf57f58c2cb4cda71107`.
The delivery validation records completed paths and their limits.

Every Ubuntu entry starts with the operator's VPS at
`https://93.114.194.66/oneboot`. This includes Manual, Auto and the separate
18/20 Net entries. Selecting an OS or confirming Auto never selects GitHub as
the initial boot source.

If a required VPS boot file fails, OneBoot holds an untimed menu. It offers
Show fetch details, Retry VPS, Try fallback, Edit network, Select another NIC
and Back. Back is the default. Show fetch details displays the exact operation,
URL, iPXE error code and selected network. No cleanup command prints a spurious
missing kboot/iboot message.

The same rule applies to the full ISO fetch after the kernel starts. A failed
VPS fetch, invalid SHA256, or incompatible ISO holds a console prompt. Type
`r` and Enter to retry VPS, `f` and Enter to allow public fallback, or `s` and
Enter for the native diagnostic shell. No public speed probe, mirror race or
automatic source switch runs on the VPS path. Detailed logs are kept in RAM at
`/run/oneboot-download.log`; download errors are also printed to the consoles.
The kernel-stage prompt continues in that installer because iPXE has already
handed over control.

## Sources and installer behavior

| Selection | Initial VPS source | Explicit fallback |
| --- | --- | --- |
| Ubuntu22/24/26 Manual or Auto | Existing paired kernel/patched initrd and exact full ISO | GitHub paired boot files; exact Canonical ISO and configured release mirrors |
| Ubuntu18/20 Manual Full ISO | Existing kernel and full ISO; a separately versioned initrd adds the gated download handler | iPXE failure: official interactive classic Net installer; ISO-stage failure: exact Canonical Full ISO |
| Ubuntu18/20 Auto | VPS netboot kernel and byte-identical qualified v1.4 R4 automatic initrd | The same kernel/automatic initrd from the pinned GitHub R4 resource |
| Ubuntu18/20 separate Manual Net entries | Existing VPS netboot kernel/initrd | Official Ubuntu archive netboot files |

Classic Net/Auto installation packages come from the signed Ubuntu archive.
The VPS does not contain an APT package mirror. This package source is separate
from the boot files and full ISO source selection above.

Fallback always requests the pinned release filename, not a latest alias or a
new point release. The full ISO is checked against the pinned SHA256 before it
is used. Modern casper media must also pass its original installer UUID check.
The public ISO candidates are Canonical and four configured release mirrors;
they are tried only after the operator permits fallback, in the listed order.

Manual remains interactive, with no automatic disk layout. Auto keeps the
visible password entered twice, hostname, static NIC/IP and explicit Go review.
It selects only the first eligible fixed disk, configures boot/root and chosen
root/user password SSH, and retains the existing busy/LVM/RAID stop behavior.
A bounded private RAM profile survives a fetch retry or source change. Going
Back to mode selection clears it. Passwords are absent from kernel arguments,
public boot resources and the ISO.

The old VPS assets and older delivered ISOs are preserved. New legacy download
handlers live under the separate `ubuntu/oneboot-v1.4.1/` resource directory.
Non-Ubuntu menu/boot paths remain unchanged.

## Qualification and scope

`scripts/test-oneboot-vps-policy.py` executes the actual shell handler with a
blocked input FIFO and mocked network. It checks VPS success without public
requests, a held failure until `f`, VPS-only retry, bad-hash rejection, explicit
fallback, unrelated-casper behavior and the actual C private-profile retry.

`scripts/test-oneboot-vps-fault-ui.py` boots the actual ISO without disks and
records every Ubuntu mode's VPS failure, its untimed choices and network
captures before/after explicit fallback in BIOS and UEFI. Captures require
visual review. `scripts/verify-oneboot-v1.4.1.py` checks the actual hybrid ISO,
embedded helper/certificate bytes, source policy and versioned VPS assets.

Full-install qualification uses disposable 24-GiB first and protected 64-GiB
second disks, a separate cold boot without ISO, chosen root/user password SSH,
static IPv4/routes/DNS, APT and services. The delivery validation records which
versions and paths actually completed; boot/menu checks are not full installs.
Physical server/controller/iLO behavior requires separate qualification.

The exact delivered ISO completed clean, unattended Ubuntu24 and Ubuntu26 Auto
installations in UEFI VMs using the VPS kernel, initrd and full ISO, followed by
cold boot without the ISO. Both passed chosen root/user password SSH, first-disk
boot/root layout, static IPv4/routes/DNS, APT/security sources and active network
and SSH services; the separate larger disk remained unchanged. No guest input
was sent after Go. The same ISO reached the interactive language screen in
Ubuntu24 and Ubuntu26 Manual and left both test disks unwritten. Those Manual
checks are boot checks, not complete Manual installations.

All 24 VPS-failure cases (12 entries/modes in each of BIOS and UEFI) passed
with visually reviewed captures and network evidence: no public source before
explicit fallback, a held error menu, working details, and GitHub contact only
after fallback was selected. Twelve mode/password/review captures were also
reviewed. All eight source-policy/private-profile tests passed. All four new
legacy resource URLs returned HTTP200 after matching the existing asset store's
Nginx-readable group; file content hashes were unchanged.

Full BIOS installs, new full Ubuntu18/20/22 installs and physical hardware are
not newly qualified by this patch. Package downloads in classic installers
still require access to signed Ubuntu archives. Existing access rules remain
in force. A temporary test-PC /32 was removed after download checks.

The original v1.4 qualification and its limits remain historical evidence for
the byte-identical classic Auto payloads. Its old GitHub-first source policy is
superseded by this version. Existing v1.3 BIOS26 full/unattended limitations are
not erased by a new menu or a successful UEFI test.

Flux source attribution and GPL terms remain in `NOTICE-FLUXBILLING.md` and
`vendor/fluxbilling`. The fixed upstream source revision is unchanged.
