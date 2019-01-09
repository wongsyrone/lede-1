ARCH:=x86_64
BOARDNAME:=x86_64
DEFAULT_PACKAGES += kmod-button-hotplug kmod-e1000e kmod-e1000 kmod-r8169 kmod-igb kmod-usb-hid kmod-usb-net-asix kmod-usb-net-asix-ax88179 \
	kmod-rt2800-usb kmod-igbvf kmod-ixgbe kmod-vmxnet3 kmod-bnx2

define Target/Description
        Build images for 64 bit systems including virtualized guests.
endef
