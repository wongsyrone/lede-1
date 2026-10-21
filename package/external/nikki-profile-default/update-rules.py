#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Lock the current upstream rule output to one verified build snapshot."""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
import urllib.error
import urllib.request


REPOSITORY = "MetaCubeX/meta-rules-dat"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
RAW_ROOT = f"https://raw.githubusercontent.com/{REPOSITORY}"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
ENTRY_PATTERN = re.compile(
    r"^\$\(eval \$\(call RuleDownload,([A-Za-z0-9_.!+-]+),"
    r"([A-Za-z0-9_./@!+-]+),([0-9a-f]{64})\)\)$", re.MULTILINE
)
MAX_FILE_SIZE = 64 * 1024 * 1024


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
    temporary.chmod(0o644)
    temporary.replace(path)


def entries_from_manifest(path):
    text = path.read_text(encoding="utf-8")
    entries = ENTRY_PATTERN.findall(text)
    if not entries or len(entries) != text.count("$(call RuleDownload,") or (
        len({name for name, _, _ in entries}) != len(entries)
    ):
        raise ValueError("Rule manifest must contain unique RuleDownload entries")
    for name, source, _ in entries:
        parts = PurePosixPath(source).parts
        if name in (".", "..") or len(parts) != 3 or parts[:2] not in (
            ("geo", "geosite"), ("geo", "geoip")
        ) or any(part in (".", "..") for part in parts) or not source.endswith(".mrs"):
            raise ValueError(f"Invalid rule name or source path: {name}")
    return entries


class Github:
    def request(self, url, api=False):
        headers = {"User-Agent": "nikki-profile-default-rule-lock"}
        # The workflow supplies its ephemeral token. Local runs need no PAT.
        if api and os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=headers), timeout=45
                ) as response:
                    data = response.read(MAX_FILE_SIZE + 1)
                if len(data) > MAX_FILE_SIZE:
                    raise ValueError("Upstream response exceeds the size limit")
                return data
            except urllib.error.HTTPError as error:
                if attempt == 2 or error.code not in (429, 500, 502, 503, 504):
                    raise ValueError(f"Upstream HTTP {error.code}: {url}") from error
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise ValueError(f"Unable to download upstream data: {url}") from None
            time.sleep(attempt + 1)
        raise AssertionError("Unreachable retry state")

    def json(self, path):
        return json.loads(self.request(API_ROOT + path, api=True))

    def rule(self, revision, path):
        return self.request(f"{RAW_ROOT}/{revision}/{path}")


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def resolve(client, entries, revision=None):
    if revision is None:
        revision = client.json("/git/ref/heads/meta")["object"]["sha"]
    if not SHA_PATTERN.fullmatch(revision):
        raise ValueError("Upstream revision must be a complete Git SHA")
    commit = client.json("/git/commits/" + revision)
    if commit["sha"] != revision or not SHA_PATTERN.fullmatch(commit["tree"]["sha"]):
        raise ValueError("Upstream commit identity does not match")
    committed = datetime.datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00"))
    version = committed.astimezone(datetime.timezone.utc).strftime("%Y.%m.%d") + "~" + revision[:12]
    trees = {}

    def tree(sha):
        if sha not in trees:
            result = client.json("/git/trees/" + sha)
            if result.get("truncated") or result.get("sha") != sha:
                raise ValueError("Upstream returned an incomplete or mismatched Git tree")
            trees[sha] = {item["path"]: item for item in result["tree"]}
        return trees[sha]

    selected = []
    for name, source, _ in entries:
        current = commit["tree"]["sha"]
        parts = PurePosixPath(source).parts
        for part in parts[:-1]:
            item = tree(current).get(part)
            if not item or item["type"] != "tree" or not SHA_PATTERN.fullmatch(item["sha"]):
                raise ValueError(f"Missing upstream rule directory: {source}")
            current = item["sha"]
        item = tree(current).get(parts[-1])
        if not item or item["type"] != "blob" or item["mode"] != "100644":
            raise ValueError(f"Missing upstream rule file: {source}")
        if not SHA_PATTERN.fullmatch(item["sha"]) or not 0 < item["size"] <= MAX_FILE_SIZE:
            raise ValueError(f"Invalid upstream rule object: {source}")
        selected.append((name, source, item["sha"], item["size"]))
    return revision, version, commit["tree"]["sha"], selected


def snapshot(client, manifest, destination, download_dir, revision=None):
    entries = entries_from_manifest(manifest)
    revision, version, tree_sha, selected = resolve(client, entries, revision)

    def download(entry):
        name, source, expected_blob, expected_size = entry
        path = download_dir / f"nikki-rule-{revision}-{name}.mrs"
        data = path.read_bytes() if path.is_file() else b""
        if len(data) != expected_size or git_blob(data) != expected_blob:
            data = client.rule(revision, source)
        if len(data) != expected_size or git_blob(data) != expected_blob:
            raise ValueError(f"Rule content does not match its Git object: {source}")
        atomic_write(path, data)
        return name, source, hashlib.sha256(data).hexdigest()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as workers:
        locked = list(workers.map(download, selected))
    lines = [
        "# Generated build snapshot: MetaCubeX/meta-rules-dat, branch meta (GPL-3.0).",
        f"RULES_REV:={revision}",
        f"RULES_VERSION:={version}",
        f"# Source tree: {tree_sha}",
        "",
        "define Rules/Downloads",
        *[f"$(eval $(call RuleDownload,{name},{source},{sha256}))" for name, source, sha256 in locked],
        "endef",
        "",
    ]
    atomic_write(destination, "\n".join(lines).encode())
    return revision, len(locked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    package = Path(__file__).resolve().parent
    parser.add_argument("--manifest", type=Path, default=package / "rules.mk")
    parser.add_argument("--output", type=Path, default=package / "rules.mk")
    parser.add_argument("--download-dir", type=Path, default=package.parents[2] / "dl")
    parser.add_argument("--revision", help="Replay a specific immutable SHA instead of current meta")
    args = parser.parse_args()
    try:
        revision, count = snapshot(
            Github(), args.manifest, args.output, args.download_dir, args.revision
        )
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Rule snapshot failed: {error}\n")
    print(f"Locked {count} rules at {REPOSITORY}@{revision}")


if __name__ == "__main__":
    main()
