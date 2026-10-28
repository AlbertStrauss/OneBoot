#!/usr/bin/env bash
set -euo pipefail
umask 0027

readonly RELEASE_VERSION="1.0"
readonly EXPECTED_IPXE_COMMIT="8958a4a66022640d622dec1ad5f2ddf77adfcd0f"
readonly PROJECT_ROOT="${ONEBOOT_PROJECT_ROOT:-/srv/oneboot}"
readonly SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ASSET_ROOT="${PROJECT_ROOT}/assets"
readonly BUILD_ROOT="${PROJECT_ROOT}/build"
readonly RELEASE_ROOT="${PROJECT_ROOT}/releases/v${RELEASE_VERSION}"
readonly IPXE_ROOT="${PROJECT_ROOT}/toolchain/ipxe"
readonly BASE_URL="${ONEBOOT_BASE_URL:-https://93.114.194.66/oneboot}"

# Do not inherit an inaccessible caller directory (for example /root) when the
# build is intentionally run as the unprivileged oneboot user.
cd "${SOURCE_ROOT}"

if [[ -e "${RELEASE_ROOT}/QUALIFIED.txt" || -e "${RELEASE_ROOT}/DELIVERED.txt" ]]; then
  echo 'OneBoot 1.0 is already delivered; create a new release instead of replacing it.' >&2
  exit 1
fi

case "${BASE_URL}" in
  https://*) ;;
  *)
    echo "ONEBOOT_BASE_URL must start with https://" >&2
    exit 1
    ;;
esac

if [[ "${BASE_URL}" =~ [[:space:]\&\|\;] ]] || [[ "${BASE_URL}" == */ ]]; then
  echo "ONEBOOT_BASE_URL must not contain whitespace, shell separators, or a trailing slash" >&2
  exit 1
fi

required_commands=(git make gcc sha256sum sed grep xorriso mformat mmd mcopy install mktemp truncate flock python3)
for command_name in "${required_commands[@]}"; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "Missing required command: ${command_name}" >&2
    exit 1
  }
done

required_files=(
  "${SOURCE_ROOT}/src/oneboot-v1.0.ipxe.in"
  "${SOURCE_ROOT}/ipxe/oneboot_autonet_cmd.c"
  "${SOURCE_ROOT}/ipxe/oneboot_error_cmd.c"
  "${SOURCE_ROOT}/src/isolinux.cfg"
  "${SOURCE_ROOT}/assets/oneboot-background-v1.0.png"
  "${SOURCE_ROOT}/config/branding-v1.0.sha256"
  "${SOURCE_ROOT}/scripts/verify-oneboot-v1.0-scope.py"
  "${SOURCE_ROOT}/config/ipxe-console.h"
  "${SOURCE_ROOT}/config/ipxe-general.h"
  "${SOURCE_ROOT}/config/ubuntu-assets.sha256"
  "${SOURCE_ROOT}/config/tools-assets.sha256"
  "${SOURCE_ROOT}/config/winpe-assets.sha256"
  "${SOURCE_ROOT}/config/minitool-source.sha256"
  "${SOURCE_ROOT}/config/almalinux-source.sha256"
  "${SOURCE_ROOT}/config/almalinux-assets.sha256"
  "${SOURCE_ROOT}/config/debian-source-iso.sha256"
  "${SOURCE_ROOT}/config/debian-assets.sha256"
  "${SOURCE_ROOT}/config/ubuntu-upstream-initrd.sha256"
  "${SOURCE_ROOT}/initramfs/usr/bin/openssl"
  "${SOURCE_ROOT}/scripts/patch-initrd-openssl-ip.sh"
  "${IPXE_ROOT}/src/Makefile"
  "/usr/lib/ISOLINUX/isohdpfx.bin"
  "/usr/lib/ISOLINUX/isolinux.bin"
  "/usr/lib/syslinux/modules/bios/ldlinux.c32"
)
for required_file in "${required_files[@]}"; do
  [[ -r "${required_file}" ]] || {
    echo "Required file is missing or unreadable: ${required_file}" >&2
    exit 1
  }
