#!/usr/bin/env python3
"""Compile the actual C cpio serializer and inspect its private-prefix output."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]
class CpioTests(unittest.TestCase):
    def test_actual_c_serializer_preserves_profile_mode_content_and_alignment(self):
        raw=(SOURCE/'ipxe/oneboot_ubuntu_cmd.c').read_text(encoding='utf-8')
        function=re.search(r'^static size_t profile_cpio_entry .*?^}',raw,re.M|re.S).group()
        harness='''#include <stdio.h>
#include <string.h>
'''+function+'''
int main(void) {
 char input[640], output[1024]={0};
 size_t n=fread(input,1,sizeof(input),stdin), len;
 len=profile_cpio_entry(output,"oneboot-profile",input,n,0100600);
 len+=profile_cpio_entry(output+len,"TRAILER!!!",NULL,0,0);
 return fwrite(output,1,len,stdout)!=len;
}
'''
        with tempfile.TemporaryDirectory(prefix='oneboot-cpio-') as tmp:
            c=Path(tmp)/'test.c';binary=Path(tmp)/'test'
            c.write_text(harness,encoding='utf-8')
            subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(c),'-o',str(binary)],check=True)
            for blob in (b'HOSTNAME=ob14-test\nPASSWORD_HEX=414243\n',
                         b'HOSTNAME='+b'a'*253+b'\nPASSWORD_HEX='+b'ff'*128+b'\n'):
                data=subprocess.check_output([str(binary)],input=blob);position=0;members=[]
                while position<len(data):
                    self.assertEqual(data[position:position+6],b'070701')
                    fields=[int(data[position+6+i*8:position+14+i*8],16) for i in range(13)]
                    start=position+110;name=data[start:start+fields[11]-1].decode()
                    start=(start+fields[11]+3)&~3
                    payload=data[start:start+fields[6]];position=(start+fields[6]+3)&~3
                    members.append((name,fields[1],payload))
                self.assertEqual(members,[('oneboot-profile',0o100600,blob),('TRAILER!!!',0,b'')])
                self.assertEqual(len(data)%4,0)
if __name__=='__main__':unittest.main()
