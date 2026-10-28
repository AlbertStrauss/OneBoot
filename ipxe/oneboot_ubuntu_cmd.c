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

static void clear_profile ( void ) {
 struct image *image = find_image ( "oneboot-profile" );
 if ( image ) unregister_image ( image );
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
 if ( argc==2 && !strcmp(argv[1],"clear") ) { clear_profile(); return 0; }
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
out:
 if (password) { memset(password,0,len); free(password); }
 if (confirm) { memset(confirm,0,strlen(confirm)); free(confirm); }
 if (blob) { memset(blob,0,size); free(blob); }
 free(host);
 return rc;
}
COMMAND ( obpayload, obpayload_exec );
COMMAND ( obprofile, obprofile_exec );
