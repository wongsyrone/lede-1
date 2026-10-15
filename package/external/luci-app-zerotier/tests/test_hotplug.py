import os
import re
import subprocess
import unittest
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "root/etc/hotplug.d/net/99-zerotier").read_text()
ADD_EVENT = SOURCE[SOURCE.index('if [ "$ACTION" = "add" ]; then'):]

# Execute the real add-event body without touching UCI, services, or the firewall.
MOCKS = r"""
ACTION=add
INTERFACE=zt_test
FIRST_PORT_FILE=first-port
SECOND_PORT_FILE=second-port
THIRD_PORT_FILE=third-port
uci() {
    case "$*" in
        'get zerotier.openwrt_network.port') printf '%s\n' "$TEST_PORT" ;;
        'get zerotier.openwrt_network.join') : ;;
        '-q batch') /bin/cat ;;
        *) return 1 ;;
    esac
}
cat() {
    case "$1" in
        first-port) printf '%s\n' "$TEST_PORT" ;;
        second-port) printf '%s\n' "$TEST_SECOND_PORT" ;;
        third-port) printf '%s\n' "$TEST_THIRD_PORT" ;;
        *) return 1 ;;
    esac
}
my_log() { :; }
config_load() { :; }
remove_firewall_rules() { :; }
add_nftables_rule() { :; }
add_iptables_rule() { :; }
openwrt_network_auto_nat_enabled() { [ "$TEST_NAT" = 1 ]; }
"""


def render_rules(port="19993", second="24567", third="35678", nat="1"):
    result = subprocess.run(
        ["sh"],
        input=MOCKS + ADD_EVENT,
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "TEST_PORT": port, "TEST_SECOND_PORT": second,
             "TEST_THIRD_PORT": third, "TEST_NAT": nat},
    )
    return result.stdout


class HotplugRulesTest(unittest.TestCase):
    def assert_inbound_rules(self, output, expected):
        rules = dict(re.findall(
            r"rename firewall\.@rule\[-1\]=(\w+)\n(.*?)commit firewall", output, re.S
        ))
        self.assertEqual(set(rules), set(expected))
        for name, port in expected.items():
            self.assertIn("add_list firewall.@rule[-1].proto='udp'", rules[name])
            self.assertIn(f"set firewall.@rule[-1].dest_port='{port}'", rules[name])
            self.assertIn("set firewall.@rule[-1].src='*'", rules[name])

    def test_three_dynamic_udp_ports(self):
        for ports in (("19993", "24567", "35678"), ("29993", "45678", "56789")):
            with self.subTest(ports=ports):
                self.assert_inbound_rules(render_rules(*ports), dict(zip(
                    ("zt_rule_allowInbound", "zt_rule_allowSecondPort", "zt_rule_allowThirdPort"), ports
                )))

    def test_absent_optional_ports_and_default_primary_port(self):
        self.assert_inbound_rules(render_rules("", "", ""), {"zt_rule_allowInbound": "9993"})

    def test_subnet_forwarding_and_nat_remain_unrestricted(self):
        output = render_rules()
        self.assertIn("set firewall.@zone[-1].forward=ACCEPT", output)
        self.assertIn("set firewall.@zone[-1].input=ACCEPT", output)
        self.assertIn("set firewall.@zone[-1].masq=1", output)
        forwardings = dict(re.findall(
            r"rename firewall\.@forwarding\[-1\]=(\w+)\n(.*?)(?=add firewall forwarding|commit firewall)",
            output, re.S,
        ))
        expected = {
            "zt_fwd_zt_test2lan": ("zerotier", "lan"),
            "zt_fwd_zt_test2wan": ("zerotier", "wan"),
            "zt_fwd_lan2zt_test": ("lan", "zerotier"),
        }
        self.assertEqual(set(forwardings), set(expected))
        for name, (source, destination) in expected.items():
            self.assertIn(f"set firewall.@forwarding[-1].src={source}", forwardings[name])
            self.assertIn(f"set firewall.@forwarding[-1].dest={destination}", forwardings[name])
            self.assertNotIn(".proto=", forwardings[name])
            self.assertNotIn(".dest_port=", forwardings[name])

    def test_nat_disabled_does_not_add_inbound_rules(self):
        self.assert_inbound_rules(render_rules(nat="0"), {})


if __name__ == "__main__":
    unittest.main()
