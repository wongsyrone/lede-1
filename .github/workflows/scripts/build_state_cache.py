#!/usr/bin/env python3
"""Verified shared tools/toolchain state; never cache dl or target packages."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from decimal import Decimal

SCHEMA = "owrt-state-v4"
# Temporary: accept unscoped v4 keys until the default-branch migration is complete.
KEY_PATTERN = re.compile(
    re.escape(SCHEMA) + r"-(?P<fingerprint>[0-9a-f]{64})-(?P<run>[0-9]+)-[0-9]+"
    r"-(?P<group>[0-9a-f]{64})(?:-scope-(?P<scope>[0-9a-f]{64}))?")
WORK = Path(".ci-state")
CACHE = WORK / "cache"
PLAN = WORK / "plan.json"
RECEIPT = WORK / "receipt.json"
REJECTIONS = WORK / "rejections.json"
INPUT_PATHS = [
    "tools", "toolchain", "include", "scripts", "config", "target/linux",
    "Config.in", "Makefile", "rules.mk",
    ".github/workflows/build-release.yml",
    ".github/workflows/scripts/build_state_cache.py",
]
# Scope Buildbot's native version check to Make, without changing Kconfig defaults.
TOOLS_MAKE_FLAGS = ["SOURCE_DATE_EPOCH=0", "REVISION=ci-tools", "CONFIG_BUILDBOT=y"]


def command(*args, **kwargs):
    return subprocess.check_output(args, **kwargs).decode().strip()


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def output(name, value):
    print(f"{name}={value}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"{name}={value}\n")


def report(message):
    print(message, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(message + "\n\n")


def source_records():
    paths = command("git", "ls-files", "-z", "--", *INPUT_PATHS).split("\0")
    records = {}
    for name in sorted(filter(None, paths)):
        path = Path(name)
        info = path.lstat()
        records[name] = {
            "mode": stat.S_IMODE(info.st_mode),
            "link": os.readlink(path) if path.is_symlink() else None,
            "sha256": None if path.is_symlink() else digest(path),
            "mtime_ns": info.st_mtime_ns,
        }
    return records


def download_records():
    directory = Path("dl")
    if directory.is_symlink():
        raise ValueError("Download directory must not be a symlink")
    return {
        str(path): {
            "mode": stat.S_IMODE(path.stat().st_mode), "link": None,
            "sha256": digest(path), "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in sorted(directory.glob("*"))
        if not path.name.startswith(".") and not path.is_symlink() and path.is_file()
    }


def identity(records):
    return {name: {k: v for k, v in record.items() if k != "mtime_ns"}
            for name, record in records.items()}


def retain_source_times(saved, live):
    retained = 0
    for name, record in saved.items():
        if name not in live or identity({name: live[name]}) != identity({name: record}):
            continue
        path = Path(name)
        os.utime(path, ns=(path.lstat().st_atime_ns, record["mtime_ns"]), follow_symlinks=False)
        if path.lstat().st_mtime_ns != record["mtime_ns"]:
            raise ValueError("Source timestamp precision changed")
        retained += 1
    return retained


def make_inputs():
    """Let Make expand the selected components and their actual build recipes."""
    components = command(
        "make", "--no-print-directory", "-s", "OPENWRT_BUILD=1", *TOOLS_MAKE_FLAGS,
        "CI_COMPONENTS=$(addprefix tools/,$(sort $(tools-y))) "
        "$(addprefix toolchain/,$(toolchain/builddirs))", "val.CI_COMPONENTS",
    ).split()
    variables = (
        "PKG_VERSION", "PKG_SOURCE", "PKG_HASH", "PKG_MIRROR_HASH",
        "HOST_CONFIGURE_ARGS", "HOST_CONFIGURE_VARS", "HOST_MAKE_VARS",
        "HOST_CFLAGS", "HOST_CXXFLAGS", "HOST_LDFLAGS", "TARGET_CFLAGS",
        "TARGET_LDFLAGS", "GCC_CONFIGURE", "TARGET_LANGUAGES",
        "Host/Prepare", "Host/Configure", "Host/Compile", "Host/Install",
    )
    signature = "\n".join(name + "=$(" + name + ")" for name in variables)
    result = {}
    WORK.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-inputs-", dir=WORK) as temporary:
        query, answer = Path(temporary, "query.mk").resolve(), Path(temporary, "answer").resolve()
        query.write_text("include Makefile\n.PHONY: ci-cache-inputs\n"
                         "ci-cache-inputs:\n\t@: $(file >" + str(answer) + ",$(CI_SIGNATURE))\n")
        for component in sorted(components):
            subprocess.run([
                "make", "--no-print-directory", "-s", "-C", component, "-f", str(query),
                "TOPDIR=" + str(Path.cwd()), "OPENWRT_BUILD=1", *TOOLS_MAKE_FLAGS,
                "CI_SIGNATURE=" + signature, "ci-cache-inputs",
            ], check=True)
            result[component] = answer.read_text()
    return result


def pinned_feeds():
    locked = Path("feeds.conf").read_text()
    for line in locked.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        kind, name, url = line.split()
        if kind not in ("src-git", "src-git-full") or not re.fullmatch(
                r"[A-Za-z0-9_-]+", name):
            raise ValueError("State cache requires pinned Git feeds")
        revision = url.rsplit("^", 1)[-1]
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or command(
                "git", "-C", f"feeds/{name}", "rev-parse", "HEAD") != revision:
            raise ValueError(f"Feed {name} is not at its locked revision")
        if command("git", "-C", f"feeds/{name}", "status", "--porcelain",
                   "--untracked-files=no"):
            raise ValueError(f"Feed {name} has modified tracked files")
    return locked


def check_roots(roots):
    if len(roots) != 4 or roots[:1] != ["build_dir/host"] or roots[2:3] != ["staging_dir/host"]:
        raise ValueError("Unexpected state roots")
    if not re.fullmatch(r"build_dir/toolchain-[A-Za-z0-9_.+-]+", roots[1]):
        raise ValueError("Unexpected toolchain build directory")
    if roots[3] != "staging_dir/" + roots[1].split("/", 1)[1]:
        raise ValueError("Toolchain staging/build directories differ")
    for name in roots:
        path = Path(name)
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("State roots must not be symlinks")
    return roots


def configure(target):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", target) or not Path("cfg", target).is_file():
        raise ValueError("Invalid build target")
    Path(".config").write_text(Path("cfg", target).read_text() + """
