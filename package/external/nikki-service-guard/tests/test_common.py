import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path


COMMON = Path(__file__).resolve().parents[1] / "files/common.uc"
UCODE = shutil.which(os.environ.get("UCODE", "ucode"))


class CommonTest(unittest.TestCase):
    def run_ucode(self, body):
        self.assertIsNotNone(UCODE)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "test.uc"
            script.write_text(
                "import { domain, real_address, nodes, ready, request, atomic, withdrawn } from "
                + json.dumps(str(COMMON)) + ";\n" + body
            )
            result = subprocess.run([UCODE, "-S", str(script)], text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_native_domains_and_provider_boundaries(self):
        self.run_ucode(r"""
            assert(domain('Node.Example.COM.') == 'node.example.com');
            assert(domain('203.0.113.1') == null);
            assert(domain('2001:db8::1') == null);
            for (let value in ['node', '../secret', 'node;reboot', 'bad..example', '-bad.example']) {
                let rejected = false;
                try { domain(value); } catch (e) { rejected = true; }
                assert(rejected);
            }
            let local = ['127.0.0.1', '10.0.0.1'];
            let valid = {name: 'native', type: 'socks5', server: '10.0.0.1', port: 1081};
            assert(length(nodes({proxies: [valid]}, local)) == 1);
            for (let patch in [{server: 'proxy.example'}, {server: '203.0.113.1'},
                {name: '__guard_down__fake'}, {type: 'trojan'}, {port: 0}, {port: '1081'}, {tls: true}]) {
                let rejected = false;
                try { nodes({proxies: [{...valid, ...patch}]}, local); } catch (e) { rejected = true; }
                assert(rejected);
            }
            assert(withdrawn('trojan').proxies[0].type == 'reject');
        """)

    def test_atomic_state_is_unchanged_when_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = json.dumps(str(Path(directory) / "state.json"))
            self.run_ucode(f"""
                assert(atomic({path}, {{ state: 'ready' }}));
                assert(!atomic({path}, {{ state: 'ready' }}));
                assert(atomic({path}, {{ state: 'isolated' }}));
            """)

    def test_fake_ip_cidrs_follow_effective_ipv4_ipv6_configuration(self):
        self.run_ucode(r"""
            let dns = {'fake-ip-range': '198.20.4.1/23', 'fake-ip-range6': 'fd12:3456::1/48'};
            assert(!real_address('198.20.4.9', dns));
            assert(!real_address('198.20.5.255', dns));
            assert(real_address('198.20.6.0', dns));
            assert(real_address('198.18.0.1', dns));
            assert(!real_address('fd12:3456:0:1234::7', dns));
            assert(real_address('fd12:3456:1::7', dns));
            assert(real_address('2001:db8::7', dns));
            dns['fake-ip-range'] = '192.0.2.0/24';
            assert(real_address('198.20.4.9', dns));
            assert(!real_address('192.0.2.255', dns));
            for (let cidr in ['broken', '198.20.0.0/33', 'fd00::/129', '192.0.2.0/-1']) {
                let failed = false;
                try { real_address('192.0.2.1', {'fake-ip-range': cidr}); } catch (e) { failed = true; }
                assert(failed);
            }
            let failed = false;
            try {
                real_address('127.0.0.1', {'fake-ip-range': '0.0.0.0/0', 'fake-ip-range6': 'fd00::/129'});
            } catch (e) { failed = true; }
            assert(failed);
        """)

    def local_server(self, callback):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen()
        server.settimeout(8)
        errors = []

        def serve():
            try:
                conn, _ = server.accept()
                conn.settimeout(5)
                with conn:
                    callback(conn)
            except Exception as exc:
                errors.append(exc)
            finally:
                server.close()

        thread = threading.Thread(target=serve)
        thread.start()
        self.addCleanup(thread.join, 10)
        return server.getsockname()[1], thread, errors

    def test_socks_protocol_readiness_and_rejection(self):
        for response, expected in ((b"\x05\x00", True), (b"\x05\xff", False), (b"HTTP", False)):
            with self.subTest(response=response):
                def callback(conn):
                    self.assertEqual(conn.recv(3), b"\x05\x01\x00")
                    conn.sendall(response)
                port, thread, errors = self.local_server(callback)
                self.run_ucode(f"assert(ready({{type:'socks5', server:'127.0.0.1', port:{port}}}) == {str(expected).lower()});")
                thread.join(6)
                self.assertFalse(errors, errors)

    def test_api_uses_memory_only_auth_and_validates_status(self):
        for status in (200, 401):
            with self.subTest(status=status):
                def callback(conn):
                    data = b""
                    while b"\r\n\r\n" not in data:
                        data += conn.recv(4096)
                    self.assertIn(b"Authorization: Bearer lab-secret\r\n", data)
                    body = b'{"proxies":[]}'
                    conn.sendall(f"HTTP/1.0 {status} test\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                port, thread, errors = self.local_server(callback)
                body = f"""
                    let failed = false;
                    try {{ request({{'external-controller':'127.0.0.1:{port}', secret:'lab-secret'}},
                        'GET', '/providers/proxies/external-trojan'); }} catch(e) {{ failed = true; }}
                    assert(failed == {str(status == 401).lower()});
                """
                self.run_ucode(body)
                thread.join(6)
                self.assertFalse(errors, errors)

    def test_api_allows_dns_bootstrap_reply_after_one_second(self):
        def callback(conn):
            conn.recv(4096)
            time.sleep(1.2)
            conn.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{}')
        port, thread, errors = self.local_server(callback)
        self.run_ucode(f"request({{'external-controller':'127.0.0.1:{port}'}}, 'GET', '/dns/query');")
        thread.join(6)
        self.assertFalse(errors, errors)


if __name__ == "__main__":
    unittest.main()
