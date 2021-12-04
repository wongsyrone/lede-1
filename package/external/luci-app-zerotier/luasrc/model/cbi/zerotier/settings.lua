a = Map("zerotier")
a.title = translate("ZeroTier")
a.description = translate("Zerotier is an open source, cross-platform and easy to use virtual LAN")

a:section(SimpleSection).template = "zerotier/zerotier_status"

t = a:section(NamedSection, "openwrt_network", "zerotier")
t.anonymous = true
t.addremove = false

e = t:option(Flag, "enabled", translate("Enable"))
e.default = 0
e.rmempty=false

e = t:option(Value, "config_path", translate("Persistent Configuration Folder"))
e.optional = true
e.default = "/etc/zerotier"
e.rmempty = true

e = t:option(Flag, "copy_config_path", translate("Copy Persistent Configuration Folder to RAM?"))
e.description = translate("copy Persistent Configuration Folder to RAM to prevent writing to flash")
e.default = 0
e.rmempty = false

e = t:option(DynamicList, "join", translate('ZeroTier Network ID'))
e.password = true
e.rmempty = false

e = t:option(Value, "secret", translate("Secret"))
e.password = true
e.default = ""
e.rmempty = false

e = t:option(Value, "public_portion", translate("Public portion"))
e.password = false
e.default = ""
e.rmempty = false

e = t:option(Flag, "nat", translate("Auto NAT Clients"))
e.description = translate("Allow zerotier clients access your LAN network")
e.default = 0
e.rmempty = false

e = t:option(DummyValue, "opennewwindow", translate("<input type=\"button\" class=\"cbi-button cbi-button-apply\" value=\"Zerotier.com\" onclick=\"window.open('https://my.zerotier.com/network')\" />"))
e.description = translate("Create or manage your zerotier network, and auth clients who could access")

return a
