#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).with_name("release_assets.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.temporary = tempfile.TemporaryDirectory()
        os.chdir(self.temporary.name)
        self.directory = Path("assets")
        self.directory.mkdir()

    def tearDown(self):
        os.chdir(self.previous)
        self.temporary.cleanup()

    def package(self):
        (self.directory / "openwrt-2026-10-15-device.bin").write_bytes(b"firmware")
        (self.directory / "profiles.json").write_text("{}")
        release.package("first", self.directory)

    def remote_assets(self):
        return [
            {"id": i, "name": path.name, "size": path.stat().st_size,
             "state": "uploaded", "digest": "sha256:" + release.digest(path)}
            for i, path in enumerate(sorted(self.directory.iterdir()), 1)
        ]

    def test_failed_target_does_not_select_another_targets_successful_artifact(self):
        entries = [{"id": 7, "name": "firmware-first", "expired": False},
                   {"id": 8, "name": "firmware-second", "expired": True}]
        with patch.object(release, "artifacts", return_value=entries), \
                patch.object(release, "output") as output:
            release.select("first")
            output.assert_called_with("artifact_id", 7)
            release.select("second")
            output.assert_called_with("artifact_id", "")

    def test_package_names_and_checksums_are_target_scoped(self):
        self.package()
        checksum = self.directory / "sha256sums-first.txt"
        self.assertEqual({"first--openwrt-2026-10-15-device.bin", "first--profiles.json"},
                         release.checksum_names(checksum.read_text()))
        self.assertEqual(3, len(list(self.directory.iterdir())))
        for path in self.directory.iterdir():
            self.assertFalse(path.is_symlink())
        self.assertNotIn("sha256sums-first.txt", checksum.read_text())

    def test_empty_and_non_firmware_directories_are_rejected(self):
        for files in (False, True):
            with self.subTest(files=files):
                if files:
                    (self.directory / "profiles.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "firmware"):
                    release.package("first", self.directory)

    def test_checksum_index_rejects_unsafe_or_malformed_names(self):
        for name in ("../other.bin", "/absolute.bin", "a\\b.bin", "other/file.bin"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.checksum_names("a" * 64 + "  " + name + "\n")
        with self.assertRaises(ValueError):
            release.checksum_names("not-a-checksum  image.bin\n")

    def test_missing_release_is_allowed_but_api_outage_is_not(self):
        with patch.object(release, "api", side_effect=subprocess.CalledProcessError(
                1, ["gh"], output=b'{"status":"404"}')):
            self.assertIsNone(release.get_release("nightly"))
        with patch.object(release, "api", side_effect=subprocess.CalledProcessError(
                1, ["gh"], output=b'{"status":"503"}')):
            with self.assertRaises(subprocess.CalledProcessError):
                release.get_release("nightly")

    def test_previous_legacy_index_protects_files_shared_with_other_targets(self):
        assets = [
            {"id": 1, "name": "sha256sums-first.txt"},
            {"id": 2, "name": "sha256sums-first-extra.txt"},
            {"id": 3, "name": "sha256sums-all.txt"},
        ]
        indexes = {
            1: "a" * 64 + "  old-first.bin\n" + "b" * 64 + "  shared.json\n",
            2: "b" * 64 + "  shared.json\n" + "c" * 64 + "  other.bin\n",
        }
        with patch.object(release, "get_release", return_value={"id": 99}), \
                patch.object(release, "assets", return_value=assets), \
                patch.object(release, "read_index", side_effect=lambda entry: indexes[entry["id"]]):
            release.prepare("first", "nightly")
        saved = json.loads(release.PREVIOUS.read_text())
        self.assertEqual(["old-first.bin"], saved["legacy"])
        self.assertEqual(99, saved["release_id"])

    def test_broken_foreign_index_does_not_block_target_publication_or_guess_ownership(self):
        entries = [{"id": 1, "name": "sha256sums-first.txt"},
                   {"id": 2, "name": "sha256sums-second.txt"}]
        for foreign in ("invalid checksum\n", subprocess.CalledProcessError(1, ["gh"])):
            def read(entry):
                if entry["id"] == 1:
                    return "a" * 64 + "  old-first.bin\n"
                if isinstance(foreign, Exception):
                    raise foreign
                return foreign
            with self.subTest(foreign=foreign), \
                    patch.object(release, "get_release", return_value={"id": 99}), \
                    patch.object(release, "assets", return_value=entries), \
                    patch.object(release, "read_index", side_effect=read):
                release.prepare("first", "nightly")
                self.assertEqual([], json.loads(release.PREVIOUS.read_text())["legacy"])

    def test_verified_upload_retires_only_this_targets_old_assets(self):
        self.package()
        release.write_json(release.PREVIOUS, {
            "target": "first", "tag": "nightly", "release_id": 99, "legacy": ["legacy-first.bin"]})
        old = [
            {"id": 11, "name": "first--openwrt-2026-10-14-device.bin"},
            {"id": 12, "name": "first-extra--openwrt-2026-10-14-device.bin"},
            {"id": 13, "name": "legacy-first.bin"},
            {"id": 14, "name": "unrelated.bin"},
            {"id": 15, "name": "sha256sums-all.txt"},
        ]
        with patch.object(release, "get_release", return_value={"id": 99}), \
                patch.object(release, "assets", return_value=self.remote_assets() + old), \
                patch.object(release, "api") as api:
            release.retire("first", "nightly", self.directory)
        self.assertEqual([("releases/assets/11", "DELETE"), ("releases/assets/13", "DELETE"),
                          ("releases/assets/15", "DELETE")],
                         [call.args for call in api.call_args_list])

    def test_failed_incomplete_or_changed_upload_keeps_previous_assets(self):
        self.package()
        release.write_json(release.PREVIOUS, {
            "target": "first", "tag": "nightly", "release_id": 99, "legacy": ["old.bin"]})
        complete = self.remote_assets()
        for entries in (complete[:-1], [{**entry, "digest": "sha256:" + "f" * 64}
                                        for entry in complete]):
            with self.subTest(entries=entries), \
                    patch.object(release, "get_release", return_value={"id": 99}), \
                    patch.object(release, "assets", return_value=entries), \
                    patch.object(release, "api") as api:
                with self.assertRaisesRegex(ValueError, "not confirmed"):
                    release.retire("first", "nightly", self.directory)
                api.assert_not_called()

    def test_replaced_release_or_wrong_target_receipt_never_deletes(self):
        self.package()
        for changed in ({"target": "second"}, {"release_id": 100}):
            release.write_json(release.PREVIOUS, {
                "target": "first", "tag": "nightly", "release_id": 99,
                "legacy": ["old.bin"], **changed})
            with patch.object(release, "get_release", return_value={"id": 99}), \
                    patch.object(release, "api") as api:
                with self.assertRaisesRegex(ValueError, "identity"):
                    release.retire("first", "nightly", self.directory)
                api.assert_not_called()

    def test_empty_replacement_cannot_remove_previous_firmware(self):
        (self.directory / "sha256sums-first.txt").touch()
        release.write_json(release.PREVIOUS, {
            "target": "first", "tag": "nightly", "release_id": 99, "legacy": ["old.bin"]})
        with patch.object(release, "get_release", return_value={"id": 99}), \
                patch.object(release, "assets", return_value=[]), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "invalid target payload"):
                release.retire("first", "nightly", self.directory)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
