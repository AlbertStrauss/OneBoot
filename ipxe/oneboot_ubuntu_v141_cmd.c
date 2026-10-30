/* OneBoot Ubuntu profile and embedded helper retention. GPL-2.0-or-later. */
#undef ERRFILE
#define ERRFILE ERRFILE_nvo_cmd
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <ipxe/command.h>
#include <ipxe/image.h>
#include <ipxe/settings.h>
#include <ipxe/parseopt.h>

FILE_LICENCE ( GPL2_OR_LATER );
FILE_SECBOOT ( PERMITTED );

static const char *helper_names[] = {
 "99onebootseed", "param.conf", "oneboot-mirror-pick", "oneboot-disk", "oneboot-set-password"
};
static const char *helper_paths[] = {
 "/scripts/casper-bottom/99onebootseed mode=755 mkdir=-1",
 "/conf/param.conf mkdir=-1", "/conf/oneboot-mirror-pick mkdir=-1",
 "/oneboot-disk mode=755", "/oneboot-set-password mode=700"
};
static struct image *helpers[5];
/* Keep a bounded private copy until Back/new mode or the kernel handoff.
 * A failed fetch can free every registered image without asking for passwords again. */
static char retry_profile[640];
static size_t retry_profile_len;
static void forget_profile(void) {
 memset(retry_profile,0,sizeof(retry_profile)); retry_profile_len=0;
}

static void clear_profile ( void ) {
 struct image *image = find_image ( "oneboot-profile" );
 if ( image ) unregister_image ( image );
}

/* Old 4.15/5.4 kernels discard cpio members appended after the vendor gzip.
 * Put the private profile BEFORE the independently built auto initrd instead.
 * image_set_len preserves the vendor bytes and uses external image memory.
 */
static size_t profile_cpio_entry ( char *out, const char *name,
                                 const void *data, size_t len, unsigned int mode ) {
 size_t namesize=strlen(name)+1, pos;
 snprintf(out,111,"070701%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x%08x",
          1,mode,0,0,1,0,(unsigned int)len,0,0,0,0,(unsigned int)namesize,0);
 memcpy(out+110,name,namesize);
 pos=(110+namesize+3)&~((size_t)3);
 if (len) memcpy(out+pos,data,len);
 return (pos+len+3)&~((size_t)3);
}

static int prepend_profile ( const char *name ) {
 struct image *profile=find_image("oneboot-profile"), *initrd=find_image(name);
 char prefix[1024];
 size_t prefix_len, vendor_len;
 int rc;
 if (!profile || !initrd || profile==initrd || profile->len>640 ||
     initrd->len<6 || memcmp(initrd->data,"070701",6)) return -EINVAL;
 memset(prefix,0,sizeof(prefix));
 prefix_len=profile_cpio_entry(prefix,"oneboot-profile",profile->data,profile->len,0100600);
 prefix_len+=profile_cpio_entry(prefix+prefix_len,"TRAILER!!!",NULL,0,0);
 vendor_len=initrd->len;
 if ((rc=image_set_len(initrd,vendor_len+prefix_len)) != 0) goto out;
 memmove((char *)initrd->rwdata+prefix_len,initrd->data,vendor_len);
 memcpy(initrd->rwdata,prefix,prefix_len);
 memset(profile->rwdata,0,profile->len);
 clear_profile();
out:
 memset(prefix,0,sizeof(prefix));
 return rc;
}

static int obpayload_exec ( int argc, char **argv ) {
 unsigned int i;
 int rc;
 if ( argc == 1 ) {
  if ( helpers[0] ) return -EINVAL;
  for ( i=0; i<5; i++ ) {
   helpers[i]=find_image ( helper_names[i] );
   if ( ! helpers[i] ) return -ENOENT;
  }
  for ( i=0; i<5; i++ ) {
   image_get ( helpers[i] );
   unregister_image ( helpers[i] );
  }
  return 0;
 }
 if ( argc != 2 || strcmp ( argv[1], "restore" ) ) return -EINVAL;
 clear_profile();
 for ( i=0; i<5; i++ ) {
  if ( ! helpers[i] ) return -ENOENT;
  if ( helpers[i]->flags & IMAGE_REGISTERED ) unregister_image ( helpers[i] );
  if ( (rc=image_set_name(helpers[i],helper_names[i])) != 0 ) return rc;
  if ( (rc=image_set_cmdline(helpers[i],helper_paths[i])) != 0 ) return rc;
  if ( (rc=register_image(helpers[i])) != 0 ) return rc;
 }
 return 0;
}

