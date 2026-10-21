#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "cache", Path(__file__).with_name("build_state_cache.py"))
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)
ROOTS = ["build_dir/host", "build_dir/toolchain-test",
         "staging_dir/host", "staging_dir/toolchain-test"]
NATIVE_INPUTS = {"make": {}, "roots": ROOTS, "common_sources": {},
                 "tools_make_flags": cache.TOOLS_MAKE_FLAGS}
SCOPE_METADATA = {"native_target": {"board": "x86", "subtarget": "64"}}
SCOPE_METADATA["scope"] = cache.json_hash(SCOPE_METADATA["native_target"])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.temporary = tempfile.TemporaryDirectory()
        os.chdir(self.temporary.name)

    def tearDown(self):
        os.chdir(self.previous)
        self.temporary.cleanup()

    def fixture(self):
        for root in ROOTS:
            Path(root).mkdir(parents=True)
        source = Path("tools/test/Makefile")
        source.parent.mkdir(parents=True)
        source.write_text("original\n")
        self.source = source
        stamp = Path(ROOTS[0], "test/.built")
        stamp.parent.mkdir()
        stamp.write_text("")
        os.utime(source, ns=(1_700_000_000_123_456_789,) * 2)
        os.utime(stamp, ns=(1_700_000_010_987_654_321,) * 2)
        self.stamp = stamp
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "add", "tools/test/Makefile"], check=True)
        cache.WORK.mkdir()

    def test_profile_is_provenance_not_compatibility(self):
        self.fixture()
        Path("cfg").mkdir()
        for name in ("first", "second"):
            Path("cfg", name).touch()

        def query(*args, **kwargs):
            if args[0] == "make":
                if args[-1] in ("val.BOARD", "val.SUBTARGET"):
                    return {"val.BOARD": "x86", "val.SUBTARGET": "64"}[args[-1]]
                return str(Path(ROOTS[("BUILD_DIR_HOST", "BUILD_DIR_TOOLCHAIN",
                                      "STAGING_DIR_HOST", "TOOLCHAIN_DIR").index(args[-1][4:])]).resolve())
            return "same installed packages"

        sources = cache.source_records()
        with patch.object(cache, "command", side_effect=query), \
                patch.object(cache, "source_records", return_value=sources), \
                patch.object(cache, "pinned_feeds"), \
                patch.object(cache, "make_inputs", return_value={"tools/test": "same recipe"}):
            with patch.dict(os.environ, {"ImageVersion": "first", "LANG": "C"}):
                cache.plan("first")
            first = json.loads(cache.PLAN.read_text())
            with patch.dict(os.environ, {"ImageVersion": "second", "LANG": "en_US.UTF-8"}):
                cache.plan("second")
            second = json.loads(cache.PLAN.read_text())
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(SCOPE_METADATA["scope"], first["scope"])
        self.assertEqual(first["scope"], second["scope"])
        self.assertNotIn("scope", first["inputs"])
        self.assertNotIn("target", first["inputs"])
        self.assertFalse({"machine", "kernel", "os_release", "image", "packages",
                          "environment"} & first["inputs"].keys())

    def test_native_target_scope_survives_recipe_and_compiler_directory_changes(self):
        self.fixture()
        Path("cfg").mkdir()
        Path("cfg/test").touch()
        roots = ROOTS.copy()

        def query(*args, **kwargs):
            variable = args[-1][4:]
            if variable in ("BOARD", "SUBTARGET"):
                return {"BOARD": "x86", "SUBTARGET": "64"}[variable]
            return str(Path(roots[("BUILD_DIR_HOST", "BUILD_DIR_TOOLCHAIN",
                                   "STAGING_DIR_HOST", "TOOLCHAIN_DIR").index(variable)]).resolve())

        sources = cache.source_records()
        with patch.object(cache, "command", side_effect=query), \
                patch.object(cache, "pinned_feeds"), \
                patch.object(cache, "source_records", return_value=sources), \
                patch.object(cache, "make_inputs", side_effect=[{"toolchain/gcc": "old"},
                                                               {"toolchain/gcc": "new"}]):
            first = cache.plan("test")
            roots[1], roots[3] = "build_dir/toolchain-new", "staging_dir/toolchain-new"
            second = cache.plan("test")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotEqual(cache.scheduling_group(first["inputs"]),
                            cache.scheduling_group(second["inputs"]))
        self.assertEqual(first["scope"], second["scope"])

    def test_failed_upload_or_invisible_generation_preserves_previous(self):
        self.fixture()
        key = f"{cache.SCHEMA}-{'a' * 64}-456-1-{'b' * 64}"
        cache.write_json(cache.WORK / "receipt.json", {
            "key": key, "fingerprint": "a" * 64, "group": "b" * 64,
            "ref": "refs/heads/master", "members": ["test"]})
        previous = {"id": 1, "key": f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}",
                    "ref": "refs/heads/master", "size_in_bytes": 100}
        with patch.dict(os.environ, {"DEFAULT_BRANCH": "master", "GITHUB_REF": "refs/heads/master"}), \
                patch.object(cache, "caches", return_value=[previous]) as caches, \
                patch.object(cache, "api") as api, patch.object(cache.time, "sleep"):
            cache.confirm()
        api.assert_not_called()
        self.assertEqual(4, caches.call_count)

    def test_admission_keeps_old_generation_and_rejects_damaged_handoff(self):
        self.fixture()
        fingerprint = cache.json_hash(NATIVE_INPUTS)
        group = cache.scheduling_group(NATIVE_INPUTS)
        key = f"{cache.SCHEMA}-{fingerprint}-456-1-{group}"
        cache.CACHE.mkdir()
        payload = cache.CACHE / "state.tar.zst"
        payload.write_bytes(b"verified sealed payload")
        cache.write_json(cache.CACHE / "manifest.json", {
            "inputs": NATIVE_INPUTS, "fingerprint": fingerprint,
            "cache_key": key, "payload_sha256": cache.digest(payload)})
        receipt = {"key": key, "fingerprint": fingerprint, "group": group, "ref": "refs/heads/master"}
        cache.write_json(cache.RECEIPT, receipt)
        previous = {"id": 1, "key": f"{cache.SCHEMA}-{fingerprint}-123-1-{group}",
                    "ref": "refs/heads/master", "size_in_bytes": 100,
                    "last_accessed_at": "2026-10-14T00:00:00Z"}
        inventory = [previous] + [
            {"id": i + 2, "key": f"{cache.SCHEMA}-{i:064x}-123-1-{i:064x}",
             "ref": "refs/heads/master", "size_in_bytes": 10_000_000_000,
             "last_accessed_at": "2026-10-14T00:00:00Z"} for i in range(10)]
        with patch.dict(os.environ, {"DEFAULT_BRANCH": "master", "GITHUB_REF": "refs/heads/master"}), \
                patch.object(cache, "caches", return_value=inventory), \
                patch.object(cache, "artifacts", side_effect=AssertionError("No capacity planning")), \
                patch.object(cache, "api") as api, patch.object(cache, "output") as output:
            cache.admit()
            self.assertEqual("true", dict(call.args for call in output.call_args_list)["save"])
            api.assert_not_called()
            for changed in ({"group": "f" * 64}, {"ref": "refs/heads/other"}):
                cache.write_json(cache.RECEIPT, {**receipt, **changed})
                with self.assertRaisesRegex(ValueError, "damaged or mismatched"):
                    cache.admit()
            cache.write_json(cache.RECEIPT, receipt)
            inventory.append({**previous, "key": key})
            output.reset_mock()
            cache.admit()
            self.assertEqual("false", dict(call.args for call in output.call_args_list)["save"])
            payload.write_bytes(b"transport corruption")
            with self.assertRaisesRegex(ValueError, "damaged or mismatched"):
                cache.admit()
            api.assert_not_called()

    def test_corrupt_artifact_transport_does_not_retire_persistent_generation(self):
        self.fixture()
        fingerprint = cache.json_hash(NATIVE_INPUTS)
        group = cache.scheduling_group(NATIVE_INPUTS)
        current = {"fingerprint": fingerprint, "inputs": NATIVE_INPUTS, "sources": cache.source_records(),
                   "reused": False, "roots": ROOTS, "cache_key": f"{cache.SCHEMA}-{fingerprint}-123-1-{group}"}
        cache.write_json(cache.PLAN, current)
        cache.write_json(cache.CACHE / "manifest.json", {**current, "payload_sha256": "not the checksum"})
        (cache.CACHE / "state.tar.zst").write_bytes(b"corrupt transfer")
        with patch.dict(os.environ, {"STATE_ORIGIN": "artifact"}), patch.object(cache, "retire") as retire:
            cache.restore()
            retire.assert_not_called()
        self.assertFalse(json.loads(cache.PLAN.read_text())["reused"])

    def test_corrupt_manifest_is_retired_instead_of_misclassified_as_incompatible(self):
        self.fixture()
        inputs = {**NATIVE_INPUTS, "env": "new"}
        fingerprint = cache.json_hash(inputs)
        key = f"{cache.SCHEMA}-{fingerprint}-123-1-{cache.scheduling_group(inputs)}"
        current = {"fingerprint": fingerprint, "inputs": inputs,
                   "sources": cache.source_records(), "reused": False, "roots": ROOTS}
        cache.write_json(cache.PLAN, current)
        cache.write_json(cache.CACHE / "manifest.json", {
            **current, "cache_key": key, "inputs": {**inputs, "env": "corrupted"}})
        with patch.dict(os.environ, {"MATCHED_KEY": key, "DEFAULT_BRANCH": "master"}):
            cache.restore()
        self.assertEqual([{"key": key, "ref": "refs/heads/master"}],
                         json.loads(cache.REJECTIONS.read_text()))
        self.assertFalse(cache.CACHE.exists())

    def test_grouping_deduplicates_only_equal_native_inputs(self):
        base = {"make": {"tools/test": "same"}, "roots": ROOTS,
                "common_sources": {}, "tools_make_flags": cache.TOOLS_MAKE_FLAGS}
        other = {**base, "make": {"tools/test": "different"}}
        with patch.object(cache, "configure"), \
                patch.object(cache, "plan", side_effect=[{"inputs": other}, {"inputs": base}, {"inputs": base}]), \
                patch.object(cache, "output") as output:
            cache.group_targets(["x86_64", "first", "second"])
        values = dict(call.args for call in output.call_args_list)
        groups = json.loads(values["groups"])["include"]
        builds = json.loads(values["builds"])["include"]
        self.assertEqual([["x86_64"], ["first", "second"]], [group["members"] for group in groups])
        self.assertEqual(builds[1]["group"], builds[2]["group"])
        self.assertNotEqual(builds[0]["group"], builds[1]["group"])

    def test_producer_rechecks_actual_member_inputs(self):
        base = NATIVE_INPUTS
        other = {**base, "make": {"tools/test": "changed recipe"}}
        with patch.object(cache, "configure"), patch.object(
                cache, "plan", side_effect=[{"inputs": base}, {"inputs": other}]):
            with self.assertRaisesRegex(ValueError, "Producer inputs differ"):
                cache.check_group(cache.scheduling_group(base), ["first", "second"])

    def test_final_retirement_deduplicates_and_keeps_receipts_for_reruns(self):
        key = f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}"
        entries = [
            {"id": 1, "name": f"state-rejections-tools-{'b' * 64}-1", "expired": False},
            {"id": 2, "name": "state-rejections-build-test-1", "expired": False},
            {"id": 3, "name": f"state-payload-{'b' * 64}-1", "expired": False},
            {"id": 4, "name": f"state-receipt-{'b' * 64}-1", "expired": False},
        ]
        persisted = {"id": 5, "key": key, "ref": "refs/heads/master", "size_in_bytes": 100}
        with patch.dict(os.environ, {"DEFAULT_BRANCH": "master"}), \
                patch.object(cache, "artifacts", return_value=entries), \
                patch.object(cache, "artifact_json", return_value=[{"key": key, "ref": "refs/heads/master"}]), \
                patch.object(cache, "caches", return_value=[
                    persisted, {**persisted, "id": 6, "ref": "refs/heads/other"}]), \
                patch.object(cache, "api") as api:
            cache.finalize()
        self.assertEqual([("caches/5", "DELETE"), ("artifacts/1", "DELETE"),
                          ("artifacts/2", "DELETE"), ("artifacts/3", "DELETE")],
                         [call.args for call in api.call_args_list])

    def test_rerun_uses_real_producer_attempt_and_falls_back_to_recorded_key(self):
        self.fixture()
        group = "b" * 64
        key = f"{cache.SCHEMA}-{'a' * 64}-123-1-{group}"
        receipt = {"schema": cache.SCHEMA, "group": group, "producer_attempt": "10",
                   "run_id": "456", "ref": "refs/heads/master", "artifact_id": 3,
                   "key": key, "fingerprint": "a" * 64, "input_hashes": {}}
        entries = [
            {"id": 1, "name": f"state-receipt-{group}-2", "expired": False},
            {"id": 2, "name": f"state-receipt-{group}-10", "expired": False},
            {"id": 3, "name": f"state-payload-{group}-10", "expired": False},
            {"id": 4, "name": f"state-receipt-{'c' * 64}-10", "expired": False},
        ]
        cache.write_json(cache.PLAN, {"fingerprint": "a" * 64, "inputs": {}})
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "11",
                                    "GITHUB_REF": "refs/heads/master"}), \
                patch.object(cache, "artifacts", return_value=entries), \
                patch.object(cache, "artifact_json", return_value=receipt) as read, \
                patch.object(cache, "output") as output:
            cache.select(group)
            self.assertEqual(2, read.call_args.args[0]["id"])
            self.assertEqual(3, dict(call.args for call in output.call_args_list)["artifact_id"])
            entries[2]["expired"] = True
            output.reset_mock()
            cache.select(group)
            values = dict(call.args for call in output.call_args_list)
            self.assertEqual("", values["artifact_id"])
            self.assertEqual(key, values["key"])

    def test_missing_generation_delete_is_idempotent(self):
        error = urllib.error.HTTPError("https://api.github.com", 404, "missing", {}, None)
        with patch.object(cache, "api", side_effect=error):
            cache.delete_entry({"id": 1, "key": "test", "size_in_bytes": 0})

    def test_restored_tools_get_only_one_clean_retry(self):
        self.fixture()
        targets = "tools/download toolchain/download tools/compile toolchain/compile defconfig"
        Path("Makefile").write_text(f".PHONY: {targets}\n{targets}:\n\t@echo native-make-check\n")
        current = {"fingerprint": "a" * 64, "reused": True, "roots": ROOTS,
                   "restored_stamps": {}, "cache_key": f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}"}
        cache.write_json(cache.PLAN, current)
        with patch.object(cache, "smoke", side_effect=[ValueError("unusable"), None]) as smoke:
            cache.compile_tools()
        self.assertEqual(2, smoke.call_count)
        self.assertFalse(json.loads(cache.PLAN.read_text())["reused"])
        self.assertEqual(1, len(json.loads(cache.REJECTIONS.read_text())))
        with patch.object(cache, "smoke", side_effect=ValueError("cold failure")) as smoke:
            with self.assertRaisesRegex(ValueError, "cold failure"):
                cache.compile_tools()
        self.assertEqual(1, smoke.call_count)

    def test_make_owns_package_and_toolchain_input_selection(self):
        # Use real Make expansion, rather than mirroring a hand-picked .config filter.
        rule = "val.%:\n\t@echo '$(subst ','\"'\"',$($*))'\n"
        Path("Makefile").write_text(
            "tools-y=test\n"
            "toolchain/builddirs=test\n"
            + rule)
        for name in ("tools/test", "toolchain/test"):
            Path(name).mkdir(parents=True)
            Path(name, "Makefile").write_text(
                "include $(TOPDIR)/.config\n"
                "HOST_CONFIGURE_ARGS=--cpu=$(CONFIG_CPU_TYPE)\n"
                "define Host/Configure\n"
                "\t./configure $(HOST_CONFIGURE_ARGS)\nendef\n"
                + rule)
        Path(".config").write_text('CONFIG_CPU_TYPE=arm\nCONFIG_PACKAGE_demo=y\n')
        original = cache.make_inputs()
        Path(".config").write_text('CONFIG_CPU_TYPE=arm\nCONFIG_PACKAGE_other=y\nCONFIG_DEMO_OPT=y\n')
        self.assertEqual(original, cache.make_inputs())
        Path("feeds.conf").write_text("different feed revision\n")
        self.assertEqual(original, cache.make_inputs())
        Path(".config").write_text('CONFIG_CPU_TYPE=x86_64\nCONFIG_PACKAGE_other=y\n')
        self.assertNotEqual(original, cache.make_inputs())

    def test_native_version_check_does_not_change_firmware_config(self):
        self.fixture()
        firmware_config = "CONFIG_CPU_TYPE=arm\nCONFIG_PACKAGE_demo=y\n"
        Path(".config").write_text(firmware_config)
        Path("Makefile").write_text(
            "include .config\n.PHONY: tools/compile toolchain/compile\n"
            "tools/compile toolchain/compile:\n"
            '\t@test "$(CONFIG_BUILDBOT)" = y\n')
        cache.write_json(cache.PLAN, {
            "fingerprint": "a" * 64, "reused": False, "roots": ROOTS})
        with patch.object(cache, "smoke") as smoke:
            cache.compile_tools()
        smoke.assert_called_once_with(ROOTS)
        self.assertEqual(firmware_config, Path(".config").read_text())

    def test_redownloaded_identical_source_does_not_rebuild_native_stamps(self):
        self.fixture()
        downloaded = Path("dl/test.tar.gz")
        downloaded.parent.mkdir()
        downloaded.write_bytes(b"same source")
        os.utime(downloaded, ns=(1_700_000_001_123_456_789,) * 2)
        saved = {str(downloaded): {
            "mode": 0o644, "link": None, "sha256": cache.digest(downloaded),
            "mtime_ns": downloaded.stat().st_mtime_ns,
        }}
        prepared = self.stamp.with_name(".prepared")
        prepared.touch()
        os.utime(prepared, ns=(1_700_000_002_987_654_321,) * 2)
        Path("source.tar.gz").write_bytes(downloaded.read_bytes())
        native_download = self.previous / "include/download.mk"
        self.assertTrue(native_download.is_file())
        Path("Makefile").write_text(
            f"TOPDIR:={Path.cwd()}\nDL_DIR:=$(TOPDIR)/dl\n"
            f"HOST_STAMP_PREPARED:={prepared}\n"
            "PKG_SOURCE:=test.tar.gz\nPKG_SOURCE_URL:=file://unused\n"
            f"PKG_HASH:={cache.digest(downloaded)}\nlocked=$(1)\n"
            f"include {native_download}\n"
            "define DownloadMethod/default\n"
            "\tcp source.tar.gz $(DL_DIR)/$(FILE)\nendef\n"
            "$(eval $(call Download,default))\n"
            ".PHONY: tools/download toolchain/download tools/compile toolchain/compile\n"
            "tools/download toolchain/download: download\n"
            f"tools/compile toolchain/compile: {self.stamp}\n"
            f"{prepared}:\n\t@echo prepare >> rebuilt\n\t@touch $@\n"
            f"{self.stamp}: {prepared}\n\t@echo compile >> rebuilt\n\t@touch $@\n")
        before = cache.stamps(ROOTS)
        cache.write_json(cache.PLAN, {
            "fingerprint": "a" * 64, "reused": True, "roots": ROOTS,
            "restored_stamps": before, "restored_downloads": saved,
        })
        downloaded.unlink()
        with patch.object(cache, "smoke"), patch.object(cache, "retire") as retire, \
                patch.object(cache, "report", wraps=cache.report) as report:
            cache.compile_tools()
            self.assertEqual(before, cache.stamps(ROOTS))
            self.assertFalse(Path("rebuilt").exists())
            self.assertEqual(saved[str(downloaded)]["mtime_ns"], downloaded.stat().st_mtime_ns)
            downloaded.unlink()
            Path("source.tar.gz").write_bytes(b"changed source")
            cache.compile_tools()
            self.assertNotEqual(before, cache.stamps(ROOTS))
            self.assertEqual(["prepare", "compile"], Path("rebuilt").read_text().splitlines())
            self.assertTrue(any("Native completion stamp changes" in call.args[0] and
                                str(self.stamp) in call.args[0] for call in report.call_args_list))
            retire.assert_not_called()

    def test_snapshot_with_wrong_group_tag_is_rejected_before_unpack(self):
        self.fixture()
        fingerprint = cache.json_hash(NATIVE_INPUTS)
        current = {"roots": ROOTS, "inputs": NATIVE_INPUTS, "fingerprint": fingerprint,
                   "cache_key": f"{cache.SCHEMA}-{fingerprint}-123-1-{'f' * 64}"}
        cache.write_json(cache.PLAN, current)
        cache.write_json(cache.CACHE / "manifest.json", current)
        with patch.object(cache, "retire") as retire, patch.object(cache.subprocess, "Popen") as unpack:
            cache.restore()
            retire.assert_called_once()
            unpack.assert_not_called()

    def test_download_failure_preserves_valid_restored_generation(self):
        self.fixture()
        Path("Makefile").write_text(
            ".PHONY: tools/download toolchain/download tools/compile toolchain/compile\n"
            "tools/download toolchain/download:\n\t@exit 1\n"
            "tools/compile toolchain/compile:\n\t@exit 0\n")
        cache.write_json(cache.PLAN, {
            "fingerprint": "a" * 64, "reused": True, "roots": ROOTS,
            "restored_downloads": {},
        })
        with patch.object(cache, "smoke"), patch.object(cache, "retire") as retire:
            with self.assertRaisesRegex(ValueError, "tools/download failed"):
                cache.compile_tools()
            retire.assert_not_called()
        self.assertTrue(self.stamp.exists())
        self.assertTrue(json.loads(cache.PLAN.read_text())["reused"])

    def test_native_download_hash_check_survives_timestamp_restoration(self):
        self.fixture()
        Path("dl").mkdir()
        downloaded = Path("dl/test.tar.gz")
        downloaded.write_bytes(b"valid source archive")
        os.utime(downloaded, ns=(1_700_000_001_123_456_789,) * 2)
        saved = cache.download_records()
        expected = cache.digest(downloaded)
        hasher = Path("mkhash")
        hasher.write_text(
            "#!/usr/bin/env python3\nimport hashlib, pathlib, sys\n"
            "with open('hash-calls', 'a') as log: log.write('hash\\n')\n"
            "print(hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest())\n")
        hasher.chmod(0o755)
        Path("Makefile").write_text(
            f"DL_DIR:={Path.cwd()}/dl\nTMP_DIR:=tmp\nSTAGING_DIR_HOST:=staging_dir/host\n"
            f"MKHASH:={hasher.resolve()}\ninclude {self.previous}/include/download.mk\n"
            ".PHONY: verify\nverify:\n"
            f'\t@test "$(call gen_sha256sum_cached,test.tar.gz,{expected})" = "{expected}"\n')
        subprocess.run(["make", "-s", "verify"], check=True)
        os.utime(downloaded, ns=(1_800_000_000_555_555_555,) * 2)
        subprocess.run(["make", "-s", "verify"], check=True)
        self.assertEqual(1, cache.retain_source_times(saved, cache.download_records()))
        subprocess.run(["make", "-s", "verify"], check=True)
        self.assertEqual(3, len(Path("hash-calls").read_text().splitlines()))
        downloaded.write_bytes(b"corrupt")
        changed = downloaded.stat().st_mtime_ns
        self.assertEqual(0, cache.retain_source_times(saved, cache.download_records()))
        self.assertEqual(changed, downloaded.stat().st_mtime_ns)
        self.assertNotEqual(0, subprocess.run(["make", "-s", "verify"], stderr=subprocess.PIPE).returncode)

    def test_corrupt_download_metadata_is_retired_before_unpack(self):
        self.fixture()
        inputs = {**NATIVE_INPUTS, "fixture": "same"}
        fingerprint = cache.json_hash(inputs)
        current = {"roots": ROOTS, "inputs": inputs, "fingerprint": fingerprint,
                   "cache_key": f"{cache.SCHEMA}-{fingerprint}-123-1-{cache.scheduling_group(inputs)}"}
        record = {"mode": 0o644, "link": None, "sha256": "a" * 64, "mtime_ns": 1}
        cases = [
            [], {"dl/test.tar.gz": "invalid"},
            {"../escape": record}, {"dl/test.tar.gz": {**record, "sha256": "invalid"}},
            {"dl/test.tar.gz": {**record, "mtime_ns": "invalid"}},
        ]
        for downloads in cases:
            with self.subTest(downloads=downloads):
                cache.write_json(cache.PLAN, current)
                cache.write_json(cache.CACHE / "manifest.json", {**current, "downloads": downloads})
                with patch.object(cache, "retire") as retire, patch.object(cache.subprocess, "Popen") as unpack:
                    cache.restore()
                    retire.assert_called_once()
                    unpack.assert_not_called()
                self.assertFalse(json.loads(cache.PLAN.read_text())["reused"])

    def test_unchanged_mtime_restored_changed_and_deleted_sources_left_to_make(self):
        self.fixture()
        saved = cache.source_records()
        os.utime(self.source, ns=(1_800_000_000_555_555_555,) * 2)
        self.assertEqual(1, cache.retain_source_times(saved, cache.source_records()))
        self.assertEqual(saved[str(self.source)]["mtime_ns"], self.source.stat().st_mtime_ns)
        self.source.write_text("changed\n")
        modified = self.source.stat().st_mtime_ns
        self.assertEqual(0, cache.retain_source_times(saved, cache.source_records()))
        self.assertEqual(modified, self.source.stat().st_mtime_ns)
        self.source.unlink()
        self.assertEqual(0, cache.retain_source_times(saved, {}))

    def test_smoke_accepts_compiler_aliases_but_rejects_missing_or_distinct_compilers(self):
        self.fixture()
        for root, name in (
            (ROOTS[1], "test/.built"),
            (ROOTS[2], "stamp/.tools_compile_test"),
            (ROOTS[3], "stamp/.gcc_final_installed"),
        ):
            path = Path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        compiler = Path(ROOTS[3], "bin/x86_64-openwrt-linux-musl-gcc")
        compiler.parent.mkdir()
        compiler.touch()
        alias = compiler.with_name("x86_64-openwrt-linux-gcc")
        alias.symlink_to(compiler.name)
        checksum = cache.hashlib.sha256(b"cache-smoke").hexdigest()

        def compile_elf(arguments, **kwargs):
            if "-x" in arguments:
                Path(arguments[-1]).write_bytes(b"\x7fELF\x02\x01" + bytes(12) + b"\x3e\x00")

        with patch.object(cache, "command", side_effect=[checksum, "x86_64-openwrt-linux-musl"]), \
                patch.object(cache.subprocess, "run", side_effect=compile_elf) as run:
            cache.smoke(ROOTS)
            self.assertEqual(["c", "c++"], [call.args[0][2] for call in run.call_args_list[1:]])
        alias.unlink()
        alias.touch()
        for case in ("distinct", "missing"):
            with self.subTest(case=case), patch.object(cache, "command", return_value=checksum), \
                    patch.object(cache.subprocess, "run"):
                if case == "missing":
                    compiler.unlink()
                    alias.unlink()
                with self.assertRaisesRegex(ValueError, "Expected one OpenWrt cross compiler"):
                    cache.smoke(ROOTS)

    def test_archive_roundtrip_and_native_timestamp_check(self):
        self.fixture()
        sources = cache.source_records()
        expected = cache.stamps(ROOTS)
        inputs = {**NATIVE_INPUTS, "test": "same"}
        fingerprint = cache.json_hash(inputs)
        current = {"fingerprint": fingerprint, "inputs": inputs,
                   "sources": sources, "reused": False, "roots": ROOTS,
                   "cache_key": f"{cache.SCHEMA}-{fingerprint}-123-1-{cache.scheduling_group(inputs)}"}
        cache.write_json(cache.PLAN, current)
        cache.CACHE.mkdir()
        payload = cache.CACHE / "state.tar.zst"
        subprocess.run(["tar", "--format=posix", "-I", "zstd", "-cf",
                        str(payload), *ROOTS], check=True)
        cache.write_json(cache.CACHE / "manifest.json", {
            **current, "stamps": expected, "payload_sha256": cache.digest(payload)})
        cache.clean(ROOTS)
        os.utime(self.source, ns=(1_800_000_000_555_555_555,) * 2)
        with patch.object(cache, "smoke"):
            cache.restore()
        self.assertTrue(json.loads(cache.PLAN.read_text())["reused"])
        self.assertEqual(expected, cache.stamps(ROOTS))
        self.assertEqual(sources[str(self.source)]["mtime_ns"], self.source.stat().st_mtime_ns)
        timestamp = self.previous / "scripts/timestamp.pl"
        if timestamp.exists():
            self.assertEqual(0, subprocess.run(["perl", str(timestamp), "-n",
                                               str(self.stamp), str(self.source)]).returncode)
            self.source.write_text("changed\n")
            self.assertEqual(1, subprocess.run(["perl", str(timestamp), "-n",
                                               str(self.stamp), str(self.source)]).returncode)
        payload.write_bytes(b"corrupt")
        with patch.object(cache, "retire") as retire:
            cache.restore()
            retire.assert_called_once()
        self.assertFalse(Path(ROOTS[0]).exists())

    def test_archive_rejects_escape_and_writes_through_symlink(self):
        roots = [tarfile.TarInfo(name) for name in ROOTS]
        for member in roots:
            member.type = tarfile.DIRTYPE
        for name in ("/tmp/escape", "build_dir/host/../../escape"):
            with self.assertRaises(ValueError):
                cache.validate_members(roots + [tarfile.TarInfo(name)], ROOTS)
        link = tarfile.TarInfo("build_dir/host/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/usr/bin"
        with self.assertRaises(ValueError):
            cache.validate_members(roots + [link, tarfile.TarInfo(link.name + "/file")], ROOTS)

    def test_keys_require_current_schema_and_explicit_group(self):
        for key in (f"owrt-state-v3-foo-bar-{'a' * 64}-123-1",
                    f"{cache.SCHEMA}-{'a' * 64}-123-1",
                    f"{cache.SCHEMA}-{'a' * 64}-123-1-unrelated"):
            self.assertIsNone(cache.key_fingerprint(key))
            self.assertIsNone(cache.key_group(key))
        tagged = f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}"
        self.assertEqual("a" * 64, cache.key_fingerprint(tagged))
        self.assertEqual("b" * 64, cache.key_group(tagged))
        scoped = tagged + "-scope-" + SCOPE_METADATA["scope"]
        self.assertEqual("a" * 64, cache.key_fingerprint(scoped))
        self.assertEqual("b" * 64, cache.key_group(scoped))
        self.assertEqual(SCOPE_METADATA["scope"], cache.key_scope(scoped))
        self.assertIsNone(cache.key_scope(tagged))
        for suffix in ("-scope-short", "-scope-" + "z" * 64, "-unexpected"):
            self.assertIsNone(cache.key_group(tagged + suffix))

    def test_retention_metadata_corruption_rejects_before_unpack(self):
        self.fixture()
        fingerprint = cache.json_hash(NATIVE_INPUTS)
        group = cache.scheduling_group(NATIVE_INPUTS)
        key = f"{cache.SCHEMA}-{fingerprint}-123-1-{group}-scope-{SCOPE_METADATA['scope']}"
        current = {**SCOPE_METADATA, "inputs": NATIVE_INPUTS, "fingerprint": fingerprint,
                   "sources": cache.source_records(), "reused": False, "roots": ROOTS}
        cache.write_json(cache.PLAN, current)
        cache.write_json(cache.CACHE / "manifest.json", {
            **current, "cache_key": key, "native_target": {"board": "mvebu", "subtarget": "cortexa9"}})
        with patch.object(cache, "retire") as retire, patch.object(cache.subprocess, "Popen") as unpack:
            cache.restore()
        retire.assert_called_once()
        unpack.assert_not_called()

    def test_changed_native_recipe_rejects_before_unpack(self):
        self.fixture()
        inputs = {**NATIVE_INPUTS, "make": {"tools/test": "new recipe"}}
        current = {"fingerprint": cache.json_hash(inputs), "inputs": inputs,
                   "sources": cache.source_records(), "reused": False, "roots": ROOTS}
        cache.write_json(cache.PLAN, current)
        saved_inputs = {**inputs, "make": {"tools/test": "old recipe"}}
        saved_fingerprint = cache.json_hash(saved_inputs)
        cache.write_json(cache.CACHE / "manifest.json", {
            **current, "inputs": saved_inputs, "fingerprint": saved_fingerprint,
            "cache_key": f"{cache.SCHEMA}-{saved_fingerprint}-123-1-{cache.scheduling_group(saved_inputs)}"})
        with patch.object(cache, "retire") as retire, patch.object(cache.subprocess, "Popen") as unpack:
            cache.restore()
            retire.assert_not_called()
            unpack.assert_not_called()
        self.assertTrue(self.stamp.exists())

    def test_confirmed_generation_retires_only_its_group_across_fingerprints(self):
        self.fixture()
        group = "d" * 64
        current_key = f"{cache.SCHEMA}-{'a' * 64}-456-1-{group}"
        cache.write_json(cache.RECEIPT, {"key": current_key, "fingerprint": "a" * 64,
                                        "group": group, "members": ["test"], "ref": "refs/heads/master"})
        sibling = {"id": 2, "key": f"{cache.SCHEMA}-{'b' * 64}-123-1-{'e' * 64}",
                   "ref": "refs/heads/master", "size_in_bytes": 100}
        previous = {"id": 1, "key": f"{cache.SCHEMA}-{'a' * 64}-123-1-{group}",
                    "ref": "refs/heads/master", "size_in_bytes": 100}
        legacy = {"id": 3, "key": f"owrt-state-v3-test-{'c' * 64}-123-1",
                  "ref": "refs/heads/master", "size_in_bytes": 100}
        visible = {"id": 4, "key": current_key, "ref": "refs/heads/master", "size_in_bytes": 100}
        other_ref = {**previous, "id": 5, "ref": "refs/heads/other"}
        other_fingerprint = {**previous, "id": 6, "key": f"{cache.SCHEMA}-{'c' * 64}-123-1-{group}"}
        unknown_legacy = {**previous, "id": 7, "key": f"{cache.SCHEMA}-{'f' * 64}-123-1"}
        environment = {"GITHUB_REF": "refs/heads/master", "DEFAULT_BRANCH": "master",
                       "GITHUB_RUN_ID": "456"}
        with patch.dict(os.environ, environment), patch.object(cache, "api") as api:
            with patch.object(cache, "caches", return_value=[
                    previous, sibling, legacy, visible, other_ref, other_fingerprint,
                    unknown_legacy]):
                cache.confirm()
            self.assertEqual([("caches/1", "DELETE"), ("caches/6", "DELETE")],
                             [call.args for call in api.call_args_list])

    def test_confirmed_scope_retires_old_input_groups_but_keeps_active_variants(self):
        self.fixture()
        group, active = "d" * 64, "e" * 64
        scope = SCOPE_METADATA["scope"]
        key = f"{cache.SCHEMA}-{'a' * 64}-456-1-{group}-scope-{scope}"
        cache.write_json(cache.RECEIPT, {
            **SCOPE_METADATA, "key": key, "fingerprint": "a" * 64, "group": group,
            "members": ["x86_64"], "ref": "refs/heads/master"})
        base = {"ref": "refs/heads/master", "size_in_bytes": 100}
        old = {**base, "id": 1, "key": f"{cache.SCHEMA}-{'b' * 64}-123-1-{'c' * 64}-scope-{scope}"}
        sibling = {**base, "id": 2, "key": f"{cache.SCHEMA}-{'b' * 64}-123-1-{'f' * 64}-scope-{'f' * 64}"}
        same_group = {**base, "id": 3, "key": f"{cache.SCHEMA}-{'c' * 64}-123-1-{group}-scope-{scope}"}
        visible = {**base, "id": 4, "key": key}
        other_ref = {**old, "id": 5, "ref": "refs/heads/other"}
        variant = {**base, "id": 6, "key": f"{cache.SCHEMA}-{'f' * 64}-123-1-{active}-scope-{scope}"}
        unrelated = {**base, "id": 7, "key": "some-other-cache"}
        environment = {
            "GITHUB_REF": "refs/heads/master", "DEFAULT_BRANCH": "master",
            "STATE_GROUPS": json.dumps({"include": [{"group": group}, {"group": active}]})}
        with patch.dict(os.environ, environment), \
                patch.object(cache, "caches", return_value=[
                    old, sibling, same_group, visible, other_ref, variant, unrelated]), \
                patch.object(cache, "api") as api:
            cache.confirm()
        self.assertEqual([("caches/1", "DELETE"), ("caches/3", "DELETE")],
                         [call.args for call in api.call_args_list])

    def test_scoped_upload_must_be_uniquely_visible_before_any_retirement(self):
        self.fixture()
        group = "d" * 64
        key = f"{cache.SCHEMA}-{'a' * 64}-456-1-{group}-scope-{SCOPE_METADATA['scope']}"
        cache.write_json(cache.RECEIPT, {
            **SCOPE_METADATA, "key": key, "fingerprint": "a" * 64,
            "group": group, "members": ["x86_64"], "ref": "refs/heads/master"})
        previous = {"id": 1, "key": f"{cache.SCHEMA}-{'b' * 64}-123-1-{'c' * 64}",
                    "ref": "refs/heads/master", "size_in_bytes": 100}
        visible = {**previous, "id": 2, "key": key}
        for replacement in ([], [{**visible, "size_in_bytes": 0}],
                            [visible, {**visible, "id": 3}]):
            with self.subTest(replacement=replacement), \
                    patch.dict(os.environ, {"GITHUB_REF": "refs/heads/master",
                                            "DEFAULT_BRANCH": "master", "STATE_GROUPS": '{"include":[]}'}), \
                    patch.object(cache, "caches", return_value=[previous, *replacement]), \
                    patch.object(cache.time, "sleep"), patch.object(cache, "api") as api, \
                    patch.object(cache, "legacy_retirements") as legacy:
                cache.confirm()
            api.assert_not_called()
            legacy.assert_not_called()

    def test_unscoped_retirement_requires_exact_receipt_and_complete_profile_coverage(self):
        group = "b" * 64
        key = f"{cache.SCHEMA}-{'a' * 64}-123-1-{group}"
        entry = {"id": 1, "key": key, "ref": "refs/heads/master", "size_in_bytes": 100}
        artifact = {"id": 2, "name": f"state-receipt-{group}-1", "expired": False}
        previous = {"schema": cache.SCHEMA, "group": group, "producer_attempt": "1",
                    "run_id": "123", "ref": "refs/heads/master", "artifact_id": 3,
                    "key": key, "fingerprint": "a" * 64, "members": ["first", "second"],
                    "input_hashes": {}}
        for changed, expected in (({}, {1}), ({"members": ["third"]}, set()),
                                  ({"members": []}, set()), ({"run_id": "999"}, set()),
                                  ({"ref": "refs/heads/other"}, set()),
                                  ({"key": key.replace("-123-", "-122-")}, set())):
            with self.subTest(changed=changed), \
                    patch.dict(os.environ, {"GITHUB_REF": "refs/heads/master"}), \
                    patch.object(cache, "artifacts", return_value=[artifact]) as artifacts, \
                    patch.object(cache, "artifact_json", return_value={**previous, **changed}):
                self.assertEqual(expected, cache.legacy_retirements(
                    [entry], {"members": ["first", "second"]}))
                artifacts.assert_called_once_with("123")
        with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/master"}), \
                patch.object(cache, "artifacts", return_value=[artifact]), \
                patch.object(cache, "artifact_json", return_value=previous):
            self.assertEqual(set(), cache.legacy_retirements([entry], {"members": ["first"]}))

    def test_missing_unscoped_ownership_is_preserved(self):
        entry = {"id": 1, "key": f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}"}
        error = urllib.error.HTTPError("https://api.github.com", 404, "missing", {}, None)
        with patch.object(cache, "artifacts", side_effect=error), patch.object(cache, "api") as api:
            self.assertEqual(set(), cache.legacy_retirements([entry], {"members": ["x86_64"]}))
        api.assert_not_called()

    def test_unscoped_snapshot_is_retagged_without_repacking_or_changing_inputs(self):
        self.fixture()
        inputs = NATIVE_INPUTS
        fingerprint = cache.json_hash(inputs)
        group = cache.scheduling_group(inputs)
        sources, completion = cache.source_records(), cache.stamps(ROOTS)
        cache.write_json(cache.PLAN, {
            **SCOPE_METADATA, "inputs": inputs, "fingerprint": fingerprint, "roots": ROOTS,
            "sources": sources, "restored_stamps": completion, "restored_downloads": {}})
        cache.CACHE.mkdir()
        payload = cache.CACHE / "state.tar.zst"
        payload.write_bytes(b"existing sealed state")
        original = {"cache_key": f"{cache.SCHEMA}-{fingerprint}-123-1-{group}",
                    "inputs": inputs, "fingerprint": fingerprint,
                    "payload_sha256": cache.digest(payload), "sources": sources, "stamps": completion}
        cache.write_json(cache.CACHE / "manifest.json", original)
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(cache, "source_records", return_value=sources), \
                patch.object(cache.subprocess, "run") as run:
            cache.snapshot()
        run.assert_not_called()
        saved = json.loads((cache.CACHE / "manifest.json").read_text())
        self.assertEqual(SCOPE_METADATA["scope"], cache.key_scope(saved["cache_key"]))
        self.assertEqual("456", cache.KEY_PATTERN.fullmatch(saved["cache_key"])["run"])
        for name in ("inputs", "fingerprint", "payload_sha256", "sources", "stamps"):
            self.assertEqual(original[name], saved[name])
        self.assertEqual(b"existing sealed state", payload.read_bytes())

    def test_scoped_snapshot_receipt_and_publisher_agree(self):
        self.fixture()
        inputs = NATIVE_INPUTS
        fingerprint = cache.json_hash(inputs)
        group = cache.scheduling_group(inputs)
        cache.write_json(cache.PLAN, {
            **SCOPE_METADATA, "inputs": inputs, "fingerprint": fingerprint,
            "roots": ROOTS, "sources": cache.source_records()})
        environment = {"GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1",
                       "GITHUB_REF": "refs/heads/master", "DEFAULT_BRANCH": "master",
                       "STATE_ARTIFACT_ID": "123"}
        with patch.dict(os.environ, environment):
            cache.snapshot()
            cache.receipt(group, ["x86_64"])
            saved = json.loads(cache.RECEIPT.read_text())
            with patch.object(cache, "caches", return_value=[]), \
                    patch.object(cache, "output") as output:
                cache.admit()
                self.assertEqual("true", dict(call.args for call in output.call_args_list)["save"])
            artifact = {"id": 124, "name": f"state-receipt-{group}-1", "expired": False}
            with patch.object(cache, "artifact_json", return_value=saved):
                self.assertEqual(saved, cache.load_receipts([artifact])[group])
            cache.write_json(cache.RECEIPT, {
                **saved, "native_target": {"board": "mvebu", "subtarget": "cortexa9"}})
            with patch.object(cache, "caches") as inventory:
                with self.assertRaisesRegex(ValueError, "damaged or mismatched"):
                    cache.admit()
            inventory.assert_not_called()

    def test_make_check_metadata_does_not_upload_duplicate_state(self):
        self.fixture()
        completion = cache.stamps(ROOTS)
        Path(ROOTS[2], ".prepared").touch()
        Path(self.stamp.parent, ".prepared_deadbeef_check").touch()
        self.assertEqual(completion, cache.stamps(ROOTS))
        cache.write_json(cache.PLAN, {"roots": ROOTS, "restored_stamps": completion, "restored_downloads": {},
                                     "sources": cache.source_records(), "fingerprint": "a" * 64})
        cache.CACHE.mkdir()
        payload = cache.CACHE / "state.tar.zst"
        payload.write_bytes(b"existing verified state")
        key = f"{cache.SCHEMA}-{'a' * 64}-123-1-{'b' * 64}-scope-{SCOPE_METADATA['scope']}"
        saved = {**SCOPE_METADATA, "cache_key": key, "fingerprint": "a" * 64}
        cache.write_json(cache.CACHE / "manifest.json", saved)
        with patch.object(cache, "api") as api:
            cache.snapshot()
            api.assert_not_called()
        self.assertEqual(b"existing verified state", payload.read_bytes())
        self.assertEqual(saved, json.loads((cache.CACHE / "manifest.json").read_text()))

    def test_receipt_requires_matching_native_inputs_and_identity(self):
        self.fixture()
        inputs = {**NATIVE_INPUTS, "schema": cache.SCHEMA, "root": str(Path.cwd())}
        group = cache.scheduling_group(inputs)
        key = f"{cache.SCHEMA}-{cache.json_hash(inputs)}-123-1-{group}"
        saved = {"schema": cache.SCHEMA, "group": group, "producer_attempt": "1",
                 "run_id": "456", "ref": "refs/heads/master", "artifact_id": 3,
                 "key": key, "fingerprint": cache.json_hash(inputs),
                 "input_hashes": cache.input_hashes(inputs)}
        cache.write_json(cache.PLAN, {"inputs": inputs, "fingerprint": cache.json_hash(inputs)})
        entries = [{"id": 2, "name": f"state-receipt-{group}-1", "expired": False},
                   {"id": 3, "name": f"state-payload-{group}-1", "expired": False}]
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "456", "GITHUB_REF": "refs/heads/master"}), \
                patch.object(cache, "artifacts", return_value=entries), \
                patch.object(cache, "artifact_json", return_value=saved), \
                patch.object(cache, "output") as output:
            cache.select(group)
            self.assertEqual(3, dict(call.args for call in output.call_args_list)["artifact_id"])
            original = saved.copy()
            for changes in (
                    {"input_hashes": {**saved["input_hashes"], "root": cache.json_hash("/different/build/path")}},
                    {"input_hashes": {**saved["input_hashes"], "make": cache.json_hash("different recipe")}},
                    {"ref": "refs/heads/other"}, {"run_id": "999"},
                    {"producer_attempt": "2"},
                    {"key": f"{cache.SCHEMA}-{cache.json_hash(inputs)}-123-1-{'f' * 64}"}):
                with self.subTest(changes=changes):
                    saved.update(original)
                    saved.update(changes)
                    output.reset_mock()
                    cache.select(group)
                    self.assertEqual("", dict(call.args for call in output.call_args_list)["key"])

    def test_snapshot_stores_download_metadata_without_download_payloads(self):
        self.fixture()
        Path("dl").mkdir()
        downloaded = Path("dl/test.tar.gz")
        downloaded.write_bytes(b"source archive")
        Path("dl/.download.lock").touch()
        Path("dl/link.tar.gz").symlink_to(downloaded.resolve())
        inputs = NATIVE_INPUTS
        fingerprint = cache.json_hash(inputs)
        cache.write_json(cache.PLAN, {
            **SCOPE_METADATA,
            "roots": ROOTS, "sources": cache.source_records(), "reused": True,
            "restored_stamps": cache.stamps(ROOTS), "fingerprint": fingerprint,
            "inputs": inputs,
        })
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}):
            cache.snapshot()
        saved = json.loads((cache.CACHE / "manifest.json").read_text())
        self.assertEqual({"dl/test.tar.gz"}, set(saved["downloads"]))
        self.assertEqual(cache.digest(downloaded), saved["downloads"][str(downloaded)]["sha256"])
        with subprocess.Popen(["zstd", "-dc", str(cache.CACHE / "state.tar.zst")],
                              stdout=subprocess.PIPE) as process:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                self.assertFalse(any(member.name.startswith("dl") for member in archive))
            self.assertEqual(0, process.wait())
        with patch.object(cache, "smoke"):
            cache.restore()
        self.assertEqual(saved["downloads"], json.loads(cache.PLAN.read_text())["restored_downloads"])


if __name__ == "__main__":
    unittest.main()
