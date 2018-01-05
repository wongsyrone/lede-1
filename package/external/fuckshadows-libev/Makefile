#
# Copyright (C) 2017 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=fuckshadows-libev
PKG_VERSION:=0.2
PKG_RELEASE:=13

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=b57b4732adf06f1239c97dd7d7c0a80d1cc3d3cb
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.bz2
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_URL:=https://github.com/fuckshadows/fuckshadows-libev.git

PKG_LICENSE:=GPLv3
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=

PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_USE_MIPS16:=0
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/fuckshadows-libev
	SECTION:=net
	CATEGORY:=Network
	TITLE:=Lightweight Secured Socks5 Proxy
	URL:=https://github.com
	DEPENDS:=+libmbedtls +libsodium +libev +libpcre2 +ipset +ip +iptables-mod-tproxy
endef

define Package/fuckshadows-libev/description
Shadowsocks-libev is a lightweight secured socks5 proxy for embedded devices and low end boxes.
endef

define Package/fuckshadows-libev/conffiles
/etc/fuckshadows.json
endef

# Use shared lib provided by OpenWrt/LEDE, and use our SSP settings
CONFIGURE_ARGS += --enable-system-shared-lib --disable-ssp

# Check whether compiler follows our inline suggestion
TARGET_CFLAGS += -Wno-error=inline -Winline

# Use Link time optimization
TARGET_CFLAGS += -flto
TARGET_LDFLAGS += -Wl,-flto

# strip unused functions and data
TARGET_CFLAGS += -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

# redef CPPFLAGS and CFLAGS
# c-ares: Use CPPFLAGS for macro definitions
TARGET_CPPFLAGS += $(filter -D%,$(TARGET_CFLAGS))
TARGET_CFLAGS := $(filter-out -D%,$(TARGET_CFLAGS))

# redef CFLAGS, replace -O* with -O3
TARGET_CFLAGS := $(filter-out -O%,$(TARGET_CFLAGS)) -O3

define Package/fuckshadows-libev/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/src/fs-{local,redir,tunnel} $(1)/usr/bin
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_CONF) ./files/shadowsocks.conf $(1)/etc/fuckshadows.json
	$(INSTALL_BIN) ./files/shadowsocks.init $(1)/etc/init.d/fuckshadows
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/shadowsocks.config $(1)/etc/config/fuckshadows
	$(INSTALL_DIR) $(1)/etc/hotplug.d/iface
	$(INSTALL_BIN) ./files/shadowsocks.hotplug $(1)/etc/hotplug.d/iface/96-fuckshadows
endef

$(eval $(call BuildPackage,fuckshadows-libev))
