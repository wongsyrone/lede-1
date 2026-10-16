import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import test_defaults as defaults


MERGE = '... comments="" | . as $item ireduce ({}; . * $item ) | .proxies = .nikki-proxies + .proxies | del(.nikki-proxies) | .proxy-groups = .nikki-proxy-groups + .proxy-groups | del(.nikki-proxy-groups) | .rules = .nikki-rules + .rules | del(.nikki-rules) | explode(.)'
TUN = '(.tun) |= (.auto-route = false | .auto-redirect = false | .auto-detect-interface = false | .disable-icmp-forwarding = true)'


class MixinTest(unittest.TestCase):
    def setUp(self):
        self.fixture = defaults.DefaultsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.apply()
        self.path = self.fixture.path
        self.ucode = shutil.which(os.environ.get("UCODE", "ucode"))
        self.yq = shutil.which(os.environ.get("YQ", "yq"))
        self.core = shutil.which(os.environ.get("MIHOMO", "mihomo"))
        self.assertTrue(all((self.ucode, self.yq, self.core)), "Set UCODE, YQ and MIHOMO to native executables")
        self.nikki = defaults.ROOT / "feeds/nikki/nikki/files"
        self.package_root = Path(os.environ["PKG_ROOT"])
        self.root = self.path / "root"
        shutil.copytree(self.package_root / "etc/nikki", self.root / "etc/nikki")
        runtime = self.root / "var/run/nikki-service-guard"
        runtime.mkdir(parents=True)
        (runtime / "external-trojan.yaml").write_text(json.dumps({
            "proxies": [{"name": "__guard_down__trojan", "type": "reject"}],
        }))
        (runtime / "domains.yaml").write_text('payload: []\n')
        shutil.copyfile(defaults.PACKAGE / "files/default.yaml", self.root / "etc/nikki/profiles/default.yaml")
        self.modules = self.path / "modules"
        self.modules.mkdir()
        # Only ubus network status and host topology are mocked; UCI and generators are real.
        (self.modules / "ubus.uc").write_text('export function connect() { return { call: function(object, method, data) { if (object != "network.interface" || method != "status") die("unexpected ubus call"); return data.interface == "lan" ? { device: "br-lan" } : {}; } }; }\n')

    def run_command(self, *args):
        result = subprocess.run(args, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def relocate_generator(self, source):
        source = source.replace("'/etc/nikki/ucode/include.uc'", json.dumps(str(self.nikki / "ucode/include.uc")))
        return source.replace("cursor()", "cursor(" + ",".join(map(json.dumps, map(str, (
            self.fixture.config, self.fixture.save, self.fixture.override,
        )))) + ")")

    def assemble(self, user_nodes=None):
        if user_nodes:
            (self.root / "etc/nikki/run/providers/proxy/user.yaml").write_text(json.dumps({"proxies": user_nodes}))
        init = (self.nikki / "nikki.init").read_text()
        self.assertIn(MERGE, init, "Review changed upstream merge semantics")
        self.assertIn(TUN, init, "Review changed upstream TUN handling")
        mixin_uc = self.path / "mixin.uc"
        mixin_uc.write_text(self.relocate_generator((self.nikki / "ucode/mixin.uc").read_text()))
        mixin_json = self.path / "mixin.json"
        mixin_json.write_text(self.run_command(self.ucode, "-L", str(self.modules), "-S", str(mixin_uc)))
        mixin_yaml = self.path / "mixin.yaml"
        mixin_yaml.write_text(self.run_command(self.yq, "-M", "-p", "json", "-o", "yaml", str(mixin_json)))
        final = self.path / "config.yaml"
        final.write_text(self.run_command(self.yq, "-M", "eval-all", MERGE, str(self.root / "etc/nikki/profiles/default.yaml"), str(mixin_yaml)))
        self.run_command(self.yq, "-M", "-i", TUN, str(final))
        data = json.loads(self.run_command(self.yq, "-M", "-o", "json", str(final)))
        self.assertEqual(data["external-controller"], "127.0.0.1:9090")
        self.assertEqual(data["dns"]["listen"], "[::]:1053")
        self.assertFalse(data["tun"]["auto-route"])
        self.assertFalse(data["tun"]["auto-redirect"])
        self.assertTrue(data["dns"]["direct-nameserver-follow-policy"])
        self.assertEqual(data["socks-port"], 1080)  # Independent Trojan stays on 1081.
        for provider in [*data["proxy-providers"].values(), *data["rule-providers"].values()]:
            path = provider.get("path", "")
            if path.startswith(("/etc/nikki/", "/var/run/nikki-service-guard/")):
                provider["path"] = str(self.root / path.lstrip("/"))
                self.assertTrue(Path(provider["path"]).is_file())
        final.write_text(json.dumps(data, ensure_ascii=False))
        self.run_command(self.core, "-t", "-d", str(self.root), "-f", str(final))
        return data

    def test_empty_public_profile_with_real_nikki_mixin(self):
        self.assemble()

    def test_imported_node_with_no_matching_regions(self):
        self.assemble([{"name": "test-no-region", "type": "socks5", "server": "127.0.0.1", "port": 11081}])

    def test_trojan_present_and_absent_never_create_a_wildcard_bypass(self):
        profile_json = self.path / "profile.json"
        profile_json.write_text(json.dumps(self.assemble(), ensure_ascii=False))
        (self.modules / "fw4.uc").write_text('return { hex: function(value) { return sprintf("0x%08x", value); } };\n')
        source = self.relocate_generator((self.nikki / "ucode/hijack.ut").read_text())
        source = source.replace("const profile = load_profile();", "const profile = json(require('fs').readfile(" + json.dumps(str(profile_json)) + "));")
        source = source.replace("get_cgroups_version()", "2")
        source = source.replace("get_users()", json.dumps(["root", "dnsmasq", "ftp", "logd", "nobody", "ntp", "ubus"]))
        source = source.replace("get_groups()", json.dumps(["root", "dnsmasq", "ftp", "logd", "nogroup", "ntp", "ubus"]))
        template = self.path / "hijack.ut"
        for present in (False, True):
            with self.subTest(trojan_running=present):
                cgroups = ["services/nikki", "services/zerotier", "services/dnsmasq"]
                if present:
                    cgroups.append("services/trojan")
                template.write_text(source.replace("get_cgroups()", json.dumps(cgroups)))
                rendered = self.run_command(self.ucode, "-L", str(self.modules), "-T", str(template))
                self.assertEqual(rendered.count('"services/trojan"'), 4 if present else 0)
                self.assertNotRegex(rendered, r'meta (?:skuid|skgid) [^\n]*\broot\b')
                chains = {name: rendered.split("\tchain " + name + " {", 1)[1].split("\n\t}", 1)[0]
                          for name in ("router_dns_hijack", "router_redirect", "router_tun")}
                returns = [line for name, chain in chains.items() for line in chain.splitlines()
                           if re.search(r"counter return #\s*$", line)
                           and (name != "router_tun" or "th dport 53" not in line)]
                self.assertTrue(returns)
                self.assertTrue(all(re.search(r"meta skuid|meta skgid|socket cgroupv2", line) for line in returns), returns)


if __name__ == "__main__":
    unittest.main()
