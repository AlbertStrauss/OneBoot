# OneBoot

Boot media and verified installer download sources for OneBoot.

## Ubuntu 24 recovery

The [Ubuntu 24.04.4 mirror release](https://github.com/AlbertStrauss/OneBoot/releases/tag/ubuntu-24.04.4-oneboot-v1.3) is published. It contains three ordered parts of the original Canonical amd64 server ISO, plus SHA256SUMS. OneBoot streams the parts into one RAM file and requires the exact original size and SHA256 before mounting it.

- Original ISO: `ubuntu-24.04.4-live-server-amd64.iso`
- Bytes: `3405469696`
- SHA256: `e907d92eeec9df64163a7e454cbc8d7755e8ddc7ed42f99dbc80c40f1a138433`

The complete public GitHub download has been reconstructed and verified against that checksum. The pinned mirrors and source order are in [the manifest](mirrors/ubuntu-24.04.4.json). The publishing workflow verifies Canonical's original file before uploading and refuses to replace an existing release.

## Operator control

The primary source remains the OneBoot VPS. A failure waits for the operator: retry VPS, correct the network/NIC, or press **F** to try alternatives. F permits GitHub Releases, then three official HTTPS mirrors, then their HTTP URLs. Every completed image must match the locally pinned size and SHA256; failed or incorrect downloads are discarded.

OneBoot v1.3's boot-media candidate includes a local Ubuntu 24 kernel/initrd reserve so that alternatives can also be selected when the primary boot files cannot be downloaded. BIOS/UEFI qualification is separate from the mirror publishing workflow. This phase covers Ubuntu 24 only and keeps installation interactive, with no automatic disk policy.

Large installer files belong in GitHub Releases rather than Git history. No installer credentials or private keys belong in this repository.
