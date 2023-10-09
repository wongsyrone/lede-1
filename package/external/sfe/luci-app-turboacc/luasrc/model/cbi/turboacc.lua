local kernel_version = luci.sys.exec("echo -n $(uname -r)")

m = Map("turboacc")
m.title	= translate("Turbo ACC Acceleration Settings")
m.description = translate("Opensource Flow Offloading driver (Fast Path or Hardware NAT)")

m:append(Template("turboacc/turboacc_status"))

s = m:section(TypedSection, "turboacc", "")
s.addremove = false
s.anonymous = true

-- nftables: nft_flow_offload is built-in mod
if nixio.fs.access("/lib/modules/" .. kernel_version .. "/nft_flow_offload.ko") then
sw_flow = s:option(Flag, "sw_flow", translate("Software flow offloading"))
sw_flow.default = 0
sw_flow.description = translate("Software based offloading for routing/NAT")
sw_flow:depends("sfe_flow", 0)
end

if luci.sys.call("cat /etc/openwrt_release | grep -Eq 'filogic|mt762' ") == 0 then
hw_flow = s:option(Flag, "hw_flow", translate("Hardware flow offloading"))
hw_flow.default = 0
hw_flow.description = translate("Requires hardware NAT support, implemented at least for mt762x")
hw_flow:depends("sw_flow", 1)
end

if nixio.fs.access("/lib/modules/" .. kernel_version .. "/shortcut-fe-cm.ko")
or nixio.fs.access("/lib/modules/" .. kernel_version .. "/fast-classifier.ko")
then
sfe_flow = s:option(Flag, "sfe_flow", translate("Shortcut-FE flow offloading"))
sfe_flow.default = 0
sfe_flow.description = translate("Shortcut-FE based offloading for routing/NAT")
sfe_flow:depends("sw_flow", 0)
end

fullcone_nat = s:option(Flag, "fullcone_nat", translate("FullCone NAT Global Switch"))
fullcone_nat.default = 0
fullcone_nat.description = translate("Using FullCone NAT can improve gaming performance effectively")

fullcone_nat_mode = s:option(ListValue, "fullcone_nat_mode", translate("FullCone NAT Mode"))
fullcone_nat_mode.default = 0
fullcone_nat_mode:value("0", translate("nft_fullcone originated from Chion82"))
fullcone_nat_mode:value("1", translate("Broadcom ASUS Merlin fullconenat in masquerade"))
fullcone_nat_mode.description = translate("Using FullCone NAT can improve gaming performance effectively")

return m
