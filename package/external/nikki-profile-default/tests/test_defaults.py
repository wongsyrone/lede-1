import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[2]
UCI = shutil.which(os.environ.get("UCI", "uci"))


class DefaultsTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(UCI, "Set UCI to a native libuci CLI; tests do not mock UCI")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = self.path / "config"
        self.config.mkdir()
        self.save = self.path / "save"
        self.save.mkdir()
        self.override = self.path / "override"
        self.override.mkdir()
        shutil.copyfile(ROOT / "feeds/nikki/nikki/files/nikki.conf", self.config / "nikki")
        (self.config / "trojan").write_text("config trojan\n option enabled '1'\n")
        self.trojan = (self.config / "trojan").read_bytes()

    def uci(self, *args):
        return subprocess.run(
            [UCI, "-c", str(self.config), "-t", str(self.save), "-C", str(self.override), *args],
            check=True, text=True, capture_output=True,
        ).stdout.strip()

    def apply(self):
        script = (PACKAGE / "files/99_nikki-profile-default").read_text()
        command = " ".join(map(shlex.quote, [
            UCI, "-c", str(self.config), "-t", str(self.save), "-C", str(self.override),
        ]))
        subprocess.run(
            ["sh"], input=f"uci() {{ command {command} \"$@\"; }}\n"
            + script,
            text=True, capture_output=True, check=True,
        )
        self.assertEqual((self.config / "trojan").read_bytes(), self.trojan)

    def test_placeholder_selects_default_without_enabling_proxy(self):
        self.apply()
        self.assertEqual(self.uci("get", "nikki.config.profile"), "file:default.yaml")
        self.assertEqual(self.uci("get", "nikki.config.enabled"), "0")
        self.assertEqual(self.uci("get", "nikki.mixin.api_listen"), "127.0.0.1:9090")
        self.assertEqual(self.uci("get", "nikki.config.test_profile"), "1")

    def test_empty_selection_uses_default(self):
        self.uci("delete", "nikki.config.profile")
        self.uci("commit", "nikki")
        self.apply()
        self.assertEqual(self.uci("get", "nikki.config.profile"), "file:default.yaml")

    def test_existing_file_and_subscription_settings_are_not_overwritten(self):
        for profile in ("file:my-profile.yaml", "subscription:subscription", "future:custom"):
            with self.subTest(profile=profile):
                self.uci("set", "nikki.config.profile=" + profile)
                self.uci("set", "nikki.subscription.url=https://subscription.invalid/private")
                self.uci("set", "nikki.config.enabled=1")
                self.uci("set", "nikki.mixin.api_listen=127.0.0.1:9191")
                self.uci("commit", "nikki")
                self.apply()
                self.assertEqual(self.uci("get", "nikki.config.profile"), profile)
                self.assertEqual(self.uci("get", "nikki.config.enabled"), "1")
                self.assertEqual(self.uci("get", "nikki.mixin.api_listen"), "127.0.0.1:9191")

    def test_enabled_invalid_profile_is_not_silently_replaced(self):
        self.uci("set", "nikki.config.enabled=1")
        self.uci("commit", "nikki")
        self.apply()
        self.assertEqual(self.uci("get", "nikki.config.profile"), "subscription:subscription")
        self.assertEqual(self.uci("get", "nikki.config.enabled"), "1")

    def test_trojan_bypass_extends_scoped_rule_not_root_or_catchall(self):
        count = self.uci("show", "nikki").count("=router_access_control")
        self.apply()
        self.assertEqual(self.uci("show", "nikki").count("=router_access_control"), count)
        bypass = "nikki.@router_access_control[0]"
        self.assertIn("services/trojan", self.uci("get", bypass + ".cgroup").split())
        self.assertIn("services/zerotier", self.uci("get", bypass + ".cgroup").split())
        self.assertIn("dnsmasq", self.uci("get", bypass + ".user").split())
        self.assertNotIn("root", self.uci("get", bypass + ".user").split())
        self.assertEqual(self.uci("get", bypass + ".dns"), "0")
        self.assertEqual(self.uci("get", bypass + ".proxy"), "0")
        self.assertEqual(self.uci("get", "nikki.@router_access_control[1].proxy"), "1")

    def test_unknown_access_controls_are_left_intact(self):
        self.uci("set", "nikki.config.profile=file:custom.yaml")
        self.uci("delete", "nikki.@router_access_control[0].user")
        self.uci("commit", "nikki")
        before = (self.config / "nikki").read_bytes()
        self.apply()
        self.assertEqual((self.config / "nikki").read_bytes(), before)

    def test_idempotent(self):
        self.apply()
        before = (self.config / "nikki").read_bytes()
        self.apply()
        self.assertEqual((self.config / "nikki").read_bytes(), before)
        self.assertEqual(self.uci("get", "nikki.@router_access_control[0].cgroup").split().count("services/trojan"), 1)


if __name__ == "__main__":
    unittest.main()
