#
# Copyright (C) 2015 wongsyrone 
#
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=xsocks
PKG_VERSION:=0.4.1
PKG_RELEASE:=1
PKG_REV:=45726065bd7a26cbb464446e57863c2c543019d0

PKG_SOURCE_PROTO:=git
PKG_SOURCE_VERSION:=$(PKG_REV)
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.bz2
PKG_SOURCE_URL:=https://github.com/lparam/xsocks.git
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)

PKG_MAINTAINER:=lparam
PKG_FIXUP:=autoreconf
PKG_USE_MIPS16:=0

include $(INCLUDE_DIR)/package.mk

define Package/xsocks
	SECTION:=net
	CATEGORY:=Network
	TITLE:=A secure and fast proxy to protect your network traffic
	URL:=https://github.com/lparam/xsocks
	DEPENDS:=+libpthread +librt
endef

define Package/xsocks/description
  xsocks is a secure and fast proxy to protect your network traffic
endef

define Package/xsocks/install
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/xsocks.init $(1)/etc/init.d/xsocks
	$(INSTALL_DIR) $(1)/etc/xsocks
	$(INSTALL_CONF) ./files/xsocks.blacklist $(1)/etc/xsocks/black_list
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/xsocks.config $(1)/etc/config/xsocks
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/x{socks,tproxy,forwarder,tunnel} $(1)/usr/bin
endef

$(eval $(call BuildPackage,xsocks))
