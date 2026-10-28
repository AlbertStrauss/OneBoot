#!/usr/bin/env bash
set -euo pipefail
readonly ROOT=/srv/oneboot
while read -r expected version; do
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
  case "$version" in 9.2-1|8.4-1|7.4-1) ;; *) exit 1 ;; esac
  actual="$(gzip -dc "$ROOT/assets/proxmox/$version/initrd-pxe.img" | sha256sum)"
  [[ "${actual%% *}" == "$expected" ]]
  original="$(zstd -dc "$ROOT/assets/proxmox/$version/initrd.img" | sha256sum)"
  [[ "$actual" == "$original" ]]
  echo "$version: gzip and upstream Zstandard archives decompress to the exact pinned bytes"
done < "$ROOT/src/config/proxmox-initrd-content.sha256"