done

actual_ipxe_commit="$(git -C "${IPXE_ROOT}" rev-parse HEAD)"
if [[ "${actual_ipxe_commit}" != "${EXPECTED_IPXE_COMMIT}" ]]; then
  echo "Unexpected iPXE commit: ${actual_ipxe_commit}" >&2
  echo "Expected: ${EXPECTED_IPXE_COMMIT}" >&2
  exit 1
fi

if ! git -C "${IPXE_ROOT}" diff --quiet --no-ext-diff -- ||
   ! git -C "${IPXE_ROOT}" diff --cached --quiet --no-ext-diff --; then
  echo "The pinned iPXE checkout has tracked modifications; refusing to build" >&2
  exit 1
fi

python3 "${SOURCE_ROOT}/scripts/verify-oneboot-v1.0-scope.py" "${SOURCE_ROOT}"
python3 "${SOURCE_ROOT}/scripts/verify-oneboot-download-diagnostics.py" "${SOURCE_ROOT}"
(
  cd "${SOURCE_ROOT}"
  sha256sum --check --strict "config/branding-v1.0.sha256"
)

echo "Verifying pinned Proxmox assets..."
(cd "${ASSET_ROOT}" && sha256sum --check --quiet "${SOURCE_ROOT}/config/proxmox-assets.sha256")
bash "${SOURCE_ROOT}/scripts/verify-proxmox-initrds-vps.sh"
(cd "${ASSET_ROOT}" && sha256sum --check --strict "${SOURCE_ROOT}/config/proxmox-oneboot-bootstrap.sha256")
python3 "${SOURCE_ROOT}/scripts/prepare-proxmox-bootstrap.py" --verify
echo "Verifying pinned Ubuntu assets..."
(
  cd "${ASSET_ROOT}/ubuntu"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/ubuntu-assets.sha256"
)
echo "Verifying pinned Ubuntu 18/20 legacy assets..."
(
  cd "${ASSET_ROOT}"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/ubuntu-legacy-assets.sha256"
)
echo "Verifying pinned Tools assets..."
(
  cd "${ASSET_ROOT}"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/tools-assets.sha256"
)
echo "Verifying pinned Windows PE assets..."
(
  cd "${ASSET_ROOT}"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/winpe-assets.sha256"
)
echo "Verifying pinned AlmaLinux assets..."
(
  cd "${ASSET_ROOT}"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/almalinux-assets.sha256"
)
echo "Verifying pinned Debian netboot assets..."
(
  cd "${ASSET_ROOT}"
  sha256sum --check --quiet "${SOURCE_ROOT}/config/debian-assets.sha256"
)
background_sha256="$(sha256sum "${SOURCE_ROOT}/assets/oneboot-background-v1.0.png")"
background_sha256="${background_sha256%% *}"
readonly background_sha256
autonet_source_sha256="$(sha256sum "${SOURCE_ROOT}/ipxe/oneboot_autonet_cmd.c")"
autonet_source_sha256="${autonet_source_sha256%% *}"
readonly autonet_source_sha256

install -d -m 0750 "${BUILD_ROOT}" "${RELEASE_ROOT}"
exec 9> "${BUILD_ROOT}/oneboot-v${RELEASE_VERSION}.lock"
if ! flock -n 9; then
  echo "Another OneBoot v${RELEASE_VERSION} build is already running" >&2
  exit 1
fi

work_dir="$(mktemp -d "${BUILD_ROOT}/oneboot-v${RELEASE_VERSION}.XXXXXXXX")"
case "${work_dir}" in
  "${BUILD_ROOT}"/oneboot-v${RELEASE_VERSION}.*) ;;
  *)
    echo "Unsafe temporary build path: ${work_dir}" >&2
    exit 1
    ;;
esac

