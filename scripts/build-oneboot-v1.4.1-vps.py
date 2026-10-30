#!/usr/bin/env python3
"""Use the qualified builder in a new staging directory and versioned helpers."""
from pathlib import Path

source=Path(__file__).resolve().parents[1]
code=(source/'scripts/build-oneboot-v1.4-vps.py').read_text()
code=code.replace('oneboot-v1.4-autoinstall-','oneboot-v1.4.1-autoinstall-')
code=code.replace('prepare-oneboot-v1.4-menu.py','prepare-oneboot-v1.4.1-menu.py')
code=code.replace("source/'ipxe/oneboot_ubuntu_cmd.c'","source/'ipxe/oneboot_ubuntu_v141_cmd.c'")
code=code.replace('RELEASE_VERSION="1.4"','RELEASE_VERSION="1.4.1"')
code=code.replace('oneboot-v1.4.ipxe.in','oneboot-v1.4.1.ipxe.in')
code=code.replace("'${SOURCE_ROOT}/autoinstall/'","'${SOURCE_ROOT}/autoinstall-v1.4.1/'")
code=code.replace("'-V ONEBOOT_1_4'","'-V ONEBOOT_1_4_1'")
code=code.replace("'OneBoot 1.4\\n\\nStatus:'","'OneBoot 1.4.1\\n\\nStatus:'")
code=code.replace("source/'scripts/build-oneboot-v1.4-vps.sh'","source/'scripts/build-oneboot-v1.4.1-vps.sh'")
exec(compile(code,str(__file__),'exec'))
