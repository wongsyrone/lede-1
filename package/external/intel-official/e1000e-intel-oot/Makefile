include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=e1000e-intel-oot
PKG_VERSION:=3.8.4
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

#define KernelPackage/e1000e
#  SUBMENU:=$(NETWORK_DEVICES_MENU)
#  TITLE:=Intel(R) PRO/1000 PCIe cards kernel support
#  DEPENDS:=@PCIE_SUPPORT +kmod-ptp
#  KCONFIG:=CONFIG_E1000E
#  FILES:=$(LINUX_DIR)/drivers/net/ethernet/intel/e1000e/e1000e.ko
#  AUTOLOAD:=$(call AutoProbe,e1000e)
#  MODPARAMS.e1000e:= \
#    IntMode=1 \
#    InterruptThrottleRate=4,4,4,4,4,4,4,4
#endef

define KernelPackage/e1000e-intel-oot
  SUBMENU:=Network Devices
  TITLE:=Intel e1000e drivers - out of tree version
  DEPENDS:=@PCI_SUPPORT +kmod-ptp
  KCONFIG:=CONFIG_E1000E
  FILES:=$(PKG_BUILD_DIR)/e1000e.ko
  AUTOLOAD:=$(call AutoLoad,35,e1000e)
endef

define KernelPackage/e1000e-intel-oot/description
 Kernel modules for Intel(R) PRO/1000 PCIe Ethernet adapters.
 Kernel modules for Intel e1000e out of tree drivers
 Warning: do not select the core package kmod-e1000e as this is an
 updated version of the e1000e driver that shares the same module name
endef

define Build/Compile
	$(KERNEL_MAKE) M="$(PKG_BUILD_DIR)" modules
endef

$(eval $(call KernelPackage,e1000e-intel-oot))
 
