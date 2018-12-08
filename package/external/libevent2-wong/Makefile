#
# Copyright (C) 2011-2015 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=libevent2-wong
PKG_VERSION:=2.1.8
PKG_RELEASE:=git

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/libevent/libevent.git
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=1d2ef90032bc842bc2e295ee4adce3408b6d85da
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz

#PKG_SOURCE:=libevent-$(PKG_VERSION)-stable.tar.gz
#PKG_SOURCE_URL:=https://github.com/libevent/libevent/releases/download/release-$(PKG_VERSION)-stable
#PKG_HASH:=965cc5a8bb46ce4199a47e9b2c9e1cae3b137e8356ffdad6d94d3b9069b71dc2
#PKG_BUILD_DIR:=$(BUILD_DIR)/libevent-$(PKG_VERSION)-stable

PKG_MAINTAINER:=Jo-Philipp Wich <jo@mein.io>
PKG_LICENSE:=BSD-3-Clause
PKG_CPE_ID:=cpe:/a:libevent_project:libevent

PKG_FIXUP:=autoreconf
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

# do NOT interfere original libevent2
MY_LIBEVENT_STAGING_DIR := $(BUILD_DIR)/libevent2-wong

define Package/libevent2-wong/Default
  SECTION:=wongsyrone
  CATEGORY:=wongsyrone Specific
  TITLE:=Event notification(wong)
  URL:=http://libevent.org
endef

define Package/libevent2-wong/Default/description
	The libevent API provides a mechanism to execute a callback function
	when a specific event occurs on a file descriptor or after a timeout
	has been reached. Furthermore, libevent also support callbacks due
	to signals or regular timeouts.

	libevent is meant to replace the event loop found in event driven
	network servers. An application just needs to call event_dispatch()
	and then add or remove events dynamically without having to change
	the event loop.
endef

define Package/libevent2-wong
  $(call Package/libevent2-wong/Default)
  TITLE+= library (version 2.1)
endef

define Package/libevent2-wong/description
	$(call Package/libevent2-wong/Default/description)

	This package contains the libevent shared library historically
	containing both the core & extra libraries.
endef

define Package/libevent2-wong-core
  $(call Package/libevent2-wong/Default)
  TITLE+= core library (version 2.1)
endef

define Package/libevent2-wong-core/description
	$(call Package/libevent2-wong/Default/description)

	This package contains the libevent core shared library for the event,
	buffer & utility functions.
endef

define Package/libevent2-wong-extra
  $(call Package/libevent2/Default)
  TITLE+= extra library (version 2.1)
endef

define Package/libevent2-wong-extra/description
	$(call Package/libevent2-wong/Default/description)

	This package contains the libevent extra shared library for specific
	protocols including HTTP, DNS & RPC.
endef

define Package/libevent2-wong-openssl
  $(call Package/libevent2-wong/Default)
  TITLE+= OpenSSL library (version 2.1)
  DEPENDS+=+libopenssl
endef

define Package/libevent2-wong-openssl/description
	$(call Package/libevent2-wong/Default/description)

	This package contains the libevent OpenSSL shared library for encrypted
	bufferevents.
endef

define Package/libevent2-wong-pthreads
  $(call Package/libevent2-wong/Default)
  TITLE+= Pthreads library (version 2.1)
  DEPENDS+=+libpthread
endef

define Package/libevent2-wong-pthreads/description
	$(call Package/libevent2-wong/Default/description)

	This package contains the libevent Pthreads shared library for
	threading & locking.
endef

TARGET_CFLAGS += $(FPIC)

CONFIGURE_ARGS += \
	--disable-shared \
	--enable-static \
	--disable-debug-mode \
	--disable-samples

define Build/InstallDev
	$(INSTALL_DIR) $(MY_LIBEVENT_STAGING_DIR)/usr/include
	$(CP) $(PKG_INSTALL_DIR)/usr/include/* $(MY_LIBEVENT_STAGING_DIR)/usr/include/
	$(INSTALL_DIR) $(MY_LIBEVENT_STAGING_DIR)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libevent*.{la,a} $(MY_LIBEVENT_STAGING_DIR)/usr/lib/
endef

define Build/Clean
	rm -rf $(MY_LIBEVENT_STAGING_DIR)
	$(call Build/Clean/Default)
endef

define Package/libevent2-wong/install
true
endef

define Package/libevent2-wong-core/install
true
endef

define Package/libevent2-wong-extra/install
true
endef

define Package/libevent2-wong-openssl/install
true
endef

define Package/libevent2-wong-pthreads/install
true
endef

$(eval $(call BuildPackage,libevent2-wong))
$(eval $(call BuildPackage,libevent2-wong-core))
$(eval $(call BuildPackage,libevent2-wong-extra))
$(eval $(call BuildPackage,libevent2-wong-openssl))
$(eval $(call BuildPackage,libevent2-wong-pthreads))
