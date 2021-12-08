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

e = t:option(Flag, "allowDNS", translate("Let ZeroTier modify the system's DNS settings"))
e.default = 1
e.rmempty=false

e = t:option(Flag, "allowDefault", translate("Let ZeroTier modify the system's default route"))
e.default = 0
e.rmempty=false

e = t:option(Flag, "allowGlobal", translate("Let ZeroTier manage IP addresses and route assignments that aren't in private ranges (rfc1918)"))
e.default = 1
e.rmempty=false

e = t:option(Flag, "allowManaged", translate("Let ZeroTier manage IP addresses and Route assignments"))
e.default = 1
e.rmempty=false

e = t:option(Value, "port", translate("Port"))
e.optional = true
e.datatype = "and(uinteger,max(65535))"
e.default = "9993"
e.rmempty = true

e = t:option(DynamicList, "join", translate('ZeroTier Network ID'))
e.password = true
e.rmempty = false

e = t:option(Value, "secret", translate("Secret"))
e.optional = true
e.password = true
e.default = ""
e.rmempty = false

e = t:option(Value, "public_portion", translate("Public portion"))
e.optional = true
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
