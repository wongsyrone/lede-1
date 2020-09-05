#
# Copyright (C) 2019-2020 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#
include $(TOPDIR)/rules.mk

PKG_NAME:=mimalloc
PKG_VERSION:=1.6.4
PKG_RELEASE:=a9686d6

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/microsoft/mimalloc.git
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=a9686d6ecf00e4467e772f7c0b4ef76a15f325f6
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz
CMAKE_INSTALL:=1
PKG_BUILD_PARALLEL:=1

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_MAINTAINER:=Syrone Wong <wong.syrone@gmail.com>

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

TARGET_CXXFLAGS += -Wall -Wextra
TARGET_CXXFLAGS += $(FPIC)

CMAKE_OPTIONS += \
	-DMI_BUILD_TESTS=OFF

define Package/mimalloc
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=a compact general purpose allocator with excellent performance
  URL:=https://github.com/microsoft/mimalloc
  DEPENDS:=+libpthread +libstdcpp
endef
# STATIC lib only
define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include
	$(CP) -v $(PKG_INSTALL_DIR)/usr/lib/mimalloc-*/*.a $(1)/usr/lib/
	$(CP) -v $(PKG_INSTALL_DIR)/usr/lib/mimalloc-*/include/* $(1)/usr/include/
endef

# static lib only, no need to install to target
define Package/mimalloc/install
true
endef


$(eval $(call BuildPackage,mimalloc))
