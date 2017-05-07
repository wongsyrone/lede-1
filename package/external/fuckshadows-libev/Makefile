#
# Copyright (C) 2017 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=fuckshadows-libev
PKG_VERSION:=0.2
PKG_RELEASE:=8

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=2c1c1061a2784e1b8618d5cda3c75ca38c59c34e
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

# get pcre for static linking
PKG_BUILD_DEPENDS:=libpcre

include $(INCLUDE_DIR)/package.mk

define Package/fuckshadows-libev
	SECTION:=net
	CATEGORY:=Network
	TITLE:=Lightweight Secured Socks5 Proxy
	URL:=https://github.com
	DEPENDS:=+libmbedtls +libsodium +libev +ipset +ip +iptables-mod-tproxy
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

# pass static archive
CONFIGURE_VARS += LIBS="$(STAGING_DIR)/usr/lib/libpcre.a"
#MAKE_VARS += LDLIBS="-Wl,-Bstatic -lpcre -Wl,-Bdynamic"

define Package/fuckshadows-libev/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/src/fs-{local,redir,tunnel} $(1)/usr/bin
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_CONF) ./files/shadowsocks.conf $(1)/etc/fuckshadows.json
	$(INSTALL_BIN) ./files/shadowsocks.init $(1)/etc/init.d/fuckshadows
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/shadowsocks.config $(1)/etc/config/fuckshadows
endef

$(eval $(call BuildPackage,fuckshadows-libev))
