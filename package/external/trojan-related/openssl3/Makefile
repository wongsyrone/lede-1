#
# Copyright (C) 2006-2016 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

### Modified by wongsyrone to fit need of trojan-gfw/trojan

include $(TOPDIR)/rules.mk

PKG_NAME:=openssl3
PKG_VERSION:=3.4.0
PKG_RELEASE:=$(AUTORELEASE)
PKG_USE_MIPS16:=0

PKG_BUILD_PARALLEL:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/openssl/openssl.git
PKG_MIRROR_HASH:=95ee019ba888e2e269e1df452fa19a273ddd3b54f2d2cdf809affdfc3834824f
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=98acb6b02839c609ef5b837794e08d906d965335
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz


PKG_LICENSE:=OpenSSL
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=Eneas U de Queiroz <cotequeiroz@gmail.com>
PKG_CPE_ID:=cpe:/a:openssl:openssl

include $(INCLUDE_DIR)/package.mk

ifneq ($(CONFIG_CCACHE),)
HOSTCC=$(HOSTCC_NOCACHE)
HOSTCXX=$(HOSTCXX_NOCACHE)
endif

define Package/openssl3/Default
  TITLE:=Open source SSL toolkit3
  URL:=http://www.openssl.org/
  SECTION:=libs
  CATEGORY:=Libraries
endef

define Package/openssl3/Default/description
The OpenSSL Project is a collaborative effort to develop a robust,
commercial-grade, full-featured, and Open Source toolkit implementing the
Transport Layer Security (TLS) protocol as well as a full-strength
general-purpose cryptography library.
endef

define Package/libopenssl3
$(call Package/openssl3/Default)
  SUBMENU:=SSL
  DEPENDS:=+OPENSSL_WITH_COMPRESSION:zlib
  TITLE+= (libraries)
  ABI_VERSION:=3.0
  MENU:=1
endef

define Package/libopenssl3/description
$(call Package/openssl3/Default/description)
This package contains the OpenSSL shared libraries, needed by other programs.
endef

# do NOT interfere original openssl staging dir
MY_PKG_STAGING_DIR:=$(BUILD_DIR)/openssl3_staging_dir

OPENSSL_OPTIONS:= no-shared no-ssl3-method

# https://github.com/openssl/openssl/issues/1607
# it seems musl-libc doesn't support this
OPENSSL_OPTIONS += no-async

OPENSSL_OPTIONS += no-sm2 no-sm3 no-sm4

OPENSSL_OPTIONS += no-idea

OPENSSL_OPTIONS += no-seed

OPENSSL_OPTIONS += no-whirlpool

TARGET_CFLAGS := $(filter-out -O%,$(TARGET_CFLAGS)) -O3

OPENSSL_TARGET:=linux-$(call qstrip,$(CONFIG_ARCH))-openwrt

STAMP_CONFIGURED := $(STAMP_CONFIGURED)_$(shell echo $(OPENSSL_OPTIONS) | $(MKHASH) md5)

define Build/Configure
	[ -f $(STAMP_CONFIGURED) ] || { \
		rm -f $(PKG_BUILD_DIR)/*.so.* $(PKG_BUILD_DIR)/*.a; \
		find $(PKG_BUILD_DIR) -name \*.o | xargs rm -f; \
		rm -rf $(MY_PKG_STAGING_DIR); \
	}
	(cd $(PKG_BUILD_DIR); \
		./Configure $(OPENSSL_TARGET) \
			--prefix=/usr \
			--libdir=lib \
			--openssldir=/etc/ssl \
			--cross-compile-prefix="$(TARGET_CROSS)" \
			$(TARGET_CPPFLAGS) \
			$(TARGET_LDFLAGS) \
			$(OPENSSL_OPTIONS) && \
		{ [ -f $(STAMP_CONFIGURED) ] || make clean; } \
	)
endef

TARGET_CFLAGS += $(FPIC) -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

define Build/Compile
	+$(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR) \
		CC="$(TARGET_CC)" \
		SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH) \
		OPENWRT_OPTIMIZATION_FLAGS="$(TARGET_CFLAGS)" \
		$(OPENSSL_MAKEFLAGS) \
		all
	$(MAKE) -C $(PKG_BUILD_DIR) \
		CC="$(TARGET_CC)" \
		DESTDIR="$(PKG_INSTALL_DIR)" \
		$(OPENSSL_MAKEFLAGS) \
		install_sw install_ssldirs
endef

define Build/InstallDev
	$(INSTALL_DIR) $(MY_PKG_STAGING_DIR)/usr/include
	$(CP) $(PKG_INSTALL_DIR)/usr/include/openssl $(MY_PKG_STAGING_DIR)/usr/include/
	$(INSTALL_DIR) $(MY_PKG_STAGING_DIR)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/lib{crypto,ssl}.a $(MY_PKG_STAGING_DIR)/usr/lib/
endef

define Build/Clean
	rm -rf $(MY_PKG_STAGING_DIR)
	$(call Build/Clean/Default)
endef

define Package/libopenssl3/install
true
endef


$(eval $(call BuildPackage,libopenssl3))
