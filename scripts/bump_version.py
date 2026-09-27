#!/usr/bin/env python3
"""
Automated Version Management Script for WordLengthFilter.
Updates version.json, VERSION, filter_app.py, fastfilter.c, and CHANGELOG.md.
Optionally creates git commit and annotated tag.

Usage:
    python scripts/bump_version.py [patch|minor|major|<specific-version>] [--git] [--dry-run]
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_JSON = os.path.join(REPO_ROOT, "version.json")
VERSION_FILE = os.path.join(REPO_ROOT, "VERSION")
FILTER_APP_PY = os.path.join(REPO_ROOT, "filter_app.py")
FASTFILTER_C = os.path.join(REPO_ROOT, "fastfilter.c")
CHANGELOG_MD = os.path.join(REPO_ROOT, "CHANGELOG.md")


def load_current_version():
    if os.path.exists(VERSION_JSON):
        with open(VERSION_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    elif os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
            parts = [int(p) for p in v.split(".")]
            return {
                "version": v,
                "major": parts[0] if len(parts) > 0 else 1,
                "minor": parts[1] if len(parts) > 1 else 0,
                "patch": parts[2] if len(parts) > 2 else 0,
                "build": 1,
                "release_date": datetime.date.today().isoformat(),
            }
    return {
        "version": "1.0.0",
        "major": 1,
        "minor": 0,
        "patch": 0,
        "build": 1,
        "release_date": datetime.date.today().isoformat(),
    }


def compute_new_version(current_data, bump_type):
    major = current_data.get("major", 1)
    minor = current_data.get("minor", 0)
    patch = current_data.get("patch", 0)
    build = current_data.get("build", 0) + 1

    bump_lower = bump_type.lower()
    if bump_lower == "patch":
        patch += 1
    elif bump_lower == "minor":
        minor += 1
        patch = 0
    elif bump_lower == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        # Custom version string e.g. 1.2.3
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", bump_type.strip())
        if not match:
            print(f"[ERROR] Invalid bump type or version string: '{bump_type}'")
            print("Supported values: 'patch', 'minor', 'major', or 'X.Y.Z'")
            sys.exit(1)
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))

    new_version_str = f"{major}.{minor}.{patch}"
    today_str = datetime.date.today().isoformat()

    return {
        "version": new_version_str,
        "major": major,
        "minor": minor,
        "patch": patch,
        "build": build,
        "release_date": today_str,
    }


def update_version_json(data, dry_run=False):
    print(f"-> Updating version.json to v{data['version']} (build {data['build']})")
    if not dry_run:
        with open(VERSION_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def update_version_file(version_str, dry_run=False):
    print(f"-> Updating VERSION to {version_str}")
    if not dry_run:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(version_str + "\n")


def update_filter_app_py(version_str, dry_run=False):
    if not os.path.exists(FILTER_APP_PY):
        return
    print(f"-> Updating filter_app.py __version__ to '{version_str}'")
    with open(FILTER_APP_PY, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace or insert __version__
    if "__version__ = " in content:
        content = re.sub(
            r'__version__\s*=\s*["\'][^"\']+["\']',
            f'__version__ = "{version_str}"',
            content,
        )
    else:
        content = f'__version__ = "{version_str}"\n' + content

    if not dry_run:
        with open(FILTER_APP_PY, "w", encoding="utf-8") as f:
            f.write(content)


def update_fastfilter_c(version_str, dry_run=False):
    if not os.path.exists(FASTFILTER_C):
        return
    print(f"-> Updating fastfilter.c FASTFILTER_VERSION to '{version_str}'")
    with open(FASTFILTER_C, "r", encoding="utf-8") as f:
        content = f.read()

    if "#define FASTFILTER_VERSION" in content:
        content = re.sub(
            r'#define\s+FASTFILTER_VERSION\s+["\'][^"\']+["\']',
            f'#define FASTFILTER_VERSION "{version_str}"',
            content,
        )
    else:
        content = f'#define FASTFILTER_VERSION "{version_str}"\n' + content

    if not dry_run:
        with open(FASTFILTER_C, "w", encoding="utf-8") as f:
            f.write(content)


def update_changelog(version_str, today_str, dry_run=False):
    if not os.path.exists(CHANGELOG_MD):
        return
    print(f"-> Updating CHANGELOG.md with release section [{version_str}] - {today_str}")
    with open(CHANGELOG_MD, "r", encoding="utf-8") as f:
        content = f.read()

    target = "## [Unreleased]"
    replacement = f"## [Unreleased]\n\n## [{version_str}] - {today_str}"
    if target in content and f"## [{version_str}]" not in content:
        content = content.replace(target, replacement, 1)
        if not dry_run:
            with open(CHANGELOG_MD, "w", encoding="utf-8") as f:
                f.write(content)


def git_commit_and_tag(version_str, dry_run=False):
    tag = f"v{version_str}"
    commit_msg = f"chore(release): bump version to {tag}"
    print(f"-> Creating Git commit: '{commit_msg}'")
    print(f"-> Creating Git tag: '{tag}'")
    if dry_run:
        print("   [Dry Run] Skipping git commands.")
        return

    try:
        subprocess.run(["git", "add", "-A"], check=True, cwd=REPO_ROOT)
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=REPO_ROOT)
        subprocess.run(
            ["git", "tag", "-a", tag, "-m", f"Release {tag}"],
            check=True,
            cwd=REPO_ROOT,
        )
        print(f"[SUCCESS] Committed and tagged {tag} locally.")
        print(f"To push to remote: git push origin main --tags")
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Git commit/tag command failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Bump project version across all project files."
    )
    parser.add_argument(
        "bump",
        nargs="?",
        default="patch",
        help="Bump target: 'patch' (default), 'minor', 'major', or explicit 'X.Y.Z'",
    )
    parser.add_argument(
        "--git",
        "-g",
        action="store_true",
        help="Automatically create git commit and git tag",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Simulate updates without modifying files",
    )
    args = parser.parse_args()

    current_data = load_current_version()
    print(f"Current version: v{current_data['version']}")

    new_data = compute_new_version(current_data, args.bump)
    new_version_str = new_data["version"]
    print(f"New target version: v{new_version_str}")

    update_version_json(new_data, dry_run=args.dry_run)
    update_version_file(new_version_str, dry_run=args.dry_run)
    update_filter_app_py(new_version_str, dry_run=args.dry_run)
    update_fastfilter_c(new_version_str, dry_run=args.dry_run)
    update_changelog(new_version_str, new_data["release_date"], dry_run=args.dry_run)

    if args.git:
        git_commit_and_tag(new_version_str, dry_run=args.dry_run)

    print("\n=======================================================")
    print(f" Version bump to v{new_version_str} completed successfully! ")
    print("=======================================================")


if __name__ == "__main__":
    main()
