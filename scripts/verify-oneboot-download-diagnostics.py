#!/usr/bin/env python3
"""Ensure each transfer captures the original error before returning to a menu."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
menu = (root / 'src/oneboot-v1.0.ipxe.in').read_text(encoding='utf-8')
blocks = dict(re.findall(r'^:([^\n]+)\n(.*?)(?=^:|\Z)', menu, re.M | re.S))
transfers = boots = 0
for line in menu.splitlines():
    if not line.startswith(('kernel ', 'initrd ', 'boot ||')):
        continue
    match = re.fullmatch(r'(.+?) \|\| oberror (kernel|initrd|boot) (\S+) '
                         r'\$\{nic\} \$\{nic_mac\} \$\{validated_ip\}/\$\{input_prefix\} '
                         r'\$\{validated_gateway\} \$\{validated_dns\} \|\| goto (\S+)', line)
    assert match, 'Uninstrumented or incorrectly ordered operation: ' + line
    command, operation, resource, handler = match.groups()
    assert command.split()[0] == operation
    if operation == 'boot':
        assert resource == '${ob_boot_resource}'
        boots += 1
    else:
        assert resource in command.split(), 'Wrong resource captured: ' + line
        transfers += 1
    body = blocks[handler]
    assert 'oberror --show\n' in body
    assert 'prompt --key 0x1b ' in body and '--timeout' not in body
assert (transfers, boots) == (29, 10), (transfers, boots)
assert 'item --menu main_menu --key l last_transfer_error Last transfer error' in menu
assert 'oberror --show' in blocks['last_transfer_error']
assert '--timeout' not in blocks['last_transfer_error']

command = (root / 'ipxe/oneboot_error_cmd.c').read_text()
assert command.index('int saved_error = errno;') < command.index('parse_options ( argc, argv')
assert 'strerror ( saved_error )' in command
assert 'saved_error ? -saved_error' in command
build = (root / 'scripts/build-oneboot-v1.0-vps.sh').read_text()
assert 'REQUIRE_OBJECT ( oneboot_error_cmd );' in build
print('PASS: all 29 transfers and 10 boot commands capture errors; reports have no automatic timeout.')
