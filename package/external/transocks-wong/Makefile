#
# Copyright (C) 2018 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#
include $(TOPDIR)/rules.mk

PKG_NAME:=transocks-wong
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/wongsyrone/transocks-wong.git
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=a7db975f8d626b1afade75afa92d3d56e8a1de7f
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz
CMAKE_INSTALL:=1
PKG_BUILD_PARALLEL:=0

PKG_LICENSE:=GPL-2.0

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

ifeq ($(CONFIG_DEBUG),y)
CMAKE_OPTIONS += \
	-DENABLE_DEBUG=ON
endif

TARGET_CFLAGS += -ggdb3
TARGET_CFLAGS += -Wall -Wextra
TARGET_CFLAGS += $(FPIC)

#LTO
TARGET_CFLAGS += -flto
TARGET_LDFLAGS += -flto

TARGET_CFLAGS := $(filter-out -O%,$(TARGET_CXXFLAGS)) -O3

TARGET_CFLAGS += -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

define Package/transocks-wong
	SECTION:=wongsyrone
	CATEGORY:=wongsyrone Specific
	TITLE:=transparent ipv4 ipv6 tcp proxy
	DEPENDS:=+libevent2-core
endef

define Package/transocks-wong/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/transocks-wong $(1)/usr/sbin/transocks-wong
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/transocks-wong.config $(1)/etc/config/transocks-wong
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/transocks-wong.init $(1)/etc/init.d/transocks-wong
endef


$(eval $(call BuildPackage,transocks-wong))
