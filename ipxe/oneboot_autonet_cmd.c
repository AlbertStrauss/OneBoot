/*
 * OneBoot automatic IPv4 network defaults.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of the
 * License, or (at your option) any later version.
 *
 * You can also choose to distribute this program under the terms of
 * the Unmodified Binary Distribution Licence (as given in iPXE's
 * COPYING.UBDL), provided that you have satisfied its requirements.
 */

/* Reuse the generic settings-command error namespace without modifying the
 * pinned iPXE errfile table for this release-local source file. */
#undef ERRFILE
#define ERRFILE ERRFILE_nvo_cmd

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <getopt.h>
#include <ipxe/in.h>
#include <ipxe/command.h>
#include <ipxe/parseopt.h>
#include <ipxe/settings.h>

FILE_LICENCE ( GPL2_OR_LATER_OR_UBDL );
FILE_SECBOOT ( PERMITTED );

/** "autonet" options */
struct autonet_options {};

/** "autonet" option list */
static struct option_descriptor autonet_opts[] = {};

/** "autonet" command descriptor */
static struct command_descriptor autonet_cmd =
	COMMAND_DESC ( struct autonet_options, autonet_opts, 5, 5,
		       "<ip-setting> <prefix-setting> <netmask-setting> "
		       "<gateway-setting> <address/prefix>" );

/**
 * Parse an output setting and require the expected type
 */
static int autonet_setting ( char *name, struct named_setting *setting,
			     const struct setting_type *type ) {
	int rc;

	if ( ( rc = parse_autovivified_setting ( name, setting ) ) != 0 )
		return rc;

	if ( setting->setting.type && ( setting->setting.type != type ) ) {
		printf ( "autonet: setting %s has the wrong type\n", name );
		return -EINVAL;
	}
	setting->setting.type = type;
	return 0;
}

/**
 * "autonet" command
 *
 * For conventional subnets, the suggested gateway is network+1.  For a /31,
 * OneBoot follows the operator convention requested for point-to-point
 * assignments and suggests the first address of the pair.  A /32 has no
 * derivable gateway, so the gateway setting is cleared for manual entry.
 */
static int autonet_exec ( int argc, char **argv ) {
	struct autonet_options opts;
	struct named_setting ip_setting;
	struct named_setting prefix_setting;
	struct named_setting netmask_setting;
	struct named_setting gateway_setting;
	struct in_addr address;
	struct in_addr netmask_address;
	struct in_addr gateway_address;
	char cidr[20];
	char *slash;
	char *endp;
	unsigned long prefix;
	uint32_t host_address;
	uint32_t host_netmask;
	uint32_t host_gateway;
	int rc;

	if ( ( rc = parse_options ( argc, argv, &autonet_cmd, &opts ) ) != 0 )
		goto err_parse_options;

	if ( ( rc = autonet_setting ( argv[optind], &ip_setting,
				      &setting_type_ipv4 ) ) != 0 )
		goto err_ip_setting;
	if ( ( rc = autonet_setting ( argv[optind + 1], &prefix_setting,
				      &setting_type_int8 ) ) != 0 )
		goto err_prefix_setting;
	if ( ( rc = autonet_setting ( argv[optind + 2], &netmask_setting,
				      &setting_type_ipv4 ) ) != 0 )
		goto err_netmask_setting;
	if ( ( rc = autonet_setting ( argv[optind + 3], &gateway_setting,
				      &setting_type_ipv4 ) ) != 0 )
		goto err_gateway_setting;

	if ( strlen ( argv[optind + 4] ) >= sizeof ( cidr ) ) {
		printf ( "autonet: IPv4 CIDR value is too long\n" );
		rc = -EINVAL;
		goto err_cidr_length;
	}
	strcpy ( cidr, argv[optind + 4] );
	slash = strrchr ( cidr, '/' );
	if ( ! slash ) {
		printf ( "autonet: use IPv4/prefix format (for example 192.0.2.10/24)\n" );
		rc = -EINVAL;
		goto err_missing_prefix;
	}
	*(slash++) = '\0';

	if ( inet_aton ( cidr, &address ) == 0 ) {
		printf ( "autonet: %s is not a valid IPv4 address\n", cidr );
		rc = -EINVAL;
		goto err_address;
	}
	prefix = strtoul ( slash, &endp, 10 );
	if ( *endp || ( prefix < 8 ) || ( prefix > 32 ) ) {
		printf ( "autonet: prefix must be a whole number from 8 through 32\n" );
		rc = -ERANGE;
		goto err_prefix;
	}

	host_address = ntohl ( address.s_addr );
	host_netmask = ( ~( ( uint32_t ) 0 ) << ( 32 - prefix ) );
	netmask_address.s_addr = htonl ( host_netmask );

	if ( ( rc = storef_setting ( ip_setting.settings,
				    &ip_setting.setting,
				    inet_ntoa ( address ) ) ) != 0 )
		goto err_store_ip;
	if ( ( rc = storen_setting ( prefix_setting.settings,
				    &prefix_setting.setting, prefix ) ) != 0 )
		goto err_store_prefix;
	if ( ( rc = storef_setting ( netmask_setting.settings,
				    &netmask_setting.setting,
				    inet_ntoa ( netmask_address ) ) ) != 0 )
		goto err_store_netmask;

	if ( prefix == 32 ) {
		rc = storef_setting ( gateway_setting.settings,
				      &gateway_setting.setting, NULL );
		goto err_store_gateway;
	}

	host_gateway = ( host_address & host_netmask );
	if ( prefix != 31 )
		host_gateway++;
	gateway_address.s_addr = htonl ( host_gateway );
	if ( ( rc = storef_setting ( gateway_setting.settings,
				    &gateway_setting.setting,
				    inet_ntoa ( gateway_address ) ) ) != 0 )
		goto err_store_gateway;

	return 0;

 err_store_gateway:
 err_store_netmask:
 err_store_prefix:
 err_store_ip:
 err_prefix:
 err_address:
 err_missing_prefix:
 err_cidr_length:
 err_gateway_setting:
 err_netmask_setting:
 err_prefix_setting:
 err_ip_setting:
 err_parse_options:
	return rc;
}

/** OneBoot automatic network command */
COMMAND ( autonet, autonet_exec );