cleanup() {
  if [[ "${ipxe_console_installed:-0}" -eq 1 ]]; then
    if [[ "${ipxe_console_existed:-0}" -eq 1 ]]; then
      install -m 0644 "${ipxe_console_backup}" "${ipxe_local_console}"
    else
      rm -f -- "${ipxe_local_console}"
    fi
  fi
  if [[ "${ipxe_general_installed:-0}" -eq 1 ]]; then
    if [[ "${ipxe_general_existed:-0}" -eq 1 ]]; then
      install -m 0644 "${ipxe_general_backup}" "${ipxe_local_general}"
    else
      rm -f -- "${ipxe_local_general}"
    fi
  fi
  if [[ "${ipxe_autonet_installed:-0}" -eq 1 ]]; then
    if [[ "${ipxe_autonet_existed:-0}" -eq 1 ]]; then
      install -m 0644 "${ipxe_autonet_backup}" "${ipxe_autonet_source}"
    else
      rm -f -- "${ipxe_autonet_source}"
    fi
  fi
  if [[ "${ipxe_error_installed:-0}" -eq 1 ]]; then
    if [[ "${ipxe_error_existed:-0}" -eq 1 ]]; then
      install -m 0644 "${ipxe_error_backup}" "${ipxe_error_source}"
    else
      rm -f -- "${ipxe_error_source}"
    fi
  fi
  if [[ "${ipxe_config_patched:-0}" -eq 1 ]]; then
    install -m 0644 "${ipxe_config_backup}" "${ipxe_config_source}"
  fi
  rm -rf -- "${work_dir}"
}
trap cleanup EXIT

readonly embedded_script="${BUILD_ROOT}/oneboot-v${RELEASE_VERSION}.ipxe.build"
readonly iso_root="${work_dir}/iso-root"
readonly esp_image="${iso_root}/oneboot-esp.img"
readonly ipxe_local_console="${IPXE_ROOT}/src/config/local/console.h"
readonly ipxe_console_backup="${work_dir}/ipxe-console.h.original"
readonly ipxe_local_general="${IPXE_ROOT}/src/config/local/general.h"
readonly ipxe_general_backup="${work_dir}/ipxe-general.h.original"
readonly ipxe_autonet_source="${IPXE_ROOT}/src/hci/commands/oneboot_autonet_cmd.c"
readonly ipxe_autonet_backup="${work_dir}/oneboot_autonet_cmd.c.original"
readonly ipxe_error_source="${IPXE_ROOT}/src/hci/commands/oneboot_error_cmd.c"
readonly ipxe_error_backup="${work_dir}/oneboot_error_cmd.c.original"
readonly ipxe_config_source="${IPXE_ROOT}/src/config/config.c"
readonly ipxe_config_backup="${work_dir}/config.c.original"
ipxe_console_existed=0
ipxe_console_installed=0
ipxe_general_existed=0
ipxe_general_installed=0
ipxe_autonet_existed=0
ipxe_autonet_installed=0
ipxe_error_existed=0
ipxe_error_installed=0
ipxe_config_patched=0

if [[ -e "${ipxe_local_console}" ]]; then
  install -m 0644 "${ipxe_local_console}" "${ipxe_console_backup}"
  ipxe_console_existed=1
fi
install -m 0644 "${SOURCE_ROOT}/config/ipxe-console.h" "${ipxe_local_console}"
ipxe_console_installed=1

if [[ -e "${ipxe_local_general}" ]]; then
  install -m 0644 "${ipxe_local_general}" "${ipxe_general_backup}"
  ipxe_general_existed=1
fi
install -m 0644 "${SOURCE_ROOT}/config/ipxe-general.h" "${ipxe_local_general}"
ipxe_general_installed=1

if [[ -e "${ipxe_autonet_source}" ]]; then
  install -m 0644 "${ipxe_autonet_source}" "${ipxe_autonet_backup}"
  ipxe_autonet_existed=1
fi
install -m 0644 "${SOURCE_ROOT}/ipxe/oneboot_autonet_cmd.c" "${ipxe_autonet_source}"
ipxe_autonet_installed=1

if [[ -e "${ipxe_error_source}" ]]; then
  install -m 0644 "${ipxe_error_source}" "${ipxe_error_backup}"
  ipxe_error_existed=1
