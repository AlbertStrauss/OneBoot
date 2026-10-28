#!/usr/bin/env python3
"""Verify the independent OneBoot 1.0 menu and firmware-safe artwork."""
import re
import struct
import sys
import zlib
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
menu_path = root / 'src/oneboot-v1.0.ipxe.in'
background_path = root / 'assets/oneboot-background-v1.0.png'
menu = menu_path.read_text(encoding='utf-8')

required = (
    '#!ipxe',
    'set oneboot_version 1.0',
    'set base_url @@BASE_URL@@',
    'oneboot-background-v1.0.png',
    'OneBoot v${oneboot_version}',
    'oneboot.iso=${ubuntu_iso}',
    'oneboot_legacy=1',
    'init-oneboot-v1.0 /init mode=755',
    'root=/dev/ram0',
    'netcfg/disable_autoconfig=true',
)
for value in required:
    assert value in menu, f'missing required OneBoot behavior: {value}'

for forbidden in ('Fa' + 'stBoot', 'fa' + 'stboot', '/srv/', 'http://', '1.1 (Testing)'):
    assert forbidden not in menu, f'legacy or unsafe menu text remains: {forbidden}'

for version in ('9.2', '8.4', '7.4'):
    assert menu.count(f'Proxmox VE {version} (Testing)') == 1, version

labels = re.findall(r'^:([^\n]+)$', menu, re.MULTILINE)
assert labels and len(labels) == len(set(labels)), 'duplicate iPXE labels'
destinations = []
for line in menu.splitlines():
    if line.startswith('item ') and '--gap ' not in line:
        match = re.match(r'item --menu \S+ --key \S+ (\S+) ', line)
        assert match, line
        destinations.append(match.group(1))
for destination in destinations:
    assert destination in labels, f'menu destination has no label: {destination}'

functional_lines = '\n'.join(
    line.lower() for line in menu.splitlines()
    if line.startswith(('kernel ', 'imgargs ', 'chain ', 'initrd '))
)
for forbidden in (' autoinstall', 'preseed/url=', 'inst.ks=', 'wipefs', 'mkfs.'):
    assert forbidden not in functional_lines, f'unattended or destructive behavior found: {forbidden}'

data = background_path.read_bytes()
assert data.startswith(b'\x89PNG\r\n\x1a\n'), background_path
offset = 8
width = height = None
compressed = bytearray()
while offset < len(data):
    length = struct.unpack('>I', data[offset:offset + 4])[0]
    kind = data[offset + 4:offset + 8]
    payload = data[offset + 8:offset + 8 + length]
    offset += 12 + length
    if kind == b'IHDR':
        width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
        assert (width, height, depth, colour, compression, filtering, interlace) == (1024, 768, 8, 2, 0, 0, 0)
    elif kind == b'IDAT':
        compressed.extend(payload)
    elif kind == b'IEND':
        break
raw = zlib.decompress(bytes(compressed))
stride = 1024 * 3
assert len(raw) == 768 * (stride + 1)
rows = []
for row in range(768):
    start = row * (stride + 1)
    assert raw[start] == 0, f'PNG scanline {row} must use filter 0'
    rows.append(raw[start + 1:start + 1 + stride])
assert all(row == bytes(stride) for row in rows[200:]), 'menu area must be pure black'
points = []
for y, row in enumerate(rows[:200]):
    for x in range(1024):
        pixel = row[x * 3:x * 3 + 3]
        assert pixel[0] == pixel[1] == pixel[2], 'background must be monochrome'
        if pixel != b'\0\0\0':
            points.append((x, y))
assert points, 'header artwork is empty'
assert min(x for x, _ in points) >= 32 and max(x for x, _ in points) < 750
assert min(y for _, y in points) >= 24 and max(y for _, y in points) < 200

print('PASS: OneBoot 1.0 menu, destinations, interactive safety rules and 1024x768 firmware artwork verified.')
