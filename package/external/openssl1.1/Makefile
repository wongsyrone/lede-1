#
# Copyright (C) 2006-2016 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

### Modified by wongsyrone to fit need of trojan-gfw/trojan

include $(TOPDIR)/rules.mk

PKG_NAME:=openssl1.1

PKG_BASE:=1.1.1
PKG_BUGFIX:=
PKG_HASH:=2836875a0f89c03d0fdf483941512613a50cfb421d6fd94b9f41d7279d586a3d
ENGINES_DIR=engines-1.1


PKG_VERSION:=$(PKG_BASE)$(PKG_BUGFIX)
PKG_RELEASE:=1
PKG_USE_MIPS16:=0
PATCH_DIR=./patches/$(PKG_BASE)

PKG_BUILD_PARALLEL:=0
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)/openssl-$(PKG_VERSION)

PKG_SOURCE:=openssl-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:= \
	http://ftp.fi.muni.cz/pub/openssl/source/ \
	http://ftp.linux.hr/pub/openssl/source/ \
	http://gd.tuwien.ac.at/infosys/security/openssl/source/ \
	http://www.openssl.org/source/ \
	http://www.openssl.org/source/old/$(PKG_BASE)/

PKG_LICENSE:=OpenSSL
PKG_LICENSE_FILES:=LICENSE
PKG_CPE_ID:=cpe:/a:openssl:openssl
PKG_CONFIG_DEPENDS:= \
	CONFIG_OPENSSL11_ENGINE \
	CONFIG_OPENSSL11_ENGINE_CRYPTO \
	CONFIG_OPENSSL11_ENGINE_DIGEST \
	CONFIG_OPENSSL11_ENGINE_PADLOCK \
	CONFIG_OPENSSL11_OPTIMIZE_SPEED \
	CONFIG_OPENSSL11_PREFER_CHACHA_OVER_GCM \
	CONFIG_OPENSSL11_WITH_ARIA \
	CONFIG_OPENSSL11_WITH_ASM \
	CONFIG_OPENSSL11_WITH_ASYNC \
	CONFIG_OPENSSL11_WITH_BLAKE2 \
	CONFIG_OPENSSL11_WITH_CAMELLIA \
	CONFIG_OPENSSL11_WITH_CHACHA_POLY1305 \
	CONFIG_OPENSSL11_WITH_CMS \
	CONFIG_OPENSSL11_WITH_COMPRESSION \
	CONFIG_OPENSSL11_WITH_DEPRECATED \
	CONFIG_OPENSSL11_WITH_DTLS \
	CONFIG_OPENSSL11_WITH_EC \
	CONFIG_OPENSSL11_WITH_EC2M \
	CONFIG_OPENSSL11_WITH_GOST \
	CONFIG_OPENSSL11_WITH_IDEA \
	CONFIG_OPENSSL11_WITH_MDC2 \
	CONFIG_OPENSSL11_WITH_NPN \
	CONFIG_OPENSSL11_WITH_PSK \
	CONFIG_OPENSSL11_WITH_RFC3779 \
	CONFIG_OPENSSL11_WITH_SEED \
	CONFIG_OPENSSL11_WITH_SM234 \
	CONFIG_OPENSSL11_WITH_SRP \
	CONFIG_OPENSSL11_WITH_SSE2 \
	CONFIG_OPENSSL11_WITH_TLS13 \
	CONFIG_OPENSSL11_WITH_WHIRLPOOL

include $(INCLUDE_DIR)/package.mk

ifneq ($(CONFIG_CCACHE),)
HOSTCC=$(HOSTCC_NOCACHE)
HOSTCXX=$(HOSTCXX_NOCACHE)
endif

define Package/$(PKG_NAME)/Default
  TITLE:=Open source SSL toolkit
  URL:=http://www.openssl.org/
  SECTION:=libs
  CATEGORY:=Libraries
endef

define Package/libopenssl1.1/config
source "$(SOURCE)/Config.in"
endef

define Package/openssl1.1/Default/description
The OpenSSL Project is a collaborative effort to develop a robust,
commercial-grade, full-featured, and Open Source toolkit implementing the
Transport Layer Security (TLS) and Secure Sockets Layer (SSL) protocols as well
as a full-strength general-purpose cryptography library.
endef

