"""Exercise provider and DNS behavior in the actual installed Mihomo version."""
import json
import ipaddress
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DNS:
    def __init__(self, answer):
        self.answer = answer
        self.count = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.stopping = False
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stopping:
            try:
                packet, source = self.socket.recvfrom(4096)
            except socket.timeout:
                continue
            self.count += 1
            end = 12
            while packet[end]:
                end += packet[end] + 1
            end += 5
            response = packet[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
            response += packet[12:end] + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x00\x00\x04"
            self.socket.sendto(response + socket.inet_aton(self.answer), source)

    def close(self):
        self.stopping = True
        self.thread.join(2)
        self.socket.close()


class MihomoTest(unittest.TestCase):
    def setUp(self):
        self.core = shutil.which(os.environ.get("MIHOMO", "mihomo"))
        self.assertIsNotNone(self.core)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.direct = DNS("203.0.113.7")
        self.other = DNS("198.51.100.9")
        self.addCleanup(self.direct.close)
        self.addCleanup(self.other.close)
        self.api_port, self.dns_port = unused_port(), unused_port()
        self.fake_range = "198.20.16.1/20"
        self.provider = self.root / "external.yaml"
        self.domains = self.root / "domains.yaml"
        self.provider.write_text('{"proxies":[{"name":"__guard_down__trojan","type":"reject"}]}')
        self.domains.write_text('payload:\n  - a.example.test\n')
        (self.root / "classified.yaml").write_text('payload:\n  - +.example.test\n  - +.lan\n')
        public = json.loads(subprocess.check_output([
            os.environ.get("YQ", "yq"), "-o", "json",
            str(Path(__file__).resolve().parents[2] / "nikki-profile-default/files/default.yaml"),
        ]))
        policy = {}
        for key in public["dns"]["nameserver-policy"]:
            if key == "rule-set:external-proxy-domains":
                policy[key] = [f"127.0.0.1:{self.direct.port}"]
            elif key.startswith("+.lan,"):
                policy["+.lan"] = [f"127.0.0.1:{self.direct.port}"]
            elif key.startswith("rule-set:geosite-private,"):
                policy["rule-set:classified"] = [f"127.0.0.1:{self.other.port}"]
        profile = {
            "external-controller": f"127.0.0.1:{self.api_port}",
            "secret": "lab-secret", "log-level": "error",
            "dns": {
                "enable": True, "listen": f"127.0.0.1:{self.dns_port}",
                "enhanced-mode": "fake-ip", "fake-ip-range": self.fake_range,
                "fake-ip-filter": ["rule-set:external-proxy-domains", "+.lan"],
                # Local UDP fixtures test policy ordering, not encrypted transport.
                "nameserver": [f"127.0.0.1:{self.other.port}"],
                "default-nameserver": ["https://223.5.5.5/dns-query"],
                "nameserver-policy": policy,
            },
            "proxy-providers": {"external": {"type": "file", "path": str(self.provider)}},
            "rule-providers": {
                "external-proxy-domains": {"type": "file", "behavior": "domain", "format": "yaml", "path": str(self.domains)},
                "classified": {"type": "file", "behavior": "domain", "format": "yaml", "path": str(self.root / "classified.yaml")},
            },
            "proxy-groups": [
                {"name": "native", "type": "fallback", "use": ["external"], "url": "http://127.0.0.1:9"},
                {"name": "ordinary", "type": "fallback", "proxies": ["REJECT"], "use": ["external"],
                 "exclude-filter": "^__guard_down__", "url": "http://127.0.0.1:9"},
            ],
            "rules": ["MATCH,native"],
        }
        (self.root / "config.yaml").write_text(json.dumps(profile))
        self.log = (self.root / "core.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen([self.core, "-d", str(self.root)], stdout=self.log, stderr=self.log)
        self.addCleanup(self.stop)
        for _ in range(60):
            try:
                providers = self.api("GET", "/providers/rules")["providers"]
                if (providers["external-proxy-domains"]["ruleCount"] == 1
                        and providers["classified"]["ruleCount"] == 2):
                    break
            except Exception:
                pass
            time.sleep(0.05)
        else:
            self.log.seek(0)
            self.fail(self.log.read())

    def stop(self):
        self.process.terminate()
        self.process.wait(5)

    def api(self, method, path):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.api_port}{path}", method=method,
            headers={"Authorization": "Bearer lab-secret"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read()
        return json.loads(body) if body else {}

    def query(self, name):
        question = b"".join(bytes([len(label)]) + label.encode() for label in name.split(".")) + b"\0"
        packet = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + question + b"\x00\x01\x00\x01"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.sendto(packet, ("127.0.0.1", self.dns_port))
            response = client.recv(4096)
        self.assertEqual(response[:2], packet[:2])
        self.assertGreater(struct.unpack("!H", response[6:8])[0], 0)
        return socket.inet_ntoa(response[-4:])

    def test_provider_withdrawal_last_node_and_ordinary_empty_group(self):
        pid = self.process.pid
        self.assertEqual(self.api("GET", "/proxies/native")["all"], ["__guard_down__trojan"])
        self.assertEqual(self.api("GET", "/proxies/ordinary")["all"], ["REJECT"])
        self.provider.write_text('{"proxies":[{"name":"native-test","type":"socks5","server":"127.0.0.1","port":11081}]}')
        self.api("PUT", "/providers/proxies/external")
        self.assertEqual([p["name"] for p in self.api("GET", "/providers/proxies/external")["proxies"]], ["native-test"])
        self.provider.write_text('{"proxies":[{"name":"__guard_down__trojan","type":"reject"}]}')
        self.api("PUT", "/providers/proxies/external")
        self.assertEqual(self.api("GET", "/proxies/native")["all"], ["__guard_down__trojan"])
        self.assertEqual(self.api("GET", "/proxies/ordinary")["all"], ["REJECT"])
        self.assertEqual(self.process.pid, pid)
        self.assertIsNone(self.process.poll())

    def test_domain_change_reuses_live_dns_listener_and_overrides_classification(self):
        self.assertEqual(self.query("a.example.test"), "203.0.113.7")
        self.assertIn(ipaddress.ip_address(self.query("b.example.test")),
                      ipaddress.ip_network(self.fake_range, strict=False))
        self.domains.write_text('payload:\n  - b.example.test\n')
        self.api("PUT", "/providers/rules/external-proxy-domains")
        self.assertEqual(self.query("b.example.test"), "203.0.113.7")
        self.assertIn(ipaddress.ip_address(self.query("a.example.test")),
                      ipaddress.ip_network(self.fake_range, strict=False))
        self.assertGreater(self.direct.count, 0)
        self.assertEqual(self.other.count, 0)

    def test_empty_native_domain_provider_is_valid_at_runtime(self):
        self.domains.write_text("payload: []\n")
        self.api("PUT", "/providers/rules/external-proxy-domains")
        providers = self.api("GET", "/providers/rules")["providers"]
        self.assertEqual(providers["external-proxy-domains"]["ruleCount"], 0)
        self.assertIn(ipaddress.ip_address(self.query("a.example.test")),
                      ipaddress.ip_network(self.fake_range, strict=False))

    def test_local_authority_precedes_broad_private_classification(self):
        self.assertEqual(self.query("unknown.guard.lan"), "203.0.113.7")
        self.assertEqual(self.other.count, 0)


if __name__ == "__main__":
    unittest.main()
