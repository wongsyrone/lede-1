#
# Copyright (C) 2016 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=fping
PKG_VERSION:=3.13
PKG_RELEASE:=1

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)/$(PKG_NAME)-$(PKG_VERSION)

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/schweikert/fping.git
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=925ef8fe12be20eb9b0931a231a3d2a607279f3a
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz

PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_USE_MIPS16:=0
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/$(PKG_NAME)
	SECTION:=utils
	CATEGORY:=Utilities
	TITLE:=high performance ping tool
	DEPENDS:=+libpthread
endef

define Package/$(PKG_NAME)/description
  fping is a program to send ICMP echo probes to network hosts, similar to ping,
  but much better performing when pinging multiple hosts.
  fping has a long long story: Roland Schemers did publish a first version of
  it in 1992 and it has established itself since then as a standard tool.
endef

CONFIGURE_ARGS += \
	--enable-ipv4 \
	--enable-ipv6

TARGET_CFLAGS += -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

# Use Link time optimization
TARGET_CFLAGS += -flto
TARGET_LDFLAGS += -Wl,-flto

define Package/$(PKG_NAME)/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/src/{fping,fping6} $(1)/usr/sbin/
endef

$(eval $(call BuildPackage,fping))
