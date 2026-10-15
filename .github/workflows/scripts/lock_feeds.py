#!/usr/bin/env python3
"""
Lock feed revisions in feeds.conf to exact Git commit hashes or upstream revisions.
Supports all feed types from OpenWrt scripts/feeds (%update_method):
  - src-git, src-git-full, src-gitsvn (Git commit hash via rev-parse HEAD)
  - src-svn (SVN revision number via svn info)
  - src-hg (Mercurial node/rev via hg id)
  - src-bzr (Bazaar revno via bzr revno)
  - src-link, src-cpy, src-dummy (local / dummy unpinned)

Primary strategy:
  Uses OpenWrt's native `./scripts/feeds list -s -f` if available,
  which is the built-in, official mechanism for exporting feeds with pinned revisions.
Fallback strategy:
  Parses feeds.conf and queries each feed's local VCS repository directly.
"""

import os
import sys
import subprocess

def get_feed_revision(feed_type, feed_dir):
    """Query revision for any feed type supported by OpenWrt."""
    if not os.path.isdir(feed_dir):
        return None

    # Git-based feeds (src-git, src-git-full, src-gitsvn)
    if feed_type in ("src-git", "src-git-full", "src-gitsvn"):
        if os.path.isdir(os.path.join(feed_dir, ".git")):
            try:
                res = subprocess.run(
                    ["git", "-C", feed_dir, "rev-parse", "HEAD"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return res.stdout.strip()
            except Exception:
                return None

    # Subversion feeds (src-svn)
    elif feed_type == "src-svn":
        if os.path.isdir(os.path.join(feed_dir, ".svn")):
            try:
                res = subprocess.run(
                    ["svn", "info"],
                    cwd=feed_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                for line in res.stdout.splitlines():
                    if line.startswith("Revision:"):
                        return line.split(":", 1)[1].strip()
            except Exception:
                return None

    # Mercurial feeds (src-hg)
    elif feed_type == "src-hg":
        if os.path.isdir(os.path.join(feed_dir, ".hg")):
            try:
                res = subprocess.run(
                    ["hg", "id", "-i"],
                    cwd=feed_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return res.stdout.strip()
            except Exception:
                return None

    # Bazaar feeds (src-bzr)
    elif feed_type == "src-bzr":
        if os.path.isdir(os.path.join(feed_dir, ".bzr")):
            try:
                res = subprocess.run(
                    ["bzr", "revno"],
                    cwd=feed_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return res.stdout.strip()
            except Exception:
                return None

    # Local file / symlink / dummy feeds
    elif feed_type in ("src-link", "src-cpy", "src-dummy"):
        return "local"

    return None

def lock_feeds_via_native_tool(output_path):
    """Attempt to use OpenWrt's native './scripts/feeds list -s -f'."""
    script_path = os.path.join(os.getcwd(), "scripts", "feeds")
    if os.path.isfile(script_path) and os.access(script_path, os.X_OK):
        try:
            res = subprocess.run(
                [script_path, "list", "-s", "-f"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            output = res.stdout.strip()
            if output:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(output + "\n")
                print(f"Locked all feeds via OpenWrt native './scripts/feeds list -s -f' into {output_path}")
                return True
        except Exception as e:
            print(f"Native ./scripts/feeds invocation failed: {e}, falling back to Python parser...", file=sys.stderr)
    return False

def lock_feeds_fallback(feeds_conf_path, output_path, feeds_dir="feeds"):
    """Parse feeds.conf and lock all feed types via Python fallback."""
    if not os.path.exists(feeds_conf_path):
        print(f"Error: {feeds_conf_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(feeds_conf_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    locked_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            locked_lines.append(line)
            continue

        parts = stripped.split()
        if len(parts) >= 3:
            feed_type = parts[0]
            feed_name = parts[1]
            feed_url = parts[2]

            target_dir = os.path.join(feeds_dir, feed_name)
            revision = get_feed_revision(feed_type, target_dir)

            # Strip existing revision or branch delimiter
            clean_url = feed_url.split("^")[0].split(";")[0]

            if revision and revision not in ("local", "dummy", "X"):
                locked_line = f"{feed_type} {feed_name} {clean_url}^{revision}\n"
                print(f"Locked feed '{feed_name}' ({feed_type}) -> {revision}")
                locked_lines.append(locked_line)
            else:
                locked_lines.append(line)
        else:
            locked_lines.append(line)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(locked_lines)

    print(f"Generated locked feeds file via fallback parser: {output_path}")

def lock_feeds(feeds_conf_path, output_path, feeds_dir="feeds"):
    # Try native OpenWrt list -s -f first
    if lock_feeds_via_native_tool(output_path):
        return
    # Fallback to python parser for all feed types
    lock_feeds_fallback(feeds_conf_path, output_path, feeds_dir)

if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else "feeds.conf"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "feeds.conf.locked"
    fdir = sys.argv[3] if len(sys.argv) > 3 else "feeds"
    lock_feeds(in_file, out_file, fdir)
