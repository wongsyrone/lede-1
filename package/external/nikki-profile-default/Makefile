include $(TOPDIR)/rules.mk
include $(CURDIR)/rules.mk

PKG_NAME:=nikki-profile-default
PKG_VERSION:=$(or $(RULES_VERSION),2026.10.16)
PKG_RELEASE:=3
PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=LICENSE.rules
PKG_FILE_DEPENDS:=$(CURDIR)/rules.mk

include $(INCLUDE_DIR)/package.mk

define Package/nikki-profile-default
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Public router profile and initial rule data for Nikki
  PKGARCH:=all
  DEPENDS:=+nikki +nikki-service-guard +@KERNEL_CGROUPS +@KERNEL_CGROUP_BPF
endef

define RuleDownload
  define Download/rule-$(1)
    URL:=https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/$$(RULES_REV)/$(dir $(2))
    URL_FILE:=$(notdir $(2))
    FILE:=nikki-rule-$$(RULES_REV)-$(1).mrs
    HASH:=$(3)
  endef
  $$(eval $$(call Download,rule-$(1)))
  RULE_NAMES += $(1)
endef

$(Rules/Downloads)

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/nikki-profile-default/conffiles
/etc/nikki/profiles/default.yaml
/etc/nikki/run/providers/proxy/user.yaml
/etc/nikki/run/providers/rule/proxy-domains-extra.yaml
/etc/nikki/run/providers/rule/UK-wifi-call.yaml
/etc/nikki/run/providers/rule/US-wifi-call.yaml
/etc/nikki/run/providers/rule/HK-wifi-call.yaml
/etc/nikki/run/providers/rule/DE-wifi-call.yaml
endef

define Package/nikki-profile-default/install
	$(INSTALL_DIR) $(1)/etc/nikki/profiles $(1)/etc/nikki/run/providers/proxy $(1)/etc/nikki/run/providers/rule
	$(INSTALL_CONF) ./files/default.yaml $(1)/etc/nikki/profiles/default.yaml
	$(INSTALL_CONF) ./files/user.yaml $(1)/etc/nikki/run/providers/proxy/user.yaml
	$(INSTALL_DATA) ./files/rules/*.yaml $(1)/etc/nikki/run/providers/rule/
	$(foreach rule,$(RULE_NAMES),$(INSTALL_DATA) $(DL_DIR)/nikki-rule-$(RULES_REV)-$(rule).mrs $(1)/etc/nikki/run/providers/rule/$(rule).mrs;)
	$(INSTALL_DIR) $(1)/etc/uci-defaults $(1)/usr/share/doc/nikki-profile-default
	$(INSTALL_BIN) ./files/99_nikki-profile-default $(1)/etc/uci-defaults/99_nikki-profile-default
	$(INSTALL_DATA) ./LICENSE.rules $(1)/usr/share/doc/nikki-profile-default/LICENSE.rules
	$(INSTALL_DATA) ./rules.mk $(1)/usr/share/doc/nikki-profile-default/rules.mk
endef

$(eval $(call BuildPackage,nikki-profile-default))
