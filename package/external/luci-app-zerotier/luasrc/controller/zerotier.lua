module("luci.controller.zerotier",package.seeall)

local fs = require "nixio.fs"

function index()
	if not nixio.fs.access("/etc/config/zerotier") then
		return
	end

	entry({"admin","vpn"}, firstchild(), "VPN", 45).dependent = false

	entry({"admin", "vpn", "zerotier"},firstchild(), _("ZeroTier")).dependent = false

	entry({"admin", "vpn", "zerotier", "general"}, cbi("zerotier/settings"), _("Base Setting"), 1)
	entry({"admin", "vpn", "zerotier", "log"}, form("zerotier/info"), _("Interface Info"), 2)

	entry({"admin", "vpn", "zerotier", "status"}, call("act_status"))
	entry({"admin", "vpn", "zerotier", "nic_status"}, call("action_nic_status"))
end

function act_status()
	local e = {}
	e.running = luci.sys.call("pgrep /usr/bin/zerotier-one >/dev/null") == 0
	luci.http.prepare_content("application/json")
	luci.http.write_json(e)
end

function action_nic_status()
	local e = {}
	luci.sys.exec("for i in $(ifconfig | grep 'zt' | awk '{print $1}'); do ifconfig $i; done > /tmp/zerotier-nic.info")
	local content = fs.readfile("/tmp/zerotier-nic.info")
	if content == '' then
		content = nil
	end
	e.nic_status = content or "zerotier nic info not ready"
	e.nic_status = e.nic_status:gsub("<", "[")
	e.nic_status = e.nic_status:gsub(">", "]")

	luci.sys.exec("zerotier-cli peers > /tmp/zerotier-peers.info 2>&1")
	local content = fs.readfile("/tmp/zerotier-peers.info")
	if content == '' then
		content = nil
	end
	e.peers_status = content or "zerotier peers info not ready"
	e.peers_status = e.peers_status:gsub("<", "[")
	e.peers_status = e.peers_status:gsub(">", "]")

	luci.sys.exec("zerotier-cli listnetworks > /tmp/zerotier-networks.info 2>&1")
	local content = fs.readfile("/tmp/zerotier-networks.info")
	if content == '' then
		content = nil
	end
	e.networks_status = content or "zerotier networks info not ready"
	e.networks_status = e.networks_status:gsub("<", "[")
	e.networks_status = e.networks_status:gsub(">", "]")

	luci.http.prepare_content("application/json")
	luci.http.write_json(e)
end
