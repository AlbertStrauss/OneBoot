/* OneBoot download error snapshot. GPL2_OR_LATER_OR_UBDL, as in iPXE. */
#undef ERRFILE
#define ERRFILE ERRFILE_nvo_cmd

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <getopt.h>
#include <ipxe/command.h>
#include <ipxe/parseopt.h>

FILE_LICENCE ( GPL2_OR_LATER_OR_UBDL );
FILE_SECBOOT ( PERMITTED );

/* Fixed storage also works when a download fails because RAM is exhausted.
 * Keep a copy: strerror() uses a shared buffer and errno can change later. */
static struct {
	unsigned int number;
	int error;
	char description[96];
	char operation[24];
	char resource[1024];
	char nic[24];
	char mac[24];
	char address[32];
	char gateway[24];
	char dns[24];
} last_error;

struct oberror_options { int show; };
static struct option_descriptor oberror_opts[] = {
	OPTION_DESC ( "show", 's', no_argument,
		      struct oberror_options, show, parse_flag ),
};
static struct command_descriptor oberror_cmd =
	COMMAND_DESC ( struct oberror_options, oberror_opts, 0, 7,
		       "[--show | <operation> <url> <nic> <mac> <ip/prefix> <gateway> <dns>]" );

static void oberror_show ( void ) {
	if ( ! last_error.number ) {
		printf ( "No OneBoot transfer error has been captured in this session.\n" );
		return;
	}
	printf ( "\n================ ONEBOOT TRANSFER ERROR ================\n" );
	printf ( "Operation: %s\n", last_error.operation );
	printf ( "Resource: %s\n", last_error.resource );
	printf ( "Error: %s\n", last_error.description );
	printf ( "Code: 0x%08x\n", ( unsigned int ) last_error.error );
	printf ( "NIC: %s  MAC: %s\n", last_error.nic, last_error.mac );
	printf ( "IPv4: %s  Gateway: %s  DNS: %s\n",
		 last_error.address, last_error.gateway, last_error.dns );
	printf ( "Photograph this report. Main menu -> Last transfer error.\n" );
	printf ( "Stored in RAM only, until reboot or installer handoff.\n" );
}

static int oberror_exec ( int argc, char **argv ) {
	/* Capture before option parsing or printing can overwrite errno. */
	int saved_error = errno;
	struct oberror_options opts;
	int rc;

	if ( ( rc = parse_options ( argc, argv, &oberror_cmd, &opts ) ) != 0 )
		return rc;
	if ( opts.show ) {
		if ( argc != optind )
			return -EINVAL;
		oberror_show();
		return 0;
	}
	if ( argc - optind != 7 )
		return -EINVAL;

	last_error.number++;
	last_error.error = saved_error;
	snprintf ( last_error.description, sizeof ( last_error.description ),
		   "%s", strerror ( saved_error ) );
#define COPY_ARG( field, index ) \
	snprintf ( last_error.field, sizeof ( last_error.field ), \
		   "%s", argv[ optind + index ] )
	COPY_ARG ( operation, 0 );
	COPY_ARG ( resource, 1 );
	COPY_ARG ( nic, 2 );
	COPY_ARG ( mac, 3 );
	COPY_ARG ( address, 4 );
	COPY_ARG ( gateway, 5 );
	COPY_ARG ( dns, 6 );
#undef COPY_ARG
	/* Return the original failure so the script's final || goto is executed.
 * Printing happens in --show after the caller reaches its error screen. */
	return ( saved_error ? -saved_error : -EIO );
}

COMMAND ( oberror, oberror_exec );
