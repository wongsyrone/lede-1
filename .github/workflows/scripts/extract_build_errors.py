#!/usr/bin/env python3
"""
Accurate OpenWrt Build Error Extractor for GitHub Actions.
Extracts genuine compilation failures, image size overflows, patch errors,
and hash mismatches while ignoring harmless autoconf / gnulib noise.
"""

import argparse
import os
import re
import sys

FATAL_PATTERNS = [
    re.compile(r"WARNING: Image file .* is too big: \d+ > \d+"),
    re.compile(r"ERROR: (?:package|target|toolchain|tools)/.* failed to build"),
    re.compile(r"Patch failed! .*"),
    re.compile(r"Hash mismatch for file .*"),
    re.compile(r"make\[\d+\]: \*\*\* .* Error \d+"),
    re.compile(r"recipe for target .* failed"),
]

def analyze_build(log_file, logs_dir, target):
    summary = []
    summary.append(f"### ❌ Build Failure Summary: `{target}`\n")

    primary_causes = []
    log_content_lines = []
    if log_file and os.path.isfile(log_file):
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            log_content_lines = f.readlines()

        for line in log_content_lines:
            for pat in FATAL_PATTERNS:
                if pat.search(line):
                    clean_l = line.strip()
                    if clean_l and clean_l not in primary_causes and not clean_l.startswith("time:"):
                        primary_causes.append(clean_l)

    if primary_causes:
        summary.append("> [!CAUTION]")
        summary.append("> **Identified Root Causes:**")
        filtered_causes = []
        for c in primary_causes:
            if "flock" in c and "scripts/download.pl" in c:
                continue
            filtered_causes.append(c)

        for cause in filtered_causes[-10:]:
            summary.append(f"> - `{cause}`")
        summary.append("")

    failed_logs = []
    if logs_dir and os.path.isdir(logs_dir):
        for root, _, files in os.walk(logs_dir):
            for file in sorted(files):
                if file.endswith(".txt"):
                    path = os.path.join(root, file)
                    rel_path = os.path.relpath(path, logs_dir)
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as lf:
                            content = lf.read()
                            lines = content.strip().splitlines()
                            last_chunk = "\n".join(lines[-25:])
                            if any(k in last_chunk for k in ["Error ", "Error 1", "Error 2", "FAILED", "Patch failed", "Hash mismatch", "fatal error:"]):
                                if "Nothing to be done" not in last_chunk and "Leaving directory" not in last_chunk[-120:]:
                                    failed_logs.append((rel_path, last_chunk))
                    except Exception:
                        pass

    if failed_logs:
        summary.append("#### 📦 Failed Component Logs (`logs/`):\n")
        for rel_path, snippet in failed_logs[:5]:
            summary.append(f"<details open><summary><b>Log: <code>{rel_path}</code></b></summary>\n")
            summary.append("```text")
            summary.append(snippet)
            summary.append("```\n</details>\n")

    if not primary_causes and not failed_logs and log_content_lines:
        summary.append("#### 📜 Tail of Compilation Log:\n")
        summary.append("```text")
        summary.extend([l.rstrip() for l in log_content_lines[-40:]])
        summary.append("```\n")

    return "\n".join(summary)

def main():
    parser = argparse.ArgumentParser(description="Extract accurate OpenWrt build failures")
    parser.add_argument("--target", required=True, help="Build target name")
    parser.add_argument("--log", default="compile.log", help="Path to compile.log")
    parser.add_argument("--logs-dir", default="logs", help="Path to logs/ directory")
    parser.add_argument("--summary", default="", help="Path to GITHUB_STEP_SUMMARY")
    parser.add_argument("--output", default="", help="Optional output markdown file")
    args = parser.parse_args()

    report = analyze_build(args.log, args.logs_dir, args.target)

    # Print to stdout for runner console logs
    print(report)

    # Append to GITHUB_STEP_SUMMARY if available
    summary_path = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and os.path.exists(os.path.dirname(summary_path) or "."):
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(report + "\n")
        except Exception as e:
            print(f"Warning: Failed to write to {summary_path}: {e}", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report + "\n")

if __name__ == "__main__":
    main()