define Package/libopenssl1.1
$(call Package/openssl1.1/Default)
  SUBMENU:=SSL
  DEPENDS:=+OPENSSL11_WITH_COMPRESSION:zlib
  TITLE+= (libraries)
  ABI_VERSION:=$(PKG_VERSION)
  MENU:=1
endef

define Package/libopenssl1.1/description
$(call Package/openssl/Default/description)
This package contains the OpenSSL shared libraries, needed by other programs.
endef


define Package/libopenssl1.1/conffiles
/etc/ssl/openssl.cnf
endef

# do NOT interfere original openssl staging dir
MY_PKG_STAGING_DIR:=$(BUILD_DIR)/openssl1.1_staging_dir

OPENSSL_OPTIONS:= shared no-err


ifndef CONFIG_OPENSSL11_WITH_BLAKE2
  OPENSSL_OPTIONS += no-blake2
endif
ifndef CONFIG_OPENSSL11_WITH_CHACHA_POLY1305
  OPENSSL_OPTIONS += no-chacha no-poly1305
else
  ifdef CONFIG_OPENSSL11_PREFER_CHACHA_OVER_GCM
    OPENSSL_OPTIONS += -DOPENSSL_PREFER_CHACHA_OVER_GCM
  endif
endif
ifndef CONFIG_OPENSSL11_WITH_ASYNC
  OPENSSL_OPTIONS += no-async
endif

ifndef CONFIG_OPENSSL11_WITH_EC
  OPENSSL_OPTIONS += no-ec
endif

ifndef CONFIG_OPENSSL11_WITH_EC2M
  OPENSSL_OPTIONS += no-ec2m
endif


  ifndef CONFIG_OPENSSL11_WITH_TLS13
    OPENSSL_OPTIONS += no-tls1_3
  endif
  ifndef CONFIG_OPENSSL11_WITH_ARIA
    OPENSSL_OPTIONS += no-aria
  endif
  ifndef CONFIG_OPENSSL11_WITH_SM234
    OPENSSL_OPTIONS += no-sm2 no-sm3 no-sm4
  endif


ifndef CONFIG_OPENSSL11_WITH_CAMELLIA
  OPENSSL_OPTIONS += no-camellia
endif

ifndef CONFIG_OPENSSL11_WITH_IDEA
  OPENSSL_OPTIONS += no-idea
endif

ifndef CONFIG_OPENSSL11_WITH_SEED
  OPENSSL_OPTIONS += no-seed
endif

ifndef CONFIG_OPENSSL11_WITH_MDC2
  OPENSSL_OPTIONS += no-mdc2
endif

ifndef CONFIG_OPENSSL11_WITH_WHIRLPOOL
  OPENSSL_OPTIONS += no-whirlpool
endif

ifndef CONFIG_OPENSSL11_WITH_CMS
  OPENSSL_OPTIONS += no-cms
endif

# rfc3779 defaults as enabled in 1.1.0 and disabled in 1.0.2
ifndef CONFIG_OPENSSL11_WITH_RFC3779
  OPENSSL_OPTIONS += no-rfc3779
else
  OPENSSL_OPTIONS += enable-rfc3779
endif

ifndef CONFIG_OPENSSL11_WITH_DEPRECATED
  OPENSSL_OPTIONS += no-deprecated
endif

ifeq ($(CONFIG_OPENSSL11_OPTIMIZE_SPEED),y)
  TARGET_CFLAGS := $(filter-out -O%,$(TARGET_CFLAGS)) -O3
else
  OPENSSL_OPTIONS += -DOPENSSL_SMALL_FOOTPRINT
endif

ifdef CONFIG_OPENSSL11_ENGINE
  ifdef CONFIG_OPENSSL11_ENGINE_CRYPTO
    OPENSSL_OPTIONS += -DHAVE_CRYPTODEV
    ifdef CONFIG_OPENSSL11_ENGINE_DIGEST
      OPENSSL_OPTIONS += -DUSE_CRYPTODEV_DIGESTS
    endif
  endif
else
  OPENSSL_OPTIONS += no-engine
endif

ifndef CONFIG_OPENSSL11_WITH_GOST
  OPENSSL_OPTIONS += no-gost
endif

ifndef CONFIG_OPENSSL11_WITH_DTLS
  OPENSSL_OPTIONS += no-dtls
