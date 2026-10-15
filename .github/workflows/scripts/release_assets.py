#!/usr/bin/env python3
"""Publishable assets and confirmed nightly retirement, scoped to one target."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

from build_state_cache import artifacts, digest, output, report, write_json

PREVIOUS = Path(".ci-release/previous.json")


def select(target):
    matches = [entry for entry in artifacts()
               if entry["name"] == "firmware-" + target and not entry["expired"]]
    if len(matches) > 1:
        raise ValueError("Ambiguous firmware artifacts")
    output("artifact_id", matches[0]["id"] if matches else "")
    if not matches:
        report(f"No successful firmware artifact for `{target}`; previous release assets retained.")


def api(path, method="GET", accept="application/vnd.github+json"):
    return subprocess.check_output([
        "gh", "api", "--method", method, "-H", "Accept: " + accept,
        f"repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
    ])


def get_release(tag):
    try:
        return json.loads(api("releases/tags/" + quote(tag, safe="")))
    except subprocess.CalledProcessError as error:
        # gh's JSON error response distinguishes a missing release from API outages.
        if json.loads(error.output).get("status") != "404":
            raise
        return None


def assets(release_id):
    result, page = [], 1
    while True:
        batch = json.loads(api(f"releases/{release_id}/assets?per_page=100&page={page}"))
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def checksum_names(text):
    names = set()
    for line in text.splitlines():
        match = re.fullmatch(r"[0-9a-f]{64} [ *]([A-Za-z0-9_][A-Za-z0-9_.+-]*)", line)
        if not match:
            raise ValueError("Invalid release checksum index")
        names.add(match[1])
    return names


def read_index(entry):
    data = api(f"releases/assets/{entry['id']}", accept="application/octet-stream")
    if len(data) > 1_000_000:
        raise ValueError("Unexpected release checksum index size")
    return data.decode()


def package(target, directory):
    files = sorted(directory.iterdir())
    if not any(path.name.endswith((".bin", ".img.gz", ".tar", ".tar.gz")) for path in files):
        raise ValueError("No firmware images to publish")
    for path in files:
        if path.is_symlink() or not path.is_file() or not re.fullmatch(
                r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", path.name):
            raise ValueError("Unexpected release asset")
    for path in files:
        path.rename(path.with_name(target + "--" + path.name))
    checksum = directory / f"sha256sums-{target}.txt"
    checksum.write_text("".join(
        f"{digest(path)}  {path.name}\n" for path in sorted(directory.iterdir())))


def prepare(target, tag):
    release = get_release(tag)
    owned, protected = set(), set()
    legacy_verified = True
    if release:
        for entry in assets(release["id"]):
            match = re.fullmatch(r"sha256sums-([A-Za-z0-9_.-]+)\.txt", entry["name"])
            if match and match[1] != "all":
                try:
                    names = checksum_names(read_index(entry))
                except (ValueError, subprocess.CalledProcessError) as error:
                    legacy_verified = False
                    report(f"::warning::Legacy ownership unavailable for {entry['name']}: {error}; "
                           "unprefixed assets will be retained.")
                    continue
                if match[1] == target:
                    owned.update(names)
                else:
                    protected.update(names)
    write_json(PREVIOUS, {
        "target": target, "tag": tag, "release_id": release["id"] if release else None,
        "legacy": sorted(owned - protected) if legacy_verified else [],
    })
    report(f"Recorded previous release ownership for `{target}`.")


def retire(target, tag, directory):
    previous = json.loads(PREVIOUS.read_text())
    release = get_release(tag)
    if (previous["target"] != target or previous["tag"] != tag or release is None or
            previous["release_id"] not in (None, release["id"])):
        raise ValueError("Release retirement identity differs")
    entries = assets(release["id"])
    current = {path.name: path for path in directory.iterdir() if path.is_file()}
    checksum = f"sha256sums-{target}.txt"
    if (not any(name.endswith((".bin", ".img.gz", ".tar", ".tar.gz")) for name in current) or
            checksum not in current or
            checksum_names(current[checksum].read_text()) != current.keys() - {checksum} or
            any(name != checksum and name.split("--", 1)[0] != target for name in current)):
        raise ValueError("Release retirement received an invalid target payload")
    for name, path in current.items():
        visible = [entry for entry in entries if entry["name"] == name]
        if (len(visible) != 1 or visible[0].get("state") != "uploaded" or
                visible[0]["size"] != path.stat().st_size or
                visible[0].get("digest") != "sha256:" + digest(path)):
            raise ValueError(f"New release asset not confirmed: {name}; previous assets retained")
    legacy = set(previous["legacy"])
    for entry in entries:
        name = entry["name"]
        if name not in current and (
                name.startswith(target + "--") or name in legacy or name == "sha256sums-all.txt"):
            api(f"releases/assets/{entry['id']}", "DELETE")
            report(f"Retired previous nightly asset: `{name}`")
    report(f"Confirmed latest nightly assets for `{target}`; other targets retained.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("select", "package", "prepare", "retire"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--tag", default="nightly")
    args = parser.parse_args()
    # The separator cannot occur inside a target, so prefix ownership is unambiguous.
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*", args.target):
        raise ValueError("Invalid release target")
    if args.operation == "select":
        select(args.target)
    elif args.operation == "package":
        package(args.target, args.directory)
    elif args.operation == "prepare":
        prepare(args.target, args.tag)
    else:
        retire(args.target, args.tag, args.directory)


if __name__ == "__main__":
    main()
