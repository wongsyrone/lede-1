#
# Drivers Copyright (C) 2022 Intel Corporation
#
# This is free software, licensed under the GNU General Public License v2.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=kmod-igb-intel
PKG_VERSION:=5.14.16
PKG_RELEASE:=1

PKG_SOURCE:=igb-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=http://downloads.sourceforge.net/project/e1000/igb%20stable/$(PKG_VERSION)/
PKG_MD5SUM:=eaacff1aa1c82c275d9733bad6234d76

include $(INCLUDE_DIR)/kernel.mk
include $(INCLUDE_DIR)/package.mk

PKG_UNPACK:=zcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) -C $(PKG_BUILD_DIR) --strip-components=1 -xf -

define KernelPackage/igb-intel
  SUBMENU:=Network Devices
  TITLE:=Intel igb drivers - oot version from Intel
  DEPENDS:=@PCI_SUPPORT +kmod-i2c-core +kmod-i2c-algo-bit +kmod-ptp +kmod-hwmon-core
  CONFLICTS:=kmod-igb
  KCONFIG:=CONFIG_IGB \
    CONFIG_IGB_HWMON=y \
    CONFIG_IGB_DCA=n
  FILES:=$(PKG_BUILD_DIR)/src/igb.ko
  AUTOLOAD:=$(call AutoLoad,35,igb,1)
endef

define Build/Compile
	cd ${PKG_BUILD_DIR}/src; KSRC="$(LINUX_DIR)" \
		CONFFILE="$(LINUX_DIR)/.config" \
		OUT="$(PKG_BUILD_DIR)/src/kcompat_generated_defs.h" \
		bash kcompat-generator.sh
	+$(KERNEL_MAKE) M=$(PKG_BUILD_DIR)/src modules
endef

define KernelPackage/igb-intel/description
 Kernel modules for Intel igb out of tree drivers
endef

$(eval $(call KernelPackage,igb-intel))
