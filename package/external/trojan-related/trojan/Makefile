#
# Copyright (C) 2018-2020 wongsyrone
#
# This is free software, licensed under the GNU General Public License v3.
# See /LICENSE for more information.
#
include $(TOPDIR)/rules.mk

PKG_NAME:=trojan
PKG_VERSION:=1.16.0
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=https://github.com/trojan-gfw/trojan.git
PKG_MIRROR_HASH:=2f7f60ae2ef6e57b9565b984df2e7b9560786ad0a63402e93523804f140e39ca
PKG_SOURCE_SUBDIR:=$(PKG_NAME)-$(PKG_VERSION)
PKG_SOURCE_VERSION:=8606b7110fe79f8ab02d60c897f87ffb0a9b23f0
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-$(PKG_SOURCE_VERSION).tar.gz
CMAKE_INSTALL:=1
PKG_BUILD_PARALLEL:=1

PKG_BUILD_DEPENDS:=openssl3

PKG_LICENSE:=GPL-3.0

PKG_MAINTAINER:=GreaterFire

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

TARGET_CXXFLAGS += -Wall -Wextra
TARGET_CXXFLAGS += $(FPIC)

# LTO
TARGET_CXXFLAGS += -flto
TARGET_LDFLAGS += -flto

# CXX standard
TARGET_CXXFLAGS += -std=c++11

TARGET_CXXFLAGS := $(filter-out -O%,$(TARGET_CXXFLAGS)) -O3
MY_OPENSSL_DIR:=$(BUILD_DIR)/openssl3_staging_dir/usr

TARGET_CXXFLAGS += -ffunction-sections -fdata-sections
TARGET_LDFLAGS += -Wl,--gc-sections

CMAKE_FIND_ROOT_PATH := $(MY_OPENSSL_DIR);$(CMAKE_FIND_ROOT_PATH)
TARGET_CXXFLAGS := -I$(MY_OPENSSL_DIR)/include $(TARGET_CXXFLAGS)
TARGET_LDFLAGS := -L$(MY_OPENSSL_DIR)/lib $(TARGET_LDFLAGS)



CMAKE_OPTIONS += \
	-DENABLE_MYSQL=OFF \
	-DENABLE_NAT=ON \
	-DENABLE_REUSE_PORT=ON \
	-DENABLE_SSL_KEYLOG=ON \
	-DENABLE_TLS13_CIPHERSUITES=ON \
	-DFORCE_TCP_FASTOPEN=OFF \
	-DSYSTEMD_SERVICE=OFF \
	-DOPENSSL_USE_STATIC_LIBS=TRUE \
	-DBoost_DEBUG=ON \
	-DBoost_NO_BOOST_CMAKE=ON



define Package/trojan
	SECTION:=net
	CATEGORY:=Network
	TITLE:=An unidentifiable mechanism that helps you bypass GFW
	URL:=https://github.com/trojan-gfw/trojan
	DEPENDS:=+libpthread +libstdcpp \
		+boost +boost-system +boost-program_options +boost-date_time
endef



define Package/trojan/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/trojan $(1)/usr/sbin/trojan
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./files/trojan.config $(1)/etc/config/trojan
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/trojan.init $(1)/etc/init.d/trojan
	$(INSTALL_CONF) $(PKG_INSTALL_DIR)/etc/trojan/config.json $(1)/etc/trojan.json
endef

define Package/trojan/conffiles
/etc/config/trojan
/etc/trojan.json
endef

$(eval $(call BuildPackage,trojan))