endif

ifdef CONFIG_OPENSSL11_WITH_COMPRESSION
  OPENSSL_OPTIONS += zlib-dynamic
else
  OPENSSL_OPTIONS += no-comp
endif

ifndef CONFIG_OPENSSL11_WITH_NPN
  OPENSSL_OPTIONS += no-nextprotoneg
endif

ifndef CONFIG_OPENSSL11_WITH_PSK
  OPENSSL_OPTIONS += no-psk
endif

ifndef CONFIG_OPENSSL11_WITH_SRP
  OPENSSL_OPTIONS += no-srp
endif

ifndef CONFIG_OPENSSL11_WITH_ASM
  OPENSSL_OPTIONS += no-asm
endif

ifdef CONFIG_i386
  ifndef CONFIG_OPENSSL11_SSE2
    OPENSSL_OPTIONS += no-sse2
  endif
endif

OPENSSL_TARGET:=linux-$(CONFIG_ARCH)-openwrt

ifeq ($(CONFIG_x86_64)$(CONFIG_mips64)$(CONFIG_mips64el),y)
  OPENSSL_MAKEFLAGS += LIBDIR=lib
endif

STAMP_CONFIGURED := $(STAMP_CONFIGURED)_$(shell echo $(OPENSSL_OPTIONS) | mkhash md5)

define Build/Configure
	[ -f $(STAMP_CONFIGURED) ] || { \
		rm -f $(PKG_BUILD_DIR)/*.so.* $(PKG_BUILD_DIR)/*.a; \
		find $(PKG_BUILD_DIR) -name \*.o | xargs rm -f; \
		rm -rf $(MY_PKG_STAGING_DIR); \
	}
	(cd $(PKG_BUILD_DIR); \
		./Configure $(OPENSSL_TARGET) \
			--prefix=/usr \
			--openssldir=/etc/ssl \
			$(TARGET_CPPFLAGS) \
			$(TARGET_LDFLAGS) -ldl \
			$(OPENSSL_OPTIONS) \
			no-shared \
	)

endef

TARGET_CFLAGS += $(FPIC) -I$(CURDIR)/include -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

define Build/Compile
	+$(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR) \
		CROSS_COMPILE="$(TARGET_CROSS)" \
		CC="$(TARGET_CC)" \
		ASFLAGS="$(TARGET_ASFLAGS) -I$(PKG_BUILD_DIR)/crypto -c" \
		AR="$(TARGET_CROSS)ar" \
		RANLIB="$(TARGET_CROSS)ranlib" \
		OPENWRT_OPTIMIZATION_FLAGS="$(TARGET_CFLAGS)" \
		$(OPENSSL_MAKEFLAGS) \
		all
	
	$(MAKE) -C $(PKG_BUILD_DIR) \
		CROSS_COMPILE="$(TARGET_CROSS)" \
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
	$(INSTALL_DIR) $(MY_PKG_STAGING_DIR)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/{openssl,libcrypto,libssl}.pc $(MY_PKG_STAGING_DIR)/usr/lib/pkgconfig/
	[ -n "$(TARGET_LDFLAGS)" ] && $(SED) 's#$(TARGET_LDFLAGS)##g' $(MY_PKG_STAGING_DIR)/usr/lib/pkgconfig/{openssl,libcrypto,libssl}.pc || true
endef

define Build/Clean
	rm -rf $(MY_PKG_STAGING_DIR)
	$(call Build/Clean/Default)
endef

define Package/libopenssl1.1/install
	$(INSTALL_DIR) $(1)/etc/ssl
	$(CP) $(PKG_INSTALL_DIR)/etc/ssl/openssl.cnf $(1)/etc/ssl/
	$(INSTALL_DIR) $(1)/etc/ssl/certs
	$(INSTALL_DIR) $(1)/etc/ssl/private
	chmod 0700 $(1)/etc/ssl/private
	$(INSTALL_DIR) $(1)/usr/lib
	#$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/libcrypto.so.* $(1)/usr/lib/
	#$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/libssl.so.* $(1)/usr/lib/
	$(if $(CONFIG_OPENSSL11_ENGINE),$(INSTALL_DIR) $(1)/usr/lib/$(ENGINES_DIR))
endef

$(eval $(call BuildPackage,libopenssl1.1))
