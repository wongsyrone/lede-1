#
# Copyright (C) 2018 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#
include $(TOPDIR)/rules.mk

PKG_NAME:=wongsyrone-specific
PKG_VERSION:=1


include $(INCLUDE_DIR)/package.mk


define Package/wongsyrone-specific
	SECTION:=wongsyrone
	CATEGORY:=wongsyrone Specific
	TITLE:=wongsyrone specific packages
	DEPENDS:=+ipset +ip +iptables-mod-extra +iptables-mod-filter +iptables-mod-ipopt +iptables-mod-nat-extra +iptables-mod-tproxy \
		+IPV6:ip6tables-extra +IPV6:ip6tables-mod-nat \
		+libsodium \
		+redsocks +pdnsd +trojan +v2ray
endef

define Package/wongsyrone-specific/description
	A package collection for Chinese
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/wongsyrone-specific/install
endef


$(eval $(call BuildPackage,wongsyrone-specific))
 