static int read_value ( char *name, char **value ) {
 struct named_setting setting;
 int rc;
 if ( (rc=parse_autovivified_setting(name,&setting)) != 0 ) return rc;
 rc=fetch_string_setting_copy(setting.settings,&setting.setting,value);
 return rc<0 ? rc : 0;
}

static int valid_hostname ( const char *host ) {
 const unsigned char *p=(const unsigned char *)host;
 size_t label=0, len=strlen(host);
 if ( !len || len>253 ) return 0;
 for (; *p; p++) {
  if (*p=='.') {
   if (!label || p[-1]=='-') return 0;
   label=0;
  } else {
   if (!((*p>='a' && *p<='z') || (*p>='A' && *p<='Z') ||
         (*p>='0' && *p<='9') || *p=='-')) return 0;
   if ((!label && *p=='-') || ++label>63) return 0;
  }
 }
 return label && p[-1]!='-';
}

static int obprofile_exec ( int argc, char **argv ) {
 char *host=NULL, *password=NULL, *confirm=NULL, *blob=NULL;
 size_t len=0, i, pos, size;
 struct image *image;
 int rc=-EINVAL;
 static const char hex[]="0123456789abcdef";
 if ( argc==2 && !strcmp(argv[1],"clear") ) { clear_profile(); forget_profile(); return 0; }
 if ( argc==2 && !strcmp(argv[1],"restore") ) {
  if (!retry_profile_len) return -ENOENT;
  clear_profile();
  image=image_memory("oneboot-profile",retry_profile,retry_profile_len);
  if (!image) return -ENOMEM;
  rc=image_set_cmdline(image,"/oneboot-profile mode=600");
  if (rc) unregister_image(image);
  return rc;
 }
 if ( argc==3 && !strcmp(argv[1],"prepend") ) return prepend_profile(argv[2]);
 if ( argc!=5 || (strcmp(argv[1],"check") && strcmp(argv[1],"create")) ) {
  printf("Usage: obprofile check|create <hostname-setting> <password-setting> <confirmation-setting>\n");
  return -EINVAL;
 }
 if ( read_value(argv[2],&host) || !host || !valid_hostname(host) ) {
  printf("OneBoot: enter a valid hostname (letters, digits, hyphens and DNS labels).\n"); goto out;
 }
 if ( read_value(argv[3],&password) || !password || !(len=strlen(password)) || len>128 ) {
  printf("OneBoot: enter a non-empty password, up to 128 bytes.\n"); goto out;
 }
 for (i=0;i<len;i++) if ((unsigned char)password[i]<32 || (unsigned char)password[i]==127) {
  printf("OneBoot: the password cannot contain control characters.\n"); goto out;
 }
 if (read_value(argv[4],&confirm) || !confirm || strcmp(password,confirm)) {
  printf("OneBoot: passwords do not match. Enter both again.\n"); goto out;
 }
 if (!strcmp(argv[1],"check")) { rc=0; goto out; }
 size=strlen(host)+2*len+40;
 blob=malloc(size);
 if (!blob) { rc=-ENOMEM; goto out; }
 pos=snprintf(blob,size,"HOSTNAME=%s\nPASSWORD_HEX=",host);
 for(i=0;i<len;i++) {
  unsigned char c=password[i]; blob[pos++]=hex[c>>4]; blob[pos++]=hex[c&15];
 }
 blob[pos++]='\n';
 clear_profile();
 image=image_memory("oneboot-profile",blob,pos);
 if (!image) { rc=-ENOMEM; goto out; }
 rc=image_set_cmdline(image,"/oneboot-profile mode=600");
 if (rc) unregister_image(image);
 else {
  if (pos>sizeof(retry_profile)) { unregister_image(image); rc=-E2BIG; }
  else { forget_profile(); memcpy(retry_profile,blob,pos); retry_profile_len=pos; }
 }
out:
 if (password) { memset(password,0,len); free(password); }
 if (confirm) { memset(confirm,0,strlen(confirm)); free(confirm); }
 if (blob) { memset(blob,0,size); free(blob); }
 free(host);
 return rc;
}
COMMAND ( obpayload, obpayload_exec );
COMMAND ( obprofile, obprofile_exec );
