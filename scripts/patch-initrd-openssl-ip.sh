#!/usr/bin/env bash
set -euo pipefail
umask 0027

if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 INPUT_INITRD OUTPUT_INITRD" >&2
  exit 2
fi

readonly input_initrd="$1"
readonly output_initrd="$2"
readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly wrapper_source="${source_root}/initramfs/usr/bin/openssl"

if [[ ! -r "${input_initrd}" ]]; then
  echo "Input initrd is missing or unreadable: ${input_initrd}" >&2
  exit 1
fi
if [[ ! -r "${wrapper_source}" ]]; then
  echo "OpenSSL wrapper is missing or unreadable: ${wrapper_source}" >&2
  exit 1
fi
if [[ "$(readlink -f -- "${input_initrd}")" == "$(readlink -m -- "${output_initrd}")" ]]; then
  echo "Input and output initrd paths must be different" >&2
  exit 1
fi

required_commands=(cat chmod cpio dd dirname find grep install mktemp mv od readlink sha256sum sort touch tr zstd)
for command_name in "${required_commands[@]}"; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "Missing required command: ${command_name}" >&2
    exit 1
  }
done

readonly output_dir="$(dirname "${output_initrd}")"
install -d -m 0750 "${output_dir}"

work_dir="$(mktemp -d "${output_dir}/.oneboot-initrd-patch.XXXXXXXX")"
case "${work_dir}" in
  "${output_dir}"/.oneboot-initrd-patch.*) ;;
  *)
    echo "Unsafe temporary patch path: ${work_dir}" >&2
    exit 1
    ;;
esac

cleanup() {
  rm -rf -- "${work_dir}"
}
trap cleanup EXIT

readonly rebuilt_root="${work_dir}/rebuilt-root"
readonly rebuilt_main="${work_dir}/main.cpio.zst"
readonly temporary_output="${work_dir}/patched-initrd"

read_hex() {
  local offset="$1"
  local length="$2"

  dd if="${input_initrd}" bs=1 skip="${offset}" count="${length}" status=none \
    | LC_ALL=C grep -E "^[0-9A-Fa-f]{${length}}$"
}

byte_is_zero() {
  local offset="$1"
  local value

  value="$(
    dd if="${input_initrd}" bs=1 skip="${offset}" count=1 status=none \
      | od -An -tu1 \
      | tr -d '[:space:]'
  )"
  [[ "${value}" == "0" ]]
}

# Ubuntu initrds may start with several uncompressed newc archives followed by
# one compressed main archive. Preserve every early archive byte-for-byte and
# rebuild only the zstd-compressed main archive.
find_main_offset() {
  local start=0
  local end=0
  local magic
  local namesize_hex
  local filesize_hex
  local namesize
  local filesize

  while true; do
    end=${start}

    while true; do
      if byte_is_zero "${end}"; then
        end=$((end + 4))
        while byte_is_zero "${end}"; do
          end=$((end + 4))
        done
        break
      fi

      if ! magic="$(read_hex "${end}" 6)"; then
        break
      fi
      if [[ "${magic}" != "070701" && "${magic}" != "070702" ]]; then
        break
      fi

      namesize_hex="$(read_hex "$((end + 94))" 8)"
      filesize_hex="$(read_hex "$((end + 54))" 8)"
      namesize=$((16#${namesize_hex}))
      filesize=$((16#${filesize_hex}))
      end=$((end + 110))
      end=$(((end + namesize + 3) & ~3))
      end=$(((end + filesize + 3) & ~3))
    done

    if [[ "${end}" -eq "${start}" ]]; then
      break
    fi
    start=${end}
  done

  echo "${end}"
}

readonly main_offset="$(find_main_offset)"
if [[ "${main_offset}" -le 0 ]]; then
  echo "Could not locate the compressed main archive in ${input_initrd}" >&2
  exit 1
fi

if ! dd if="${input_initrd}" bs=4M iflag=skip_bytes skip="${main_offset}" status=none \
    | zstd --quiet --test; then
  echo "The main initrd archive is not a valid zstd stream" >&2
  exit 1
fi

install -d -m 0755 "${rebuilt_root}"
dd if="${input_initrd}" bs=4M iflag=skip_bytes skip="${main_offset}" status=none \
  | zstd --quiet --decompress --stdout \
  | (
      cd "${rebuilt_root}"
      cpio --extract --make-directories --no-absolute-filenames --quiet
    )

if [[ ! -x "${rebuilt_root}/usr/bin/openssl" ]]; then
  echo "The original /usr/bin/openssl is missing from the initrd" >&2
  exit 1
fi
if [[ -e "${rebuilt_root}/usr/bin/openssl.real" ]]; then
  echo "Refusing to overwrite an existing /usr/bin/openssl.real" >&2
  exit 1
fi
mv -- "${rebuilt_root}/usr/bin/openssl" "${rebuilt_root}/usr/bin/openssl.real"
install -m 0755 "${wrapper_source}" "${rebuilt_root}/usr/bin/openssl"
# Keep archive metadata deterministic across patch runs. The wrapper replaces
# the original command, so reuse the original binary's timestamp instead of
# the wall-clock time assigned by install(1).
touch -r "${rebuilt_root}/usr/bin/openssl.real" "${rebuilt_root}/usr/bin/openssl"

(
  cd "${rebuilt_root}"
  # cpio records directory and file mtimes. Normalize them after replacing
  # OpenSSL so two runs over the same Canonical initrd are byte-identical.
  find . -mindepth 1 -exec touch -h -d '@0' {} +
  find . -mindepth 1 -print0 \
    | LC_ALL=C sort -z \
    | cpio --null --create --format=newc --owner=0:0 --reproducible \
    | zstd --quiet --compress -19 --threads=0 --stdout \
        > "${rebuilt_main}"
)

dd if="${input_initrd}" bs=4M iflag=count_bytes count="${main_offset}" status=none \
  > "${temporary_output}"
cat "${rebuilt_main}" >> "${temporary_output}"
chmod 0440 "${temporary_output}"
mv -f -- "${temporary_output}" "${output_initrd}"

echo "Patched initrd created: ${output_initrd}"
sha256sum "${output_initrd}"
