#!/usr/bin/env python3
"""Execute the actual RAM fetch policy with a blocked input FIFO and mock network."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'autoinstall-v1.4.1/oneboot-mirror-pick'
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ob-vps-policy-');self.addCleanup(self.temp.cleanup)
        self.p=Path(self.temp.name);(self.p/'bin').mkdir()
        self.fifo=self.p/'input';os.mkfifo(self.fifo)
        self.requests=self.p/'requests';self.requests.touch()
        mock=self.p/'bin/wget'
        mock.write_text('''#!/bin/sh
out=; previous=
for arg do
 case "$arg" in -T|--timeout*) echo unsupported-timeout-option >&2; exit 91 ;; esac
 [ "$previous" = -O ] && out=$arg
 previous=$arg
 url=$arg
done
printf '%s\\n' "$url" >> "$REQUESTS"
case "$url" in
 *vps.invalid*)
   n=$(grep -c vps.invalid "$REQUESTS")
   [ "${VPS_WORKS:-0}" = 1 ] || { [ "${VPS_RETRY:-0}" = 1 ] && [ "$n" -gt 1 ]; } || exit 8
   [ "${WRONG_HASH:-0}" = 0 ] || { printf wrong > "$out"; exit 0; } ;;
esac
printf correct-iso > "$out"
''');mock.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.p/'bin')+':'+os.environ['PATH'],REQUESTS=str(self.requests),
            oneboot_cmdline=str(self.p/'cmdline'),oneboot_input_console=str(self.fifo),oneboot_download_log=str(self.p/'download.log'))
        digest=hashlib.sha256(b'correct-iso').hexdigest()
        (self.p/'cmdline').write_text('oneboot.policy=vps-first-v1 oneboot.source=vps oneboot.primary=https://vps.invalid/os.iso oneboot.fallback=https://public.invalid/os.iso oneboot.iso_sha256='+digest)
    def start(self,**env):
        script='oneboot_consoles() { :; }; . "$1"; oneboot_fetch_candidates "$2"'
        p=subprocess.Popen(['sh','-c',script,'policy-test',str(HELPER),str(self.p/'image.iso')],env=dict(self.env,**env),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(lambda:p.kill() if p.poll() is None else None)
        return p
    def wait_prompt(self,p):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if (self.p/'download.log').exists() and 'Type r + Enter' in (self.p/'download.log').read_text():return
            if p.poll() is not None:self.fail(repr(p.communicate()))
            time.sleep(.02)
        self.fail('No held fallback prompt')
    def reply(self,p,letter):
        with self.fifo.open('w') as f:f.write(letter+'\n');f.flush()
        out,err=p.communicate(timeout=5);self.assertEqual(p.returncode,0,err.decode()+out.decode())
    def urls(self):return self.requests.read_text().splitlines()
    def test_successful_vps_never_contacts_fallback(self):
        p=self.start(VPS_WORKS='1');p.communicate(timeout=5)
        self.assertEqual(p.returncode,0);self.assertEqual(self.urls(),['https://vps.invalid/os.iso'])
    def test_failure_blocks_without_any_public_request_then_f_works(self):
        p=self.start();self.wait_prompt(p);time.sleep(.4)
        self.assertIsNone(p.poll());self.assertEqual(self.urls(),['https://vps.invalid/os.iso'])
        self.reply(p,'f');self.assertEqual(self.urls(),['https://vps.invalid/os.iso','https://public.invalid/os.iso'])
    def test_retry_r_stays_on_vps(self):
        p=self.start(VPS_RETRY='1');self.wait_prompt(p);self.reply(p,'r')
        self.assertEqual(self.urls(),['https://vps.invalid/os.iso']*2)
    def test_wrong_hash_holds_and_never_autoswitches(self):
        p=self.start(VPS_WORKS='1',WRONG_HASH='1');self.wait_prompt(p)
        self.assertEqual(self.urls(),['https://vps.invalid/os.iso']);self.assertFalse((self.p/'image.iso').exists())
        self.reply(p,'f');self.assertIn('SHA256 mismatch',(self.p/'download.log').read_text())
    def test_explicit_ipxe_fallback_selection_allows_public(self):
        c=self.p/'cmdline';c.write_text(c.read_text().replace('oneboot.source=vps','oneboot.source=fallback'))
        p=self.start();p.communicate(timeout=5);self.assertEqual(p.returncode,0)
        self.assertEqual(self.urls(),['https://public.invalid/os.iso'])
    def test_unrelated_casper_path_is_not_overridden(self):
        (self.p/'cmdline').write_text('boot=casper')
        p=subprocess.run(['sh','-c','do_urlmount() { echo unchanged; }; . "$1"; do_urlmount','policy-test',str(HELPER)],env=self.env,capture_output=True,text=True)
        self.assertEqual(p.stdout.strip(),'unchanged');self.assertEqual(self.urls(),[])

class MenuTests(unittest.TestCase):
    def test_all_versions_start_vps_and_fallback_has_no_timeout(self):
        s=(ROOT/'src/oneboot-v1.4.1.ipxe.in').read_text()
        blocks=dict(re.findall(r'^:([^\n]+)\n(.*?)(?=^:|\Z)',s,re.M|re.S))
        for label in ('ubuntu_auto_go','ubuntu_manual','boot_ubuntu_1804_net','boot_ubuntu_2004_net'):
            self.assertIn('goto ubuntu_vps_start',blocks[label])
        self.assertIn('set ubuntu_source vps',blocks['ubuntu_vps_start'])
        self.assertNotIn('goto ubuntu_fallback_start',blocks['ubuntu_source_failed'])
        self.assertIn('--key f ubuntu_fallback_start',blocks['ubuntu_source_failed'])
        self.assertNotIn('--timeout',blocks['ubuntu_source_failed'])
        self.assertIn('boot=casper',blocks['ubuntu_casper_fetch'])
        self.assertNotIn('imgfree kboot',s);self.assertNotIn('imgfree iboot',s)
        for label in ('ubuntu_casper_profile_ready','ubuntu_di_auto_start','ubuntu_di_manual_start'):
            self.assertIn('${base_url}/ubuntu/',blocks[label])

class ProfileRetryTests(unittest.TestCase):
    def test_actual_c_profile_retry_and_forget(self):
        raw=(ROOT/'ipxe/oneboot_ubuntu_v141_cmd.c').read_text()
        funcs='\n'.join(re.search(r'^static '+pattern+r'.*?^}',raw,re.M|re.S).group() for pattern in
            ('void forget_profile','void clear_profile','int valid_hostname','int obprofile_exec'))
        harness=r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
struct image { char *data; size_t len; };
static struct image *registered;
static char retry_profile[640]; static size_t retry_profile_len;
static struct image *find_image(const char *name) { (void)name; return registered; }
static void unregister_image(struct image *i) { free(i->data);free(i);registered=NULL; }
static struct image *image_memory(const char *name,const void *data,size_t n) {
 (void)name;registered=calloc(1,sizeof(*registered));registered->data=malloc(n);memcpy(registered->data,data,n);registered->len=n;return registered;
}
static int image_set_cmdline(struct image *i,const char *cmd) { (void)i;(void)cmd;return 0; }
static int read_value(char *name,char **value) { *value=strdup(name);return 0; }
static int prepend_profile(const char *name) { (void)name;return -EINVAL; }
'''+funcs+r'''
int main(void) {
 char *create[]={"obprofile","create","test-host","FakePassword1!","FakePassword1!"};
 char *restore[]={"obprofile","restore"}; char *clear[]={"obprofile","clear"};
 char before[640]; size_t n;
 if(obprofile_exec(5,create))return 1;
 n=registered->len;memcpy(before,registered->data,n);
 clear_profile(); /* imgfree/obpayload restore discarded registered images */
 if(obprofile_exec(2,restore)||registered->len!=n||memcmp(before,registered->data,n))return 2;
 if(obprofile_exec(2,clear)||retry_profile_len||registered)return 3;
 for(n=0;n<sizeof(retry_profile);n++)if(retry_profile[n])return 4;
 if(obprofile_exec(2,restore)!=-ENOENT)return 5;
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='ob-profile-retry-') as tmp:
            c=Path(tmp)/'retry.c';exe=Path(tmp)/'retry';c.write_text(harness)
            subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
if __name__=='__main__':unittest.main(verbosity=2)
