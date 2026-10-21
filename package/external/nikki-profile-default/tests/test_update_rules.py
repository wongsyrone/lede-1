# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error


PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_rules", PACKAGE / "update-rules.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class Upstream:
    revision = "a" * 40
    root, geo, geosite, geoip = [value * 40 for value in "1234"]

    def __init__(self):
        self.calls = []
        self.downloads = []
        self.broken = False
        self.truncated = False
        self.missing = False
        self.payloads = {"geo/geosite/private.mrs": b"site rules",
                         "geo/geoip/private.mrs": b"address rules"}

    def json(self, path):
        self.calls.append(path)
        if path == "/git/ref/heads/meta":
            return {"object": {"sha": self.revision}}
        if path.startswith("/git/commits/"):
            return {"sha": self.revision, "tree": {"sha": self.root},
                    "committer": {"date": "2026-10-20T01:11:29Z"}}
        sha = path.rsplit("/", 1)[1]
        if sha == self.root:
            tree = [{"path": "geo", "type": "tree", "sha": self.geo}]
        elif sha == self.geo:
            tree = [{"path": "geosite", "type": "tree", "sha": self.geosite},
                    {"path": "geoip", "type": "tree", "sha": self.geoip}]
        else:
            directory = "geosite" if sha == self.geosite else "geoip"
            data = self.payloads[f"geo/{directory}/private.mrs"]
            tree = [] if self.missing else [{"path": "private.mrs", "type": "blob",
                "mode": "100644", "sha": rules.git_blob(data), "size": len(data)}]
        return {"sha": sha, "tree": tree, "truncated": self.truncated}

    def rule(self, revision, path):
        assert revision == self.revision
        self.downloads.append(path)
        return b"x" * len(self.payloads[path]) if self.broken else self.payloads[path]


class RuleSnapshotTests(unittest.TestCase):
    def setUp(self):
        # TemporaryDirectory is intentionally kept as evidence until OS cleanup.
        self.work = Path(tempfile.mkdtemp(prefix="nikki-rule-test-"))
        self.manifest = self.work / "source.mk"
        self.manifest.write_text(
            "$(eval $(call RuleDownload,private,geo/geosite/private.mrs," + "0" * 64 + "))\n"
            "$(eval $(call RuleDownload,private-ip,geo/geoip/private.mrs," + "0" * 64 + "))\n"
        )
        self.output = self.work / "rules.mk"
        self.download_dir = self.work / "dl"
        self.client = Upstream()

    def snapshot(self):
        return rules.snapshot(self.client, self.manifest, self.output, self.download_dir)

    def test_current_snapshot_is_consistent_and_reusable(self):
        original = self.manifest.read_bytes()
        revision, count = self.snapshot()
        self.assertEqual((revision, count), (self.client.revision, 2))
        text = self.output.read_text()
        self.assertIn("RULES_VERSION:=2026.10.20~" + revision[:12], text)
        self.assertIn("define Rules/Downloads", text)
        self.assertIn(rules.hashlib.sha256(b"site rules").hexdigest(), text)
        self.assertEqual(self.client.calls.count("/git/ref/heads/meta"), 1)
        self.assertFalse(any("?recursive" in path for path in self.client.calls))
        before = self.output.stat().st_mtime_ns
        self.snapshot()
        self.assertEqual(self.output.stat().st_mtime_ns, before)
        self.assertEqual(len(self.client.downloads), 2)
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_corrupt_cache_is_replaced_after_verification(self):
        self.snapshot()
        path = self.download_dir / f"nikki-rule-{self.client.revision}-private.mrs"
        path.write_bytes(b"x" * len(b"site rules"))
        self.snapshot()
        self.assertEqual(path.read_bytes(), b"site rules")
        self.assertEqual(len(self.client.downloads), 3)

    def test_bad_content_does_not_publish_a_partial_manifest(self):
        self.output.write_text("previous valid lock")
        self.client.broken = True
        with self.assertRaisesRegex(ValueError, "Git object"):
            self.snapshot()
        self.assertEqual(self.output.read_text(), "previous valid lock")

    def test_new_upstream_commit_changes_package_and_cache_identity(self):
        self.snapshot()
        before = self.output.read_text()
        self.client.revision = "b" * 40
        self.snapshot()
        self.assertNotEqual(self.output.read_text(), before)
        self.assertIn("RULES_VERSION:=2026.10.20~" + "b" * 12, self.output.read_text())
        self.assertEqual(len(list(self.download_dir.glob("*.mrs"))), 4)

    def test_truncated_tree_fails_explicitly(self):
        self.client.truncated = True
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.snapshot()
        self.assertFalse(self.output.exists())

    def test_missing_required_file_fails_before_downloads(self):
        self.client.missing = True
        with self.assertRaisesRegex(ValueError, "Missing upstream"):
            self.snapshot()
        self.assertFalse(self.client.downloads)
        self.assertFalse(self.output.exists())

    def test_malformed_manifest_is_not_silently_shortened(self):
        self.manifest.write_text(self.manifest.read_text() +
            "$(eval $(call RuleDownload,bad,geo/geosite/name?.mrs," + "0" * 64 + "))\n")
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_paths_cannot_escape_the_rule_directories(self):
        self.manifest.write_text("$(eval $(call RuleDownload,bad,../geosite/file.mrs," + "0" * 64 + "))\n")
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_network_retries_are_bounded(self):
        failure = urllib.error.HTTPError("https://example.invalid", 503, "unavailable", {}, None)
        with mock.patch.object(rules.urllib.request, "urlopen", side_effect=failure) as request, (
            mock.patch.object(rules.time, "sleep")
        ):
            with self.assertRaisesRegex(ValueError, "HTTP 503"):
                rules.Github().request("https://example.invalid")
        self.assertEqual(request.call_count, 3)

    def test_explicit_revision_avoids_a_moving_ref(self):
        rules.snapshot(self.client, self.manifest, self.output, self.download_dir, self.client.revision)
        self.assertNotIn("/git/ref/heads/meta", self.client.calls)


if __name__ == "__main__":
    unittest.main()
