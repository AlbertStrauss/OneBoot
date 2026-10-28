# OneBoot

OneBoot v1.3 is being rebuilt as a small standalone BIOS/UEFI boot ISO with optional Ubuntu autoinstall, adapted from the GPL-licensed [FluxBilling OS Installer](https://github.com/FluxBilling-app/FluxBilling-OS-Installer).

## Current v1.3 scope

Enter NIC and static IPv4 settings, choose Ubuntu 22.04, 24.04 or 26.04, then select **Manual** or **Auto**. Auto asks for hostname and a visible password twice, checks agreement, and requires an explicit **Go** on a review screen.

Auto targets the first eligible fixed disk, with normal boot/root partitions. Other disks are outside its storage layout. The disk selector performs no global wipe or RAID teardown. A busy first disk stops the automatic path for operator review. Manual mode supplies no autoinstall profile.

Credentials are carried in a private RAM file, not the kernel command line. Root and the `user` sudo account receive the confirmed password; this is shown before Go. Source attribution and the GPL license are retained in the project and boot media.

## Paired boot files

The [Ubuntu boot-pair release](https://github.com/AlbertStrauss/OneBoot/releases/tag/ubuntu-live-boot-v1.3) contains unmodified kernel/initrd pairs extracted from the exact Canonical Ubuntu 22.04.5, 24.04.4 and 26.04 ISOs. The publishing workflow checks both the original ISO hash and the extracted file hashes before uploading.

Full Ubuntu images download from Canonical or official mirrors into RAM. The mirror selector accepts fixed release filenames and retains the exact requested version. The downloaded medium must match the boot initrd's UUID. Allow 8 GiB RAM or more on installation servers.

The boot-media candidate is still undergoing disposable-disk installation tests; published boot files alone do not establish that the whole ISO is qualified. Secure Boot and physical-hardware qualification are separate.

The older `ubuntu-24.04.4-oneboot-v1.3` split-image release belongs to an abandoned recovery prototype and is not the current autoinstall download path. No keys or installer credentials belong in this repository.