fi
install -m 0644 "${SOURCE_ROOT}/ipxe/oneboot_error_cmd.c" "${ipxe_error_source}"
ipxe_error_installed=1

# iPXE command objects live in a static archive and are linked only when a
# configuration object explicitly requires them.  Apply this release-local
# requirement after the clean-tree check, then restore the pinned source in
# cleanup so older release rebuilds remain byte-for-byte reproducible.
install -m 0644 "${ipxe_config_source}" "${ipxe_config_backup}"
ipxe_config_patched=1
sed -i '/^PROVIDE_REQUIRING_SYMBOL();$/a REQUIRE_OBJECT ( oneboot_autonet_cmd );' \
  "${ipxe_config_source}"
sed -i '/^PROVIDE_REQUIRING_SYMBOL();$/a REQUIRE_OBJECT ( oneboot_error_cmd );' \
  "${ipxe_config_source}"
if [[ "$(grep -Fc 'REQUIRE_OBJECT ( oneboot_autonet_cmd );' "${ipxe_config_source}")" -ne 1 ]]; then
  echo "Failed to add the OneBoot autonet link requirement" >&2
  exit 1
fi
if [[ "$(grep -Fc 'REQUIRE_OBJECT ( oneboot_error_cmd );' "${ipxe_config_source}")" -ne 1 ]]; then
  echo "Failed to add the OneBoot error-report command link requirement" >&2
  exit 1
fi

sed "s|@@BASE_URL@@|${BASE_URL}|g" \
  "${SOURCE_ROOT}/src/oneboot-v1.0.ipxe.in" > "${embedded_script}"

if grep -q '@@BASE_URL@@' "${embedded_script}"; then
  echo "The embedded script still contains an unresolved URL token" >&2
  exit 1
fi

export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH="$(git -C "${IPXE_ROOT}" show -s --format=%ct HEAD)"

echo "Building pinned iPXE BIOS and x86_64 UEFI binaries..."
readonly embedded_files="${embedded_script},${SOURCE_ROOT}/assets/oneboot-background-v1.0.png"
make -C "${IPXE_ROOT}/src" -j"$(nproc)" bin/ipxe.lkrn EMBED="${embedded_files}"
make -C "${IPXE_ROOT}/src" -j"$(nproc)" bin-x86_64-efi/ipxe.efi EMBED="${embedded_files}"

install -d -m 0755 "${iso_root}/boot" "${iso_root}/isolinux" "${iso_root}/EFI/BOOT"
install -m 0644 "${IPXE_ROOT}/src/bin/ipxe.lkrn" "${iso_root}/boot/ipxe.lkrn"
install -m 0644 "${IPXE_ROOT}/src/bin-x86_64-efi/ipxe.efi" "${work_dir}/BOOTX64.EFI"
install -m 0644 "${work_dir}/BOOTX64.EFI" "${iso_root}/EFI/BOOT/BOOTX64.EFI"
install -m 0644 "/usr/lib/ISOLINUX/isolinux.bin" "${iso_root}/isolinux/isolinux.bin"
install -m 0644 "/usr/lib/syslinux/modules/bios/ldlinux.c32" "${iso_root}/isolinux/ldlinux.c32"
install -m 0644 "${SOURCE_ROOT}/src/isolinux.cfg" "${iso_root}/isolinux/isolinux.cfg"
install -m 0644 "${embedded_script}" "${iso_root}/oneboot.ipxe"
install -m 0644 "${SOURCE_ROOT}/assets/oneboot-background-v1.0.png" "${iso_root}/oneboot-background-v1.0.png"
install -m 0644 "${SOURCE_ROOT}/config/branding-v1.0.sha256" "${iso_root}/branding-v1.0.sha256"
install -m 0644 "${SOURCE_ROOT}/config/ubuntu-assets.sha256" "${iso_root}/ubuntu-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/ubuntu-upstream-initrd.sha256" \
  "${iso_root}/ubuntu-upstream-initrd.sha256"
