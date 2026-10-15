#
# Copyright (C) 2008-2014 The LuCI Team <luci@lists.subsignal.org>
#
# This is free software, licensed under the Apache License, Version 2.0 .
#

include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI for Zerotier
LUCI_DEPENDS:=+luci-base +zerotier
LUCI_PKGARCH:=all
PKG_VERSION:=1.0
PKG_RELEASE:=22

define Package/luci-app-zerotier/conffiles
/etc/config/zerotier
/etc/zerotier
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
