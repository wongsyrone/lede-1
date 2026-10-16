#!/bin/sh

# Called only under the native Nikki lock, after checking the live service and start flag.
. /lib/functions.sh
extra_command() { :; }
. /etc/init.d/nikki

config_load nikki
[ "$(uci -q get nikki.config.enabled)" = 1 ] || exit 1
[ -f "$STARTED_FLAG_PATH" ] || exit 1

# Reuse upstream routing/TUN recovery. The separate DNS guard stays installed throughout.
for family in -4 -6; do
	for table in "$(uci -q get nikki.routing.tproxy_route_table)" "$(uci -q get nikki.routing.tun_route_table)"; do
		case "$table" in ''|*[!0-9]*) exit 1 ;; esac
		[ "$table" -ge 1 ] && [ "$table" -le 252 ] || exit 1
		ip "$family" rule del table "$table" 2>/dev/null
		ip "$family" route flush table "$table" 2>/dev/null
	done
done
nft delete table inet nikki 2>/dev/null
service_started >/dev/null 2>&1
nft list table inet nikki >/dev/null 2>&1