install -m 0644 "${SOURCE_ROOT}/config/tools-assets.sha256" \
  "${iso_root}/tools-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/winpe-assets.sha256" \
  "${iso_root}/winpe-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/minitool-source.sha256" \
  "${iso_root}/minitool-source.sha256"
install -m 0644 "${SOURCE_ROOT}/config/almalinux-source.sha256" \
  "${iso_root}/almalinux-source.sha256"
install -m 0644 "${SOURCE_ROOT}/config/almalinux-assets.sha256" \
  "${iso_root}/almalinux-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/debian-source-iso.sha256" \
  "${iso_root}/debian-source-iso.sha256"
install -m 0644 "${SOURCE_ROOT}/config/debian-assets.sha256" \
  "${iso_root}/debian-assets.sha256"

install -m 0644 "${SOURCE_ROOT}/config/ubuntu-legacy-assets.sha256" "${iso_root}/ubuntu-legacy-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/proxmox-assets.sha256" "${iso_root}/proxmox-assets.sha256"
install -m 0644 "${SOURCE_ROOT}/config/proxmox-source.sha256" "${iso_root}/proxmox-source.sha256"
install -m 0644 "${SOURCE_ROOT}/config/proxmox-initrd-content.sha256" "${iso_root}/proxmox-initrd-content.sha256"
install -m 0644 "${SOURCE_ROOT}/config/proxmox-oneboot-bootstrap.sha256" "${iso_root}/proxmox-oneboot-bootstrap.sha256"
truncate -s 4M "${esp_image}"
mformat -i "${esp_image}" -v ONEBOOT ::
mmd -i "${esp_image}" ::/EFI ::/EFI/BOOT
mcopy -i "${esp_image}" "${work_dir}/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI

{
  printf 'OneBoot release: v%s\n' "${RELEASE_VERSION}"
  printf 'Release scope: OneBoot 1.0 with the white boot logo and monochrome theme; Proxmox menu is explicitly Testing; the proven RAM-root correction is retained for Proxmox 7/8/9.\n'
  printf 'Release status: TESTING / NOT HARDWARE-QUALIFIED; real-hardware installation and first boot are operator tests and are not yet qualified.\n'
  printf 'Proxmox: original ISO/kernel/gzip archive retained; minimal /init override recognizes root=/dev/ram0 as the RAM ISO installer selector. No rootfstype or initrd command-line parameter is passed to the installed system. Interactive installation; final network remains manual.\n'
  printf 'Download base URL: %s\n' "${BASE_URL}"
  printf 'Pinned iPXE commit: %s\n' "${actual_ipxe_commit}"
  printf 'OneBoot autonet command SHA256: %s\n' "${autonet_source_sha256}"
  printf 'OneBoot autonet linkage: release-local REQUIRE_OBJECT in pinned config.c (restored after build)\n'
  printf 'Download diagnostics: exact iPXE error/URL/network snapshot retained in RAM; error screens wait for Esc; main menu can re-display the last error.\n'
  printf 'Brand background SHA256: %s\n' "${background_sha256}"
  printf 'Build timestamp (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '\nSafety: interactive Ubuntu, AlmaLinux, Debian and Proxmox installers plus recovery tools; no disk automation.\n'
  printf 'Boot payload security: authenticated HTTPS is mandatory; no HTTP fallback is allowed.\n'
  printf 'Initrd compatibility: OpenSSL IP verification keeps certificate checks enabled.\n'
  printf 'Linux Rescue: SystemRescue 13.02; SHA-512 verification enabled at boot.\n'
  printf 'Linux Rescue memory: at least 4 GiB RAM; 8 GiB recommended.\n'
  printf 'Memory Test: Memtest86+ 8.10; no disk access.\n'
  printf 'Windows PE: Microsoft ADK 10.1.26100.2454, serviced with KB5101684.\n'
  printf 'Windows PE loader: official iPXE wimboot 2.9.0.\n'
  printf 'MiniTool: Partition Wizard 12.3.0 WinPE; third-party operator-supplied image.\n'
  printf 'AlmaLinux: 8.10, 9.8, and 10.2 Minimal installation trees over HTTPS.\n'
  printf 'AlmaLinux source: signed official CHECKSUM files and pinned extracted-asset hashes.\n'
  printf 'Ubuntu legacy: 18.04.6/20.04.6 original ISOs to RAM via verified HTTPS and pinned SHA256; isolated initrd compatibility overlays.\n'
  printf 'Ubuntu netboot: signed bionic-updates/focal-updates kernel/initrd; Ubuntu signed HTTP package repositories; no disk automation.\n'
  printf 'Debian: 10.13, 11.11, 12.15, and 13.6 official netboot installers.\n'
  printf 'Debian source: signed Release metadata, signed SHA256SUMS chain, and pinned hosted assets.\n'
  printf 'Debian network: OneBoot downloads only the kernel/initrd; Debian Installer asks for NIC and static IPv4 settings without prefilled values.\n'
  printf 'Debian package source: country, mirror, directory and proxy are selected interactively; no full ISO is loaded into RAM.\n'
  printf 'Network defaults: IPv4/prefix input, calculated editable gateway, and 8.8.8.8 DNS.\n'
  printf 'Gateway rule: network+1 for /8-/30, first address for /31, manual for /32.\n'
  printf 'UEFI Secure Boot: unsupported until the custom EFI loader is trusted.\n'
} > "${iso_root}/BUILD-INFO.txt"

