import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import prepare_backup as migration


def fixture(device):
    second = device == "10.0.1.1"
    subnet = "10.0.1" if second else "10.0.0"
    modem = "192.168.100" if second else "192.168.1"
    ports = range(1, 4 if second else 6)
    text = {
        "etc/config/network": f"""
config interface 'lan'
 option proto 'static'
 option ipaddr '{device}'
 option netmask '255.255.255.0'
 option device 'br-lan'
 option ip6assign '64'
 list ip6class 'wan_6'
config interface 'wan'
 option proto 'pppoe'
 option device 'eth0'
 option username 'fake-{device}@test'
 option password 'fake pppoe with space and quote\\'x'
 option peerdns '0'
 option ipv6 'auto'
 list dns '::1'
 list dns '127.0.0.1'
config device
 option type 'bridge'
 option name 'br-lan'
 option stp '1'
 option igmp_snooping '1'
""" + "".join(f" list ports 'eth{p}'\n" for p in ports) + f"""
config interface 'modem'
 option proto 'static'
 option device 'eth0'
 option ipaddr '{modem}.140'
 option gateway '{modem}.1'
 option defaultroute '0'
config interface 'ztohdin5bo'
 option device 'ztohdin5bo'
 option proto 'none'
""",
        "etc/config/dhcp": f"""
config dnsmasq
 option domain 'lan'
 option local '/lan/'
 option resolvfile '/tmp/resolv.conf.d/resolv.conf.auto'
config dhcp 'lan'
 option interface 'lan'
 option start '100'
 option dhcpv6 'server'
 option ra 'server'
config host
 option name 'test-static-option'
 option mac '02:00:00:00:00:01'
 option ip '{subnet}.201'
config host
 option name 'test-static-list'
 list mac '02:00:00:00:00:02'
 option ip '{subnet}.202'
""",
        "etc/config/firewall": f"""
config defaults
 option input 'REJECT'
 option output 'ACCEPT'
 option forward 'DROP'
 option fullcone '1'
config zone
 option name 'lan'
 list network 'lan'
 option input 'ACCEPT'
config zone
 option name 'wan'
 list network 'wan'
 option fullcone6 '{1 if second else 0}'
config ipset
 option name 'setmefree'
 option family 'ipv4'
 list entry '192.0.2.0/24'
config ipset
 option name 'setmefree6'
 option family 'ipv6'
 list entry '2001:db8::/32'
config include 'miniupnpd'
 option path '/usr/share/miniupnpd/firewall.include'
config zone 'zt_zone_ztohdin5bo'
 option name 'zerotier'
 option network 'ztohdin5bo'
 option input 'ACCEPT'
 option forward 'ACCEPT'
 option masq '1'
config forwarding 'zt_fwd_ztohdin5bo2lan'
 option src 'zerotier'
 option dest 'lan'
config forwarding 'zt_fwd_lan2ztohdin5bo'
 option src 'lan'
 option dest 'zerotier'
""" + "".join(f"""
config rule '{name}'
 option name '{label}'
 option src '*'
 option target 'ACCEPT'
 list proto 'all'
 option dest_port '{port}'
""" for name, label, port in [
    ("zt_rule_allowInbound", "Allow-ZeroTier-Inbound", 19993),
    ("zt_rule_allowSecondPort", "Allow-ZeroTier-2ndPort", 21001 if second else 21000),
    ("zt_rule_allowThirdPort", "Allow-ZeroTier-3rdPort", 31001 if second else 31000),
]),
        "etc/config/dropbear": "config dropbear\n option Port '444'\n",
        "etc/config/zerotier": "config zerotier 'openwrt_network'\n option enabled '1'\n option nat '1'\n",
        "etc/config/trojan": "config trojan\n option enabled '1'\n",
        "etc/trojan.json": json.dumps({
            "run_type": "client", "local_addr": device, "local_port": 1081,
            "remote_addr": "proxy.invalid", "remote_port": 443, "password": ["fake-trojan-secret"],
            "ssl": {"verify": True, "verify_hostname": True}, "tcp": {"reuse_port": True},
        }),
        "etc/zerotier/identity.secret": f"FAKE-IDENTITY-SECRET-{device}",
        "etc/zerotier/identity.public": f"FAKE-IDENTITY-PUBLIC-{device}",
        "etc/zerotier/planet": "FAKE-PLANET",
        "etc/zerotier/networks.d/0123456789abcdef.local.conf": "allowDNS=0\nallowManaged=1\n",
        "etc/dropbear/dropbear_ed25519_host_key": "FAKE-HOST-KEY",
        "etc/passwd": "root:x:0:0:root:/root:/bin/ash\n",
        "etc/group": "root:x:0:\n",
        "etc/shadow": "root:FAKE-HASH:0:0:99999:7:::\n",
        "etc/rc.local": "echo 3 > /proc/sys/net/ipv4/tcp_fastopen\nexit 0\n",
        "etc/uci-defaults/10_disable_services": "/etc/init.d/samba4 disable\n\nexit 0\n",
        "etc/sysupgrade.conf": "/etc/dnsmasq.conf\n/etc/dnsmasq.d/\n/usr/sbin/v2ray\n/etc/v2ray*.json\n/etc/trojan.json\n/etc/zerotier/planet\n",
        "etc/dnsmasq.conf": "# existing directory loading\nconf-dir=/etc/dnsmasq.d/,*.conf\n",
        "etc/dnsmasq.d/option.conf": f"no-resolv\nno-poll\nno-negcache\nall-servers\nmin-cache-ttl=1800\ncache-size=10000\nsrv-host=_vlmcs._tcp,{'second' if second else 'first'},1688,0,100\n",
        "etc/dnsmasq.d/server.conf": "server=::1#8153\n",
        "etc/dnsmasq.d/gfw-nftset.conf": "nftset=/example.invalid/4#inet#fw4#setmefree,6#inet#fw4#setmefree6\n",
        "etc/dnsmasq.d/local-self-nftset.conf": "server=/example.invalid/222.222.202.202\naddress=/my-router.lan/127.0.0.1\n",
        "etc/dnsmasq.d/accelerated-domains.china.conf": "server=/example.cn/114.114.114.114\n",
        "etc/nftables.d/20-setmefree.nft": "chain setmefree { type nat hook prerouting priority dstnat; meta l4proto tcp ip daddr @setmefree redirect to :8123; }\n",
        "etc/nftables.d/10-custom-filter-chains.nft": "chain ssh_ban_pre_input { type filter hook input priority -1; ip saddr 192.0.2.2 drop; }\n",
        "etc/nftables.d/99-zerotier-auto-nat-auto-generated-do-not-touch.nft": 'chain zt_auto_nat_post_rt { type nat hook postrouting priority srcnat; oifname "ztohdin5bo" masquerade; }\n',
        "etc/config/pdnsd": "config pdnsd\n option enabled '1'\n",
        "etc/config/transocks-wong": "config transocks-wong\n option enabled '1'\n",
        "etc/pdnsd.conf": "FAKE-PDNSD-CONFIG",
        "usr/sbin/v2ray": "FAKE-OLD-BINARY",
    }
    # Real UCI quoting: a single quote is expressed outside the surrounding single-quoted string.
    text["etc/config/network"] = text["etc/config/network"].replace(
        "'fake pppoe with space and quote\\'x'", "'fake pppoe with space and quote'\\''x'"
    )
    if second:
        text["etc/config/dhcp"] = text["etc/config/dhcp"].replace(
            " option domain 'lan'", " option domain 'lan'\n option confdir '/etc/dnsmasq.d'"
        )
        text["etc/dnsmasq.conf"] = "# directory loading is configured through UCI\n"
    return {name: value.encode() for name, value in text.items()}


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.uci = shutil.which(os.environ.get("UCI", "uci"))
        self.assertIsNotNone(self.uci, "Set UCI to a native libuci executable")

    def archive(self, files, extra=()):
        path = self.directory / f"input-{len(list(self.directory.glob('*.tar.gz')))}.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o600 if name.endswith(("identity.secret", "/shadow", "host_key", "trojan.json")) else 0o644
                archive.addfile(info, io.BytesIO(data))
            for info, data in extra:
                archive.addfile(info, io.BytesIO(data))
        return path

    def prepare(self, source, device="10.0.0.1", files=None, identity=None):
        if identity is None:
            identity = hashlib.sha256((files or fixture(device))["etc/zerotier/identity.secret"]).hexdigest()
        return migration.prepare(source, device, identity, self.uci)

    def test_both_devices_preserve_core_trojan_identity_and_service_state(self):
        for device in ("10.0.0.1", "10.0.1.1"):
            with self.subTest(device=device):
                files = fixture(device)
                source = self.archive(files)
                before = source.read_bytes()
                entries, plan = self.prepare(source, device, files)
                for name, data in files.items():
                    if name in plan["protected"]:
                        self.assertEqual(entries[name][1], data, name)
                self.assertEqual(source.read_bytes(), before)
                self.assertNotIn("etc/config/pdnsd", entries)
                self.assertNotIn("usr/sbin/v2ray", entries)
                self.assertIn(b"/etc/trojan.json", entries["etc/sysupgrade.conf"][1])
                self.assertNotIn(b"/usr/sbin/v2ray", entries["etc/sysupgrade.conf"][1])
                self.assertIn(b"address=/my-router.lan/127.0.0.1", entries["etc/dnsmasq.d/migration-local.conf"][1])
                self.assertNotIn(b"222.222", entries["etc/dnsmasq.d/migration-local.conf"][1])
                self.assertNotIn("fake-trojan-secret", json.dumps(plan))
                self.assertNotIn("FAKE-HASH", json.dumps(plan))
                self.assertTrue(any(c["action"] == "exclude" for c in plan["changes"]))

    def test_native_output_and_idempotent_second_pass(self):
        files = fixture("10.0.0.1")
        entries, plan = self.prepare(self.archive(files))
        output = self.directory / "output.tar.gz"
        migration.write_backup(output, entries)
        again, repeated = self.prepare(output)
        self.assertEqual(repeated["changes"], [])
        self.assertEqual({n: b for n, (_, b) in entries.items()}, {n: b for n, (_, b) in again.items()})
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(again["etc/zerotier/identity.secret"][0].mode, 0o600)
        with self.assertRaises(FileExistsError):
            migration.write_backup(output, entries)

    def test_wrong_device_or_identity_rejected(self):
        source = self.archive(fixture("10.0.0.1"))
        for kwargs in ({"device": "10.0.1.1"}, {"identity": "0" * 64}):
            with self.subTest(kwargs=kwargs), self.assertRaises(migration.Rejected):
                self.prepare(source, **kwargs)

    def test_missing_essential_file_rejected(self):
        for missing in ("etc/zerotier/identity.secret", "etc/shadow", "etc/config/network", "etc/trojan.json", "etc/uci-defaults/10_disable_services"):
            files = fixture("10.0.0.1")
            files.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(files))

    def test_identity_permissions_truncated_archive_and_size_limit(self):
        files = fixture("10.0.0.1")
        identity = tarfile.TarInfo("etc/zerotier/identity.secret")
        identity.mode = 0o644
        identity.size = len(files.pop(identity.name))
        source = self.archive(files, [(identity, b"x" * identity.size)])
        with self.assertRaises(migration.Rejected):
            self.prepare(source)
        source = self.archive(fixture("10.0.0.1"))
        source.write_bytes(source.read_bytes()[:100])
        with self.assertRaises(migration.Rejected):
            self.prepare(source)
        source = self.archive(fixture("10.0.0.1"))
        previous_limit = migration.MAX_BYTES
        try:
            migration.MAX_BYTES = 512
            with self.assertRaises(migration.Rejected):
                self.prepare(source)
        finally:
            migration.MAX_BYTES = previous_limit

    def test_unknown_firewall_include_or_hook_rejected(self):
        for name, data in (
            ("etc/config/firewall", b"\nconfig include\n option path '/etc/unknown-firewall'\n"),
            ("etc/uci-defaults/custom", b"exit 0\n"),
            ("etc/rc.local", b"\n/etc/init.d/transocks-wong restart\n"),
            ("etc/crontabs/root", b"* * * * * /root/custom-task\n"),
            ("etc/dnsmasq.conf", b"\nconf-file=/etc/extra-dns\n"),
            ("etc/init.d/custom", b"#!/bin/sh\n"),
        ):
            files = fixture("10.0.0.1")
            files[name] = files.get(name, b"") + data
            with self.subTest(name=name), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(files))

    def test_unknown_dns_or_nft_includes_rejected(self):
        for name, data in (
            ("etc/dnsmasq.d/custom.conf", b"server=127.0.0.1#9000\n"),
            ("etc/dnsmasq.d/server.conf", b"dhcp-option=6,1.2.3.4\n"),
            ("etc/nftables.d/custom.nft", b"chain custom {}\n"),
        ):
            files = fixture("10.0.0.1")
            files[name] = data
            with self.subTest(name=name), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(files))

    def test_known_uci_dns_directory_is_preserved_and_other_paths_rejected(self):
        files = fixture("10.0.1.1")
        entries, _ = self.prepare(self.archive(files), device="10.0.1.1", files=files)
        self.assertIn(b"confdir '/etc/dnsmasq.d'", entries["etc/config/dhcp"][1])
        for path in ("/etc/extra-dns", "/etc/dnsmasq.d/../extra-dns", "/tmp/dnsmasq.d"):
            changed = dict(files)
            changed["etc/config/dhcp"] = files["etc/config/dhcp"].replace(
                b"/etc/dnsmasq.d", path.encode()
            )
            with self.subTest(path=path), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(changed), device="10.0.1.1", files=changed)

    def test_malformed_config_or_trojan_shape_rejected(self):
        for name, data in (("etc/config/network", b"config 'unterminated"), ("etc/trojan.json", b'{"local_addr":"127.0.0.1"}')):
            files = fixture("10.0.0.1")
            files[name] = data
            with self.subTest(name=name), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(files))

    def test_dangerous_paths_duplicates_and_links_rejected(self):
        for name, kind, link in (
            ("../../escape", tarfile.REGTYPE, ""),
            ("/etc/shadow", tarfile.REGTYPE, ""),
            ("etc/../escape", tarfile.REGTYPE, ""),
            ("etc/config/network", tarfile.REGTYPE, ""),
            ("etc/zerotier/identity.secret.link", tarfile.SYMTYPE, "/etc/shadow"),
            ("etc/zerotier/hardlink", tarfile.LNKTYPE, "etc/shadow"),
            ("etc/rc.d/S95trojan", tarfile.SYMTYPE, "../../etc/shadow"),
            ("etc/fifo", tarfile.FIFOTYPE, ""),
        ):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, link
            with self.subTest(name=name), self.assertRaises(migration.Rejected):
                self.prepare(self.archive(fixture("10.0.0.1"), [(info, b"")]))

    def test_valid_rc_link_preserves_trojan_but_excludes_retired_service(self):
        links = []
        for name in ("trojan", "pdnsd"):
            info = tarfile.TarInfo(f"etc/rc.d/S95{name}")
            info.type, info.linkname = tarfile.SYMTYPE, f"../init.d/{name}"
            links.append((info, b""))
        entries, _ = self.prepare(self.archive(fixture("10.0.0.1"), links))
        self.assertIn("etc/rc.d/S95trojan", entries)
        self.assertNotIn("etc/rc.d/S95pdnsd", entries)

    def test_plan_confirmation_is_bound_to_exact_input_and_result(self):
        entries, plan = self.prepare(self.archive(fixture("10.0.0.1")))
        migration.verify_plan(plan, copy.deepcopy(plan))
        for key in ("source_sha256", "device", "result_sha256"):
            changed = copy.deepcopy(plan)
            changed[key] = "changed"
            with self.subTest(key=key), self.assertRaises(migration.Rejected):
                migration.verify_plan(plan, changed)

    def test_disabled_trojan_state_is_preserved(self):
        files = fixture("10.0.0.1")
        files["etc/uci-defaults/10_disable_services"] = b"/etc/init.d/trojan disable\nexit 0\n"
        entries, _ = self.prepare(self.archive(files))
        self.assertEqual(entries["etc/uci-defaults/10_disable_services"][1], files["etc/uci-defaults/10_disable_services"])

    def test_cli_preview_then_confirmed_output_and_refuse_stale_plan(self):
        files = fixture("10.0.0.1")
        source = self.archive(files)
        original = source.read_bytes()
        command = [sys.executable, str(Path(migration.__file__)), str(source),
                   "--device", "10.0.0.1", "--identity-sha256",
                   hashlib.sha256(files["etc/zerotier/identity.secret"]).hexdigest(), "--uci", self.uci]
        preview = subprocess.run(command, text=True, capture_output=True, check=True)
        self.assertNotIn("fake pppoe", preview.stdout + preview.stderr)
        plan = self.directory / "reviewed-plan.json"
        plan.write_text(preview.stdout)
        output = self.directory / "confirmed-output.tar.gz"
        subprocess.run(command + ["--apply-plan", str(plan), "--output", str(output)],
                       text=True, capture_output=True, check=True)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(output.exists())
        # A stale or edited plan cannot authorize a changed transformation.
        payload = json.loads(plan.read_text())
        payload["changes"] = []
        plan.write_text(json.dumps(payload))
        another = self.directory / "must-not-exist.tar.gz"
        failed = subprocess.run(command + ["--apply-plan", str(plan), "--output", str(another)],
                                text=True, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(another.exists())


if __name__ == "__main__":
    unittest.main()
