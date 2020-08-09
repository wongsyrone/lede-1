include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=ixgbe-intel-oot
PKG_VERSION:=5.8.1
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

#define KernelPackage/ixgbe
#  SUBMENU:=$(NETWORK_DEVICES_MENU)
#  TITLE:=Intel(R) 82598/82599 PCI-Express 10 Gigabit Ethernet support
#  DEPENDS:=@PCI_SUPPORT +kmod-mdio +kmod-ptp +kmod-hwmon-core +LINUX_5_4:kmod-libphy
#  KCONFIG:=CONFIG_IXGBE \
#    CONFIG_IXGBE_VXLAN=n \
#    CONFIG_IXGBE_HWMON=y \
#    CONFIG_IXGBE_DCA=n
#  FILES:=$(LINUX_DIR)/drivers/net/ethernet/intel/ixgbe/ixgbe.ko
#  AUTOLOAD:=$(call AutoLoad,35,ixgbe)
#endef

define KernelPackage/ixgbe-intel-oot
  SUBMENU:=Network Devices
  TITLE:=Intel ixgbe drivers - out of tree version
  DEPENDS:=@PCI_SUPPORT +kmod-mdio +kmod-ptp +kmod-hwmon-core +LINUX_5_4:kmod-libphy
  KCONFIG:=CONFIG_IXGBE \
    CONFIG_IXGBE_VXLAN=n \
    CONFIG_IXGBE_HWMON=y \
    CONFIG_IXGBE_DCA=n
  FILES:=$(PKG_BUILD_DIR)/ixgbe.ko
  AUTOLOAD:=$(call AutoLoad,35,ixgbe)
endef

define KernelPackage/ixgbe-intel-oot/description
 Kernel modules for Intel(R) 82598/82599 PCI-Express 10 Gigabit Ethernet adapters.
 Kernel modules for Intel ixgbe out of tree drivers
 Warning: do not select the core package kmod-ixgbe as this is an
 updated version of the ixgbe driver that shares the same module name
endef

define Build/Compile
	$(KERNEL_MAKE) M="$(PKG_BUILD_DIR)" modules
endef

$(eval $(call KernelPackage,ixgbe-intel-oot))
 
