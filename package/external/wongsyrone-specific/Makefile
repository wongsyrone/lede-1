#
# Copyright (C) 2018 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#
include $(TOPDIR)/rules.mk

PKG_NAME:=wongsyrone-specific
PKG_VERSION:=2


include $(INCLUDE_DIR)/package.mk

# iptables
# +IPV6:ip6tables-extra +IPV6:ip6tables-mod-nat
# +iptables-mod-extra +iptables-mod-filter +iptables-mod-ipopt +iptables-mod-nat-extra +iptables-mod-tproxy
# +iptables-mod-fullconenat

define Package/wongsyrone-specific
	SECTION:=wongsyrone
	CATEGORY:=wongsyrone Specific
	TITLE:=wongsyrone specific packages
	DEPENDS:=+ipset +ip  \
		+kmod-nf-nathelper +kmod-nf-nathelper-extra +kmod-nft-socket +kmod-nft-compat +kmod-nft-tproxy \
		+transocks-wong +ipt2socks \
		+pdnsd +trojan +v2ray +vlmcsd \
		+luci-app-turboacc \
		+ethtool \
		+kmod-igb +kmod-e1000e \
		+kmod-nft-fullcone
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
 
