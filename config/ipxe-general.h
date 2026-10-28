#ifndef CONFIG_LOCAL_GENERAL_H
#define CONFIG_LOCAL_GENERAL_H

/* BIOS removes this command by default; OneBoot needs it for branding. */
#define CONSOLE_CMD

/* Required by both the BIOS and UEFI builds for authenticated downloads. */
#define DOWNLOAD_PROTO_HTTPS

#endif /* CONFIG_LOCAL_GENERAL_H */
