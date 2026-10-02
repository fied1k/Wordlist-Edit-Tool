#!/usr/bin/env python3
"""
scripts/md_cache.py - High-Efficiency Markdown Cache & Token Saver

Tracks file modification timestamps and sizes for all repository markdown files.
Allows instant verification (via os.stat) so AI agents, developers, and release scripts
never need to re-read full .md files (CHANGELOG.md, README.md, AGENTS.md, GEMINI.md)
unless their size or modification timestamp actually changed.

Usage:
    python scripts/md_cache.py check        # Fast check: prints 1-line cache hit/miss (Exit 0=hit, 1=miss)
    python scripts/md_cache.py status       # Compact summary table of all markdown files
    python scripts/md_cache.py update       # Force update of .md_cache.json
    python scripts/md_cache.py get <file>   # Extract specific file section or cached summary
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(REPO_ROOT, ".md_cache.json")

# Standard markdown files to track
TRACKED_MD_FILES = [
    "README.md",
    "CHANGELOG.md",
    "GEMINI.md",
    "AGENTS.md",
    os.path.join("releases", "README.md"),
]


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:16]


def extract_metadata(rel_path, abs_path):
    """Extract lightweight summary / key stats from markdown file without storing raw bulk."""
    meta = {}
    if not os.path.exists(abs_path):
        return meta

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip() for line in f]
    except Exception:
        return meta

    meta["line_count"] = len(lines)

    norm = rel_path.replace("\\", "/")
    if norm == "CHANGELOG.md":
        latest_ver = "Unknown"
        latest_date = ""
        notes = []
        capture = False
        for line in lines:
            m = re.match(r"^##\s+\[([0-9.]+)\](?:\s+-\s+([0-9-]+))?", line)
            if m:
                if not capture:
                    latest_ver = m.group(1)
                    latest_date = m.group(2) or ""
                    capture = True
                else:
                    break
            elif capture:
                if line.startswith("## ["):
                    break
                if line.strip():
                    notes.append(line.strip())
        meta["latest_version"] = latest_ver
        meta["latest_date"] = latest_date
        meta["latest_notes_summary"] = " | ".join(notes[:3])
        meta["summary"] = f"Release history through v{latest_ver} ({latest_date})."

    elif norm == "README.md":
        badge = ""
        for line in lines[:15]:
            m = re.search(r"version-v([0-9.]+)-blue", line)
            if m:
                badge = m.group(1)
                break
        meta["badge_version"] = badge
        meta["summary"] = f"Wordlist-Edit-Tool documentation & CLI/GUI guide (v{badge})."

    elif norm == "GEMINI.md":
        meta["summary"] = "Automation rules: Always formal release, auto SemVer, preserve changelog, local binary archival."

    elif norm == "AGENTS.md":
        meta["summary"] = "Agent architecture, build instructions, token efficiency rules, and conventions."

    elif norm == "releases/README.md":
        meta["summary"] = "Directory index for local standalone binary archives (v1.0.0 through v1.5.0+)."

    else:
        meta["summary"] = lines[0] if lines else "Markdown document"

    return meta


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": "1.0", "updated_at": "", "files": {}}


def save_cache(cache_data):
    cache_data["updated_at"] = datetime.datetime.now().isoformat()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)
        f.write("\n")


def scan_and_update(force=False):
    cache = load_cache()
    cached_files = cache.get("files", {})
    changes = []

    for rel in TRACKED_MD_FILES:
        abs_p = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(abs_p):
            continue

        stat = os.stat(abs_p)
        cur_size = stat.st_size
        cur_mtime = stat.st_mtime
        norm_key = rel.replace("\\", "/")

        entry = cached_files.get(norm_key)
        if not force and entry:
            if entry.get("size") == cur_size and abs(entry.get("mtime", 0) - cur_mtime) < 0.001:
                continue

        # File changed or not cached
        old_size = entry.get("size") if entry else None
        sha = compute_sha256(abs_p)
        meta = extract_metadata(rel, abs_p)
        mtime_str = datetime.datetime.fromtimestamp(cur_mtime).strftime("%Y-%m-%d %H:%M:%S")

        cached_files[norm_key] = {
            "rel_path": norm_key,
            "size": cur_size,
            "mtime": cur_mtime,
            "mtime_str": mtime_str,
            "sha256": sha,
            **meta,
        }
        changes.append((norm_key, old_size, cur_size))

    cache["files"] = cached_files
    if changes or force:
        save_cache(cache)
    return changes


def cmd_check():
    cache = load_cache()
    cached_files = cache.get("files", {})

    if not cached_files:
        changes = scan_and_update(force=True)
        print(f"[CACHE INITIALIZED] Indexed {len(changes)} markdown files into .md_cache.json")
        return 0

    misses = []
    for rel in TRACKED_MD_FILES:
        abs_p = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(abs_p):
            continue
        stat = os.stat(abs_p)
        norm_key = rel.replace("\\", "/")
        entry = cached_files.get(norm_key)
        if not entry:
            misses.append((norm_key, "New file"))
        elif entry.get("size") != stat.st_size or abs(entry.get("mtime", 0) - stat.st_mtime) >= 0.001:
            misses.append((norm_key, f"Modified (size: {entry.get('size')} -> {stat.st_size} bytes)"))

    if not misses:
        file_list = ", ".join(rel.replace("\\", "/") for rel in TRACKED_MD_FILES)
        print(f"[CACHE HIT] All {len(TRACKED_MD_FILES)} markdown files unchanged ({file_list}).")
        return 0
    else:
        print(f"[CACHE MISS] Changes detected in {len(misses)} file(s):")
        for f, reason in misses:
            print(f"  * {f}: {reason}")
        scan_and_update()
        print("  -> Updated .md_cache.json with latest metadata.")
        return 1


def cmd_status():
    scan_and_update()
    cache = load_cache()
    files = cache.get("files", {})

    print(f"\nMarkdown Cache Status (.md_cache.json) — Last Updated: {cache.get('updated_at', 'N/A')}")
    print("-" * 88)
    print(f"{'File':<20} {'Size':<10} {'Lines':<8} {'Last Modified':<20} {'Summary'}")
    print("-" * 88)
    for norm_key, info in files.items():
        sz = f"{info.get('size', 0):,} B"
        lines = str(info.get("line_count", "-"))
        mtime = info.get("mtime_str", "")[:19]
        summary = info.get("summary", "")
        if len(summary) > 40:
            summary = summary[:37] + "..."
        print(f"{norm_key:<20} {sz:<10} {lines:<8} {mtime:<20} {summary}")
    print("-" * 88)
    return 0


def cmd_get(rel_file, latest_only=False, head_n=0):
    norm_key = rel_file.replace("\\", "/")
    cache = load_cache()
    info = cache.get("files", {}).get(norm_key)

    if not info:
        scan_and_update()
        cache = load_cache()
        info = cache.get("files", {}).get(norm_key)

    if not info:
        print(f"[ERROR] File '{rel_file}' not found in markdown cache.")
        return 1

    if latest_only and norm_key == "CHANGELOG.md":
        print(f"Version: {info.get('latest_version')} ({info.get('latest_date')})")
        print(f"Notes: {info.get('latest_notes_summary')}")
        return 0

    abs_p = os.path.join(REPO_ROOT, norm_key)
    if not os.path.exists(abs_p):
        print(f"[ERROR] File '{abs_p}' not on disk.")
        return 1

    with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
        if head_n > 0:
            for _ in range(head_n):
                line = f.readline()
                if not line:
                    break
                print(line, end="")
        else:
            print(f.read())
    return 0


def main():
    parser = argparse.ArgumentParser(description="High-efficiency markdown cache and token saver.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("check", help="Fast check for changes using os.stat (Exit 0=hit, 1=miss)")
    subparsers.add_parser("status", help="Print compact summary table of all markdown files")
    subparsers.add_parser("update", help="Force update of .md_cache.json")

    get_p = subparsers.add_parser("get", help="Get cached summary or contents of a file")
    get_p.add_argument("file", help="Relative file path (e.g. CHANGELOG.md)")
    get_p.add_argument("--latest", action="store_true", help="For CHANGELOG.md, return latest version notes only")
    get_p.add_argument("--head", type=int, default=0, help="Print only first N lines")

    args = parser.parse_args()
    cmd = args.command or "check"

    if cmd == "check":
        sys.exit(cmd_check())
    elif cmd == "status":
        sys.exit(cmd_status())
    elif cmd == "update":
        scan_and_update(force=True)
        print("[SUCCESS] Markdown cache fully updated.")
    elif cmd == "get":
        sys.exit(cmd_get(args.file, args.latest, args.head))


if __name__ == "__main__":
    main()
