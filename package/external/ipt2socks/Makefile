#
# Copyright (C) 2014 OpenWrt-dist
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=ipt2socks
PKG_VERSION:=1.1.3
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/zfl9/ipt2socks.git
PKG_MIRROR_HASH:=914465049c065c9fd21a6eabb96418acf134f2b6f0a1b861d5987ae0d10da83a
PKG_SOURCE_VERSION:=384dab4bae5ed9402e07ec1950e502c05812bc26
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION)
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)/$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION)

include $(INCLUDE_DIR)/package.mk

define Package/ipt2socks
	SECTION:=net
	CATEGORY:=Network
	TITLE:=Utility for converting iptables (REDIRECT/TPROXY) to SOCKS5
	URL:=https://github.com/zfl9/ipt2socks
endef

define Package/ipt2socks/description
Utility for converting iptables (REDIRECT/TPROXY) to SOCKS5.
endef

define Package/ipt2socks/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/ipt2socks $(1)/usr/bin
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/ipt2socks.config $(1)/etc/config/ipt2socks
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/ipt2socks.init $(1)/etc/init.d/ipt2socks
endef

$(eval $(call BuildPackage,ipt2socks))
