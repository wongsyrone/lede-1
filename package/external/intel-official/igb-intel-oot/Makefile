include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=igb-intel-oot
PKG_VERSION:=5.3.6
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

#define KernelPackage/igb
#  SUBMENU:=$(NETWORK_DEVICES_MENU)
#  TITLE:=Intel(R) 82575/82576 PCI-Express Gigabit Ethernet support
#  DEPENDS:=@PCI_SUPPORT +kmod-i2c-core +kmod-i2c-algo-bit +kmod-ptp +kmod-hwmon-core
#  KCONFIG:=CONFIG_IGB \
#    CONFIG_IGB_HWMON=y \
#    CONFIG_IGB_DCA=n
#  FILES:=$(LINUX_DIR)/drivers/net/ethernet/intel/igb/igb.ko
#  AUTOLOAD:=$(call AutoLoad,35,igb)
#endef

define KernelPackage/igb-intel-oot
  SUBMENU:=Network Devices
  TITLE:=Intel igb drivers - out of tree version
  DEPENDS:=@PCI_SUPPORT +kmod-ptp +kmod-hwmon-core
  KCONFIG:=CONFIG_IGB \
    CONFIG_IGB_HWMON=y \
    CONFIG_IGB_DCA=n
  FILES:=$(PKG_BUILD_DIR)/igb.ko
  AUTOLOAD:=$(call AutoLoad,35,igb)
endef

define KernelPackage/igb-intel-oot/description
 Kernel modules for Intel(R) 82575/82576 PCI-Express Gigabit Ethernet adapters.
 Kernel modules for Intel igb out of tree drivers
 Warning: do not select the core package kmod-igb as this is an
 updated version of the igb driver that shares the same module name
endef

define Build/Compile
	$(KERNEL_MAKE) M="$(PKG_BUILD_DIR)" modules
endef

$(eval $(call KernelPackage,igb-intel-oot))
