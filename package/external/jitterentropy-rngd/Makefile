#
# Copyright (C) 2015-2017 wongsyrone 
#
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=jitterentropy-rngd
PKG_VERSION:=1.0.6
PKG_RELEASE:=1

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)/$(PKG_NAME)-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk

define Package/jitterentropy-rngd
	SECTION:=utils
	CATEGORY:=Utilities
	TITLE:=entropy collector via cpu jitter
endef

define Package/jitterentropy-rngd/description
	entropy collector via cpu jitter.
endef

# XXX: check original Makefile
#      The patch to Makefile deletes all hardcoded things and let the buildroot choose what we want.
TARGET_CFLAGS += -Wall -Wextra -pedantic -fwrapv

define Package/jitterentropy-rngd/install
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/jitterentropy-rngd.init $(1)/etc/init.d/jitterentropy-rngd
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/jitterentropy-rngd.config $(1)/etc/config/jitterentropy-rngd
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/jitterentropy-rngd $(1)/usr/sbin/jitterentropy-rngd
endef

$(eval $(call BuildPackage,jitterentropy-rngd)) 
