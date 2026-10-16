include $(TOPDIR)/rules.mk

PKG_NAME:=nikki-service-guard
PKG_VERSION:=2026.10.16
PKG_RELEASE:=2
PKG_LICENSE:=GPL-3.0-only

include $(INCLUDE_DIR)/package.mk

define Package/nikki-service-guard
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Nikki independent proxy service coordination
  PKGARCH:=all
  DEPENDS:=+nikki +ucode +ucode-mod-fs +ucode-mod-uci +ucode-mod-ubus +ucode-mod-uloop +ucode-mod-socket +ucode-mod-digest
endef

define Build/Compile
endef

define Package/nikki-service-guard/conffiles
/etc/config/nikki_service_guard
/etc/nikki/guard/providers/trojan.yaml
endef

define Package/nikki-service-guard/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/init.d $(1)/etc/nikki/guard/providers
	$(INSTALL_CONF) ./files/guard.config $(1)/etc/config/nikki_service_guard
	$(INSTALL_CONF) ./files/trojan.yaml $(1)/etc/nikki/guard/providers/trojan.yaml
	$(INSTALL_BIN) ./files/guard.init $(1)/etc/init.d/nikki-service-guard
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/nikki-service-guard $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) ./files/guard.sh $(1)/usr/libexec/nikki-service-guard
	$(INSTALL_BIN) ./files/guard-exec.sh $(1)/usr/libexec/nikki-guard-exec
	$(INSTALL_DATA) ./files/*.uc $(1)/usr/share/nikki-service-guard/
	$(INSTALL_BIN) ./files/recover.sh $(1)/usr/share/nikki-service-guard/recover.sh
	$(INSTALL_DATA) ./files/keep $(1)/lib/upgrade/keep.d/nikki-service-guard
endef

$(eval $(call BuildPackage,nikki-service-guard))
