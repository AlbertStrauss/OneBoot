#ifndef ONEBOOT_LOCAL_USB_V13_H
#define ONEBOOT_LOCAL_USB_V13_H
/* Same BIOS keyboard policy as FluxBilling: retain firmware USB emulation. */
#if defined ( PLATFORM_pcbios )
#undef USB_HCD_XHCI
#undef USB_HCD_EHCI
#undef USB_HCD_UHCI
#undef USB_KEYBOARD
#undef USB_BLOCK
#endif
#endif