CONFIG_DEVEL=y
CONFIG_BUILD_LOG=y
CONFIG_AUTOREBUILD=y
# CONFIG_CCACHE is not set
""")
    subprocess.run(["make", "defconfig"], check=True)
    diffconfig = command("./scripts/diffconfig.sh")
    Path(target + ".diffconfig").write_text(diffconfig + "\n")


def scheduling_group(inputs):
    return json_hash({name: inputs[name] for name in
                      ("make", "roots", "common_sources", "tools_make_flags")})


def input_hashes(inputs):
    return {name: json_hash(value) for name, value in inputs.items()}


def generation_key(fingerprint, inputs, scope):
    return (f"{SCHEMA}-{fingerprint}-" + os.environ.get("GITHUB_RUN_ID", "local") +
            "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1") + "-" + scheduling_group(inputs) +
            "-scope-" + scope)


def plan(target, emit=True):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", target) or not Path("cfg", target).is_file():
        raise ValueError("Invalid build target")
    roots = []
    for variable in ("BUILD_DIR_HOST", "BUILD_DIR_TOOLCHAIN", "STAGING_DIR_HOST", "TOOLCHAIN_DIR"):
        value = command("make", "--no-print-directory", "-s", f"val.{variable}")
        roots.append(str(Path(value).relative_to(Path.cwd())))
    check_roots(roots)
    native_target = {
        name.lower(): command("make", "--no-print-directory", "-s", f"val.{name}")
        for name in ("BOARD", "SUBTARGET")
    }
    if not native_target["board"] or any(
            not re.fullmatch(r"[A-Za-z0-9_.+-]*", value) for value in native_target.values()):
        raise ValueError("Unexpected native target identity")
    scope = json_hash(native_target)
    sources = source_records()
    pinned_feeds()
    inputs = {
        "schema": SCHEMA, "root": str(Path.cwd()),
        "make": make_inputs(), "roots": roots, "tools_make_flags": TOOLS_MAKE_FLAGS,
        # Native per-component stamps do not cover changes to shared build helpers.
        "common_sources": identity({
            name: record for name, record in sources.items()
            if name in ("Makefile", "rules.mk") or name.startswith(
                ("include/", "scripts/", "tools/include/", "target/linux/"))
        }),
    }
    fingerprint = json_hash(inputs)
    prefix = f"{SCHEMA}-{fingerprint}-"
    key = generation_key(fingerprint, inputs, scope)
    result = {"inputs": inputs, "fingerprint": fingerprint, "sources": sources,
              "target": target, "reused": False, "roots": roots, "cache_key": key,
              "native_target": native_target, "scope": scope}
    write_json(PLAN, result)
    if emit:
        output("prefix", prefix)
        output("key", key)
        report("Input field hashes: `" + json.dumps(input_hashes(inputs), sort_keys=True) + "`")
    report(f"State input fingerprint ({target}): `{fingerprint}`")
    return result


def group_targets(targets):
    groups, builds = {}, []
    for target in targets:
        configure(target)
        current = plan(target, emit=False)
        group = scheduling_group(current["inputs"])
        groups.setdefault(group, {"group": group, "target": target, "members": []})["members"].append(target)
        builds.append({"target": target, "group": group})
    output("groups", json.dumps({"include": list(groups.values())}, separators=(",", ":")))
    output("builds", json.dumps({"include": builds}, separators=(",", ":")))
    report("Native Make groups: `" + json.dumps(list(groups.values())) + "`")


def check_group(group, members):
    expected = None
    # End with the representative profile's config and plan.
    for target in reversed(members):
        configure(target)
        current = plan(target, emit=False)
        if scheduling_group(current["inputs"]) != group or (
                expected is not None and current["inputs"] != expected):
            raise ValueError("Producer inputs differ from the proposed shared group; consumers must build independently")
        expected = current["inputs"]
    if expected is None:
        raise ValueError("Empty toolchain group")
    plan(members[0])


def stamps(roots):
    result = {}
    for root in roots:
        for directory, _, files in os.walk(root):
            for name in files:
                if name.endswith(("_check", "_check.1")) or (
                        name == ".prepared" and directory == root):
                    continue
                if name in (".built", ".configured") or name.startswith(".prepared") or name.endswith("_installed"):
                    path = Path(directory, name)
                    if not path.is_symlink():
                        result[str(path)] = [path.stat().st_mtime_ns, digest(path)]
    return result


def smoke(roots):
    host, toolchain = Path(roots[2]), Path(roots[3])
    if not list(host.glob("stamp/.tools_compile*")) or not (toolchain / "stamp/.gcc_final_installed").is_file():
        raise ValueError("Native tools/toolchain completion stamps missing")
    if not list(Path(roots[0]).glob("*/.built")) or not list(Path(roots[1]).glob("*/.built")):
        raise ValueError("Native build completion state missing")
    expected = hashlib.sha256(b"cache-smoke").hexdigest()
    actual = command(str(host / "bin/mkhash"), "sha256", input=b"cache-smoke")
    if actual != expected:
        raise ValueError("Host mkhash smoke test failed")
    subprocess.run([str(host / "bin/tar"), "--version"], check=True, stdout=subprocess.DEVNULL)
    # OpenWrt installs GNU target aliases pointing to the same compiler.
    compilers = {path.resolve(): path for path in
                 (toolchain / "bin").glob("*-openwrt-linux*-gcc")}
    if len(compilers) != 1:
        raise ValueError("Expected one OpenWrt cross compiler")
    gcc = next(iter(compilers.values()))
    triple = command(str(gcc), "-dumpmachine")
    machines = {"arm": 40, "armeb": 40, "mips": 8, "mipsel": 8,
                "x86_64": 62, "aarch64": 183, "i386": 3, "i486": 3,
                "i586": 3, "i686": 3, "riscv64": 243}
    expected_machine = machines[triple.split("-")[0]]
    env = {**os.environ, "STAGING_DIR": str(toolchain.resolve()),
           "PATH": str(host.resolve() / "bin") + ":" + os.environ["PATH"]}
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=WORK) as temporary:
        binary = Path(temporary, "test")
        for compiler, source, language in (
            (gcc, b"#include <stdio.h>\nint main(void){return puts(\"cache-smoke\")<0;}\n", "c"),
            (Path(str(gcc)[:-3] + "g++"),
             b"#include <string>\nint main(){return std::string(\"cache-smoke\").empty();}\n", "c++"),
        ):
            subprocess.run([str(compiler), "-x", language, "-", "-o", str(binary)],
                           input=source, env=env, check=True)
            elf = binary.read_bytes()[:20]
            byteorder = "little" if elf[5] == 1 else "big"
            if elf[:4] != b"\x7fELF" or int.from_bytes(elf[18:20], byteorder) != expected_machine:
                raise ValueError("Cross compiler produced unexpected ELF architecture")
    report(f"Host tools and C/C++ link smoke tests passed: `{triple}`")


def validate_members(members, roots):
    names, links = set(), {}
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or str(path) != member.name or
                not any(member.name == root or member.name.startswith(root + "/") for root in roots)):
            raise ValueError("Archive path escapes state roots")
        if member.name in names or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError("Duplicate or unsupported archive member")
        names.add(member.name)
        if member.issym() or member.islnk():
            links[member.name] = member
    for name in names:
        if any(str(parent) in links for parent in PurePosixPath(name).parents):
            raise ValueError("Archive would write through a link")
    for member in links.values():
        if member.islnk() and (member.linkname not in names or member.linkname in links):
            raise ValueError("Unsafe archive hard link")
        if member.issym() and os.path.isabs(member.linkname):
            allowed = (str(Path.cwd()) + "/", "/usr/", "/bin/", "/lib/", "/lib64/")
            if not os.path.normpath(member.linkname).startswith(allowed):
                raise ValueError("Unexpected absolute symlink")
    if not all(root in names for root in roots):
        raise ValueError("Archive is missing a state root")


def clean(roots):
    for name in check_roots(roots):
        path = Path(name)
        if path.exists():
            shutil.rmtree(path)


def restore():
    current = json.loads(PLAN.read_text())
    current["reused"] = False
    current.pop("restored_stamps", None)
    current.pop("restored_downloads", None)
    write_json(PLAN, current)
    if not (CACHE / "manifest.json").exists():
        output("reused", "false")
        return
    verified_payload = False
    try:
        saved = json.loads((CACHE / "manifest.json").read_text())
        if (not isinstance(saved, dict) or not isinstance(saved.get("inputs"), dict) or
                json_hash(saved["inputs"]) != saved["fingerprint"] or
                key_fingerprint(saved["cache_key"]) != saved["fingerprint"] or
                key_group(saved["cache_key"]) != scheduling_group(saved["inputs"]) or
                not scope_metadata_matches(saved["cache_key"], saved)):
            raise ValueError("Snapshot manifest identity is corrupt")
        if saved.get("downloads") is not None:
            if not isinstance(saved["downloads"], dict):
                raise ValueError("Snapshot download metadata is corrupt")
            for name, record in saved["downloads"].items():
                path = PurePosixPath(name)
                if (str(path) != name or path.parent != PurePosixPath("dl") or path.name.startswith(".") or
                        not isinstance(record, dict) or set(record) != {"mode", "link", "sha256", "mtime_ns"} or
                        type(record["mode"]) is not int or not 0 <= record["mode"] <= 0o7777 or
                        record["link"] is not None or not isinstance(record["sha256"], str) or
                        not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) or
                        type(record["mtime_ns"]) is not int or record["mtime_ns"] < 0):
                    raise ValueError("Snapshot download metadata is corrupt")
        expected, actual = current["inputs"], saved["inputs"]
        if actual != expected:
            changed = sorted(name for name in expected.keys() | actual.keys()
                             if expected.get(name) != actual.get(name))
            report(f"Snapshot is incompatible in {changed}; its generation remains valid for its original inputs.")
            shutil.rmtree(CACHE)
            output("reused", "false")
            return
        payload = CACHE / "state.tar.zst"
        if digest(payload) != saved["payload_sha256"]:
            raise ValueError("Snapshot payload checksum mismatch")
        with subprocess.Popen(["zstd", "-dc", str(payload)], stdout=subprocess.PIPE) as decoder:
            with tarfile.open(fileobj=decoder.stdout, mode="r|") as archive:
                members = list(archive)
            if decoder.wait() != 0:
                raise ValueError("Snapshot decompression failed")
        validate_members(members, current["roots"])
        verified_payload = True
        with tempfile.TemporaryDirectory(prefix="restore-", dir=WORK) as temporary:
            subprocess.run(["tar", "--zstd", "-xf", str(payload.resolve()),
                            "--no-same-owner", "--same-permissions", "-C", temporary], check=True)
            for member in members:
                info = Path(temporary, member.name).lstat()
                mtime_ns = int(Decimal(member.pax_headers.get("mtime", str(member.mtime))) * 1_000_000_000)
                if info.st_mtime_ns != mtime_ns or stat.S_IMODE(info.st_mode) != member.mode:
                    raise ValueError("Archive metadata precision or permissions changed")
            clean(current["roots"])
            for root in current["roots"]:
                Path(root).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(Path(temporary, root)), root)
        retained = retain_source_times(saved["sources"], source_records())
        if stamps(current["roots"]) != saved["stamps"]:
            raise ValueError("Native completion stamps changed during restore")
        smoke(current["roots"])
        current["reused"] = True
        current["restored_stamps"] = saved["stamps"]
        current["restored_downloads"] = saved.get("downloads")
        current["cache_key"] = saved["cache_key"]
        write_json(PLAN, current)
        output("reused", "true")
        report(f"Verified state restored; retained timestamps for {retained} unchanged source files. "
               "Changed sources remain subject to native Make checks.")
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        report(f"State rejected; rebuilding tools/toolchain: {error}")
        clean(current["roots"])
        if os.environ.get("STATE_ORIGIN", "cache") == "cache" or verified_payload:
            retire()
            output("rejected", "true")
        shutil.rmtree(CACHE)
        output("reused", "false")


def compile_tools():
    current = json.loads(PLAN.read_text())

    def run_make(*targets):
        with Path("toolchain.log").open("a") as log:
            for target in targets:
                with subprocess.Popen(["make", target, "-j" + command("nproc"), *TOOLS_MAKE_FLAGS],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
                    for line in process.stdout:
                        print(line, end="", flush=True)
                        log.write(line)
                    if process.wait():
                        raise ValueError(f"{target} failed; see toolchain.log")

    def compile_once():
        run_make("tools/compile", "toolchain/compile")
        smoke(current["roots"])

    if current["reused"]:
        # Native .prepared depends on dl archives; a fresh download would rebuild it.
        run_make("tools/download", "toolchain/download")
        if current.get("restored_downloads") is not None:
            retained = retain_source_times(current["restored_downloads"], download_records())
            report(f"Retained timestamps for {retained} identical downloaded source archives. "
                   "Changed downloads remain subject to native Make checks.")
        else:
            report("Snapshot has no download timestamp metadata; native Make may rebuild affected components.")

    try:
        compile_once()
    except (ValueError, OSError, subprocess.SubprocessError):
        if not current["reused"]:
            raise
        retire()
        clean(current["roots"])
        current["reused"] = False
        current.pop("restored_stamps", None)
        current.pop("restored_downloads", None)
        write_json(PLAN, current)
        subprocess.run(["make", "defconfig"], check=True)
        report("Retrying tools/toolchain once with clean state.")
        compile_once()
    completion = stamps(current["roots"])
    previous = current.get("restored_stamps", {})
    unchanged = current.get("restored_stamps") == completion
    if current["reused"] and not unchanged:
        report("Native completion stamp changes: `" + json.dumps({
            "added": sorted(completion.keys() - previous.keys()),
            "removed": sorted(previous.keys() - completion.keys()),
            "changed": sorted(name for name in completion.keys() & previous.keys()
                              if completion[name] != previous[name]),
        }) + "`")
    report(f"Tools/toolchain checked by Make; reused={current['reused']}, "
           f"completion stamps unchanged={unchanged}.")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        redirected = super().redirect_request(request, fp, code, message, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


def api_bytes(path, method="GET"):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/{path}",
        method=method, headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    with urllib.request.build_opener(SafeRedirect()).open(request, timeout=30) as response:
        return response.read()


def api(path, method="GET"):
    body = api_bytes(path, method)
    return json.loads(body) if body else {}


def caches():
    result, page = [], 1
    while True:
        batch = api(f"caches?per_page=100&page={page}")["actions_caches"]
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def retire():
    """Record an exact generation; only the final serial job may delete it."""
    current = json.loads(PLAN.read_text())
    matched = os.environ.get("MATCHED_KEY") or current.get("cache_key", "")
    if not key_fingerprint(matched) or (
            key_fingerprint(matched) != current["fingerprint"] and
            matched != current.get("cache_key")):
        return
    rejected = json.loads(REJECTIONS.read_text()) if REJECTIONS.exists() else []
    record = {"key": matched, "ref": "refs/heads/" + os.environ.get("DEFAULT_BRANCH", "")}
    if record not in rejected:
        rejected.append(record)
    write_json(REJECTIONS, rejected)
    report(f"Rejected generation queued for final retirement: `{matched}`")


def key_fingerprint(key):
    match = KEY_PATTERN.fullmatch(key)
    return match["fingerprint"] if match else None


def key_group(key):
    match = KEY_PATTERN.fullmatch(key)
    return match["group"] if match else None


def key_scope(key):
    match = KEY_PATTERN.fullmatch(key)
    return match["scope"] if match else None


def scope_metadata_matches(key, saved):
    scope = key_scope(key)
    if scope is None:
        return "scope" not in saved and "native_target" not in saved
    return scope == saved.get("scope") == json_hash(saved.get("native_target"))


def snapshot():
    current = json.loads(PLAN.read_text())
    completion = stamps(current["roots"])
    unchanged = current.get("restored_stamps") == completion
    output("completion_unchanged", str(unchanged).lower())
    report(f"Native completion stamps: {len(completion)}; unchanged after Make: {unchanged}.")
    output("handoff", "false")
    sources = source_records()
    if identity(sources) != identity(current["sources"]):
        raise ValueError("Source inputs changed during compilation")
    payload = CACHE / "state.tar.zst"
    if (not unchanged or current.get("restored_downloads") is None or
            os.environ.get("FORCE_REBUILD") == "true" or not payload.exists()):
        CACHE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "--format=posix", "--pax-option=delete=atime,delete=ctime",
                        "-I", "zstd -T0 -3", "-cf", str(payload), *current["roots"]], check=True)
        key = generation_key(current["fingerprint"], current["inputs"], current["scope"])
        write_json(CACHE / "manifest.json", {
            **current, "cache_key": key, "sources": sources, "stamps": completion,
            "downloads": download_records(),
            "payload_sha256": digest(payload), "run_id": os.environ["GITHUB_RUN_ID"],
        })
    else:
        saved = json.loads((CACHE / "manifest.json").read_text())
        # Temporary unscoped-v4 migration; remove once no unscoped default-branch keys remain.
        if key_scope(saved["cache_key"]) is None:
            saved.update({name: current[name] for name in ("native_target", "scope")})
            saved["cache_key"] = generation_key(current["fingerprint"], current["inputs"], current["scope"])
            saved["run_id"] = os.environ["GITHUB_RUN_ID"]
            write_json(CACHE / "manifest.json", saved)
    output("handoff", "true")


def receipt(group, members):
    saved = json.loads((CACHE / "manifest.json").read_text())
    write_json(RECEIPT, {
        "schema": SCHEMA, "group": group, "members": members,
        "fingerprint": saved["fingerprint"], "key": saved["cache_key"],
        "artifact_id": int(os.environ["STATE_ARTIFACT_ID"]),
        "producer_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "run_id": os.environ["GITHUB_RUN_ID"], "ref": os.environ["GITHUB_REF"],
        "input_hashes": input_hashes(saved["inputs"]),
        "native_target": saved["native_target"], "scope": saved["scope"],
    })


def artifacts(run_id=None):
    result, page = [], 1
    while True:
        batch = api(f"runs/{run_id or os.environ['GITHUB_RUN_ID']}/artifacts?per_page=100&page={page}")["artifacts"]
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def artifact_json(entry, filename):
    with zipfile.ZipFile(io.BytesIO(api_bytes(f"artifacts/{entry['id']}/zip"))) as archive:
        if archive.namelist() != [filename] or archive.getinfo(filename).file_size > 65_536:
            raise ValueError("Unexpected state metadata artifact")
        return json.loads(archive.read(filename))


def load_receipts(entries, groups=None, run_id=None):
    latest, result = {}, {}
    for entry in entries:
        match = re.fullmatch(r"state-receipt-([0-9a-f]{64})-([0-9]+)", entry["name"])
        if match and not entry["expired"]:
            group, attempt = match[1], int(match[2])
            if groups is not None and group not in groups:
                continue
            if group not in latest or attempt > latest[group][0]:
                latest[group] = (attempt, entry)
    for group, (attempt, entry) in latest.items():
        try:
            saved = artifact_json(entry, "receipt.json")
            if (saved["schema"] != SCHEMA or saved["group"] != group or
                    saved["run_id"] != (run_id or os.environ["GITHUB_RUN_ID"]) or
                    saved["ref"] != os.environ["GITHUB_REF"] or
                    str(attempt) != saved["producer_attempt"] or
                    key_fingerprint(saved["key"]) != saved["fingerprint"] or
                    key_group(saved["key"]) != group or
                    not scope_metadata_matches(saved["key"], saved)):
                raise ValueError("State receipt identity differs")
            result[group] = saved
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
            report(f"::warning::Receipt unavailable for group {group}: {error}")
    return result


def select(group, publisher=False):
    output("artifact_id", "")
    output("key", "")
    try:
        entries = artifacts()
        saved = load_receipts(entries, {group}).get(group)
        if saved is None:
            report("No producer receipt; normal cache lookup or cold build will be used.")
            return
        if not publisher:
            current = json.loads(PLAN.read_text())
            expected = input_hashes(current["inputs"])
            actual = saved["input_hashes"]
            if actual != expected:
                changed = sorted(name for name in expected.keys() | actual.keys()
                                 if expected.get(name) != actual.get(name))
                report(f"Producer is incompatible in {changed}; building this profile independently.")
                return
        write_json(RECEIPT, saved)
        output("key", saved["key"])
        name = f"state-payload-{group}-{saved['producer_attempt']}"
        if any(entry["id"] == saved["artifact_id"] and entry["name"] == name and
               not entry["expired"] for entry in entries):
            output("artifact_id", saved["artifact_id"])
        report(f"Selected producer attempt {saved['producer_attempt']}; generation `{saved['key']}`.")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        report(f"::warning::Producer handoff unavailable: {error}")


def delete_entry(entry):
    try:
        api(f"caches/{entry['id']}", "DELETE")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    report(f"Retired cache ID {entry['id']} ({entry['size_in_bytes']} bytes): `{entry['key']}`")


def admit():
    output("save", "false")
    if not RECEIPT.exists() or not (CACHE / "manifest.json").exists():
        return
    if os.environ["GITHUB_REF"] != "refs/heads/" + os.environ["DEFAULT_BRANCH"]:
        report("Persistent state writes are restricted to the default branch.")
        return
    saved = json.loads(RECEIPT.read_text())
    manifest = json.loads((CACHE / "manifest.json").read_text())
    payload = CACHE / "state.tar.zst"
    if (saved["ref"] != os.environ["GITHUB_REF"] or manifest["cache_key"] != saved["key"] or
            manifest["fingerprint"] != saved["fingerprint"] or
            json_hash(manifest["inputs"]) != saved["fingerprint"] or
            key_fingerprint(saved["key"]) != saved["fingerprint"] or
            scheduling_group(manifest["inputs"]) != saved["group"] or
            key_group(saved["key"]) != saved["group"] or
            not scope_metadata_matches(saved["key"], saved) or
            not scope_metadata_matches(manifest["cache_key"], manifest) or
            saved.get("scope") != manifest.get("scope") or
            digest(payload) != manifest["payload_sha256"]):
        raise ValueError("Publisher received a damaged or mismatched snapshot")
    entries = caches()
    if any(entry["key"] == saved["key"] and entry["ref"] == saved["ref"] for entry in entries):
        report("Verified generation already exists; no duplicate upload.")
        return
    report("Verified shared state ready for upload; repository capacity is managed by GitHub.")
    output("save", "true")


def legacy_retirements(entries, saved):
    """Temporary unscoped-v4 migration; remove with the optional key scope parser."""
    receipts, result = {}, set()
    for entry in entries:
        match = KEY_PATTERN.fullmatch(entry["key"])
        if match is None or match["scope"] is not None:
            continue
        run_id = match["run"]
        try:
            if run_id not in receipts:
                receipts[run_id] = load_receipts(artifacts(run_id), run_id=run_id)
            previous = receipts[run_id].get(match["group"])
            if (previous and previous["key"] == entry["key"] and previous["members"] and
                    set(previous["members"]) <= set(saved["members"])):
                result.add(entry["id"])
            else:
                report(f"Unscoped cache ID {entry['id']} retained; complete replacement ownership was not proven.")
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
            receipts[run_id] = {}
            report(f"::warning::Unscoped cache ownership unavailable for run {run_id}; retained: {error}")
    return result


def confirm():
    if not RECEIPT.exists() or os.environ["GITHUB_REF"] != "refs/heads/" + os.environ["DEFAULT_BRANCH"]:
        return
    saved = json.loads(RECEIPT.read_text())
    if (saved["ref"] != os.environ["GITHUB_REF"] or
            key_fingerprint(saved["key"]) != saved["fingerprint"] or
            key_group(saved["key"]) != saved["group"] or
            not scope_metadata_matches(saved["key"], saved)):
        raise ValueError("State receipt identity differs")
    active_groups = {item["group"] for item in json.loads(
        os.environ.get("STATE_GROUPS", '{"include":[]}'))["include"]}
    if active_groups and saved["group"] not in active_groups:
        raise ValueError("Publisher group is absent from the active build plan")
    for delay in (0, 2, 5, 10):
        if delay:
            time.sleep(delay)
        entries = caches()
        visible = [entry for entry in entries if entry["key"] == saved["key"] and
                   entry["ref"] == os.environ["GITHUB_REF"] and entry["size_in_bytes"] > 0]
        if len(visible) == 1:
            report(f"Confirmed persisted generation ID {visible[0]['id']}: `{saved['key']}`")
            candidates = [entry for entry in entries
                          if entry["ref"] == os.environ["GITHUB_REF"] and
                          entry["id"] != visible[0]["id"] and
                          key_group(entry["key"]) not in active_groups - {saved["group"]}]
            legacy = legacy_retirements(
                [entry for entry in candidates if key_group(entry["key"]) != saved["group"]], saved
            ) if saved.get("scope") is not None else set()
            for entry in candidates:
                if (key_group(entry["key"]) == saved["group"] or
                        saved.get("scope") is not None and key_scope(entry["key"]) == saved["scope"] or
                        entry["id"] in legacy):
                    delete_entry(entry)
            return
    report("::warning::New generation was not confirmed; previous generations retained.")


def finalize():
    entries = artifacts()
    rejected = set()
    for entry in entries:
        if re.fullmatch(r"state-rejections-(?:tools-[0-9a-f]{64}|build-[A-Za-z0-9_.-]+)-[0-9]+",
                        entry["name"]) and not entry["expired"]:
            for record in artifact_json(entry, "rejections.json"):
                if key_fingerprint(record["key"]) and record["ref"] == "refs/heads/" + os.environ["DEFAULT_BRANCH"]:
                    rejected.add((record["key"], record["ref"]))
    if rejected:
        for entry in caches():
            if (entry["key"], entry["ref"]) in rejected:
                delete_entry(entry)
    for entry in entries:
        if re.fullmatch(r"state-(?:payload-[0-9a-f]{64}|rejections-(?:tools-[0-9a-f]{64}|build-[A-Za-z0-9_.-]+))-[0-9]+",
                        entry["name"]):
            try:
                api(f"artifacts/{entry['id']}", "DELETE")
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            report(f"Removed temporary state artifact {entry['id']}: `{entry['name']}`")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("configure", "plan", "group", "check-group", "compile",
                                            "restore", "snapshot", "receipt", "select",
                                            "admit", "confirm", "finalize", "retire", "clean", "validate"))
    parser.add_argument("--target")
    parser.add_argument("--targets", type=json.loads)
    parser.add_argument("--group")
    parser.add_argument("--members", type=json.loads)
    parser.add_argument("--publisher", action="store_true")
    args = parser.parse_args()
    if args.operation == "plan":
        plan(args.target)
    elif args.operation == "configure":
        configure(args.target)
    elif args.operation == "group":
        group_targets(args.targets)
    elif args.operation == "check-group":
        check_group(args.group, args.members)
    elif args.operation == "compile":
        compile_tools()
    elif args.operation == "receipt":
        receipt(args.group, args.members)
    elif args.operation == "select":
        select(args.group, args.publisher)
    elif args.operation == "clean":
        clean(json.loads(PLAN.read_text())["roots"])
    elif args.operation == "validate":
        smoke(json.loads(PLAN.read_text())["roots"])
    else:
        globals()[args.operation]()


if __name__ == "__main__":
    main()