cat > "${iso_root}/TESTING-NOTICE.txt" <<'EOF'
OneBoot 1.0

Status: TESTING / NOT HARDWARE-QUALIFIED.
Proxmox VE 7.4, 8.4 and 9.2 retain the v0.9.5 RAM-root correction, but the
operator must validate a complete installation and a cold first boot on real
hardware. This testing release must not be represented as a qualified Proxmox release.
Debian remains fully interactive after the initial OneBoot kernel/initrd
download. No installer in this ISO receives an unattended disk policy.
EOF

readonly release_iso="${RELEASE_ROOT}/oneboot-v${RELEASE_VERSION}.iso"
readonly temporary_iso="${work_dir}/oneboot-v${RELEASE_VERSION}.iso"

(cd "${iso_root}" && sha256sum boot/ipxe.lkrn EFI/BOOT/BOOTX64.EFI > BOOT-LOADERS.sha256)

echo "Creating hybrid BIOS/UEFI ISO..."
xorriso -as mkisofs \
  -o "${temporary_iso}" \
  -V ONEBOOT_1_0 \
  -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
  -c isolinux/boot.cat \
  -b isolinux/isolinux.bin \
  -no-emul-boot \
  -boot-load-size 4 \
  -boot-info-table \
  -eltorito-alt-boot \
  -e oneboot-esp.img \
  -no-emul-boot \
  -isohybrid-gpt-basdat \
  "${iso_root}"

# Publish by rename so a validation VM already using the previous candidate
# keeps its original ISO inode intact while a new candidate is built.
install -m 0440 "${temporary_iso}" "${release_iso}.new"
mv -f -- "${release_iso}.new" "${release_iso}"
install -m 0440 "${embedded_script}" "${RELEASE_ROOT}/oneboot-v${RELEASE_VERSION}.ipxe"
install -m 0440 "${iso_root}/BUILD-INFO.txt" "${RELEASE_ROOT}/BUILD-INFO.txt"
install -m 0440 "${iso_root}/TESTING-NOTICE.txt" "${RELEASE_ROOT}/TESTING-NOTICE.txt"
install -m 0440 "${iso_root}/BOOT-LOADERS.sha256" "${RELEASE_ROOT}/BOOT-LOADERS.sha256"
(
  cd "${RELEASE_ROOT}"
  sha256sum "$(basename "${release_iso}")" > "${work_dir}/oneboot-v${RELEASE_VERSION}.iso.sha256"
)
install -m 0440 "${work_dir}/oneboot-v${RELEASE_VERSION}.iso.sha256" \
  "${release_iso}.sha256"

echo
echo "OneBoot v${RELEASE_VERSION} created successfully:"
ls -lh "${release_iso}" "${release_iso}.sha256"
sha256sum "${release_iso}"
