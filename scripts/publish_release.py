#!/usr/bin/env python3
"""
Automated Iteration & Release Publisher for WordLengthFilter.

Performs complete end-to-end iteration release:
1. Calculates new Semantic Version (patch/minor/major/custom).
2. Updates version.json, VERSION, filter_app.py, fastfilter.c, and README.md.
3. Appends new version entry to CHANGELOG.md while preserving all past version history.
4. Compiles native C DLL (fastfilter.dll), CLI (dist/fastfilter.exe), and GUI (dist/WordLengthFilter.exe).
5. Stores archived copy of binaries in releases/v<version>/ for permanent local history.
6. Commits changes to Git and creates annotated tag v<version>.
7. Pushes main and tags to GitHub.
8. Creates GitHub Release and attaches compiled standalone executables.

Usage:
    python scripts/publish_release.py [patch|minor|major|<version>] [--notes "Release notes"]
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_JSON = os.path.join(REPO_ROOT, "version.json")
VERSION_FILE = os.path.join(REPO_ROOT, "VERSION")
FILTER_APP_PY = os.path.join(REPO_ROOT, "filter_app.py")
FASTFILTER_C = os.path.join(REPO_ROOT, "fastfilter.c")
FASTFILTER_DLL = os.path.join(REPO_ROOT, "fastfilter.dll")
CHANGELOG_MD = os.path.join(REPO_ROOT, "CHANGELOG.md")
README_MD = os.path.join(REPO_ROOT, "README.md")
SPEC_FILE = os.path.join(REPO_ROOT, "WordLengthFilter.spec")
DIST_DIR = os.path.join(REPO_ROOT, "dist")
RELEASES_DIR = os.path.join(REPO_ROOT, "releases")
W64DEVKIT_GCC = os.path.join(REPO_ROOT, "w64devkit", "bin", "gcc.exe")


def run_cmd(cmd, cwd=REPO_ROOT, check=True):
    print(f"  [EXEC] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"[ERROR] Command failed with return code {res.returncode}")
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        sys.exit(res.returncode)
    return res


def load_current_version():
    if os.path.exists(VERSION_JSON):
        with open(VERSION_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "version": "1.0.0",
        "major": 1,
        "minor": 0,
        "patch": 0,
        "build": 1,
        "release_date": datetime.date.today().isoformat(),
    }


def compute_next_version(current, bump_type):
    major = current.get("major", 1)
    minor = current.get("minor", 0)
    patch = current.get("patch", 0)
    build = current.get("build", 0) + 1

    b = bump_type.lower()
    if b == "patch":
        patch += 1
    elif b == "minor":
        minor += 1
        patch = 0
    elif b == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", bump_type.strip())
        if not m:
            print(f"[ERROR] Invalid version specification: {bump_type}")
            sys.exit(1)
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))

    new_v = f"{major}.{minor}.{patch}"
    return {
        "version": new_v,
        "major": major,
        "minor": minor,
        "patch": patch,
        "build": build,
        "release_date": datetime.date.today().isoformat(),
    }


def update_code_and_metadata(new_data, notes=""):
    v_str = new_data["version"]
    rel_date = new_data["release_date"]

    print(f"\n[1/6] Updating version metadata to v{v_str}...")
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2)
        f.write("\n")

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(v_str + "\n")

    # Update filter_app.py
    if os.path.exists(FILTER_APP_PY):
        with open(FILTER_APP_PY, "r", encoding="utf-8") as f:
            app_code = f.read()
        app_code = re.sub(r'__version__\s*=\s*["\'][^"\']+["\']', f'__version__ = "{v_str}"', app_code)
        with open(FILTER_APP_PY, "w", encoding="utf-8") as f:
            f.write(app_code)

    # Update fastfilter.c
    if os.path.exists(FASTFILTER_C):
        with open(FASTFILTER_C, "r", encoding="utf-8") as f:
            c_code = f.read()
        c_code = re.sub(r'#define\s+FASTFILTER_VERSION\s+["\'][^"\']+["\']', f'#define FASTFILTER_VERSION "{v_str}"', c_code)
        with open(FASTFILTER_C, "w", encoding="utf-8") as f:
            f.write(c_code)

    # Update README.md badge
    if os.path.exists(README_MD):
        with open(README_MD, "r", encoding="utf-8") as f:
            readme_text = f.read()
        readme_text = re.sub(r'version-v[0-9.]+-blue\.svg', f'version-v{v_str}-blue.svg', readme_text)
        with open(README_MD, "w", encoding="utf-8") as f:
            f.write(readme_text)

    # Update CHANGELOG.md (preserve all previous version history!)
    if os.path.exists(CHANGELOG_MD):
        with open(CHANGELOG_MD, "r", encoding="utf-8") as f:
            changelog_text = f.read()

        if f"## [{v_str}]" not in changelog_text:
            notes_section = f"\n### Added / Changed\n- {notes}\n" if notes else "\n### Changed\n- General performance improvements and updates.\n"
            new_entry = f"## [Unreleased]\n\n## [{v_str}] - {rel_date}\n{notes_section}"
            changelog_text = changelog_text.replace("## [Unreleased]", new_entry, 1)
            with open(CHANGELOG_MD, "w", encoding="utf-8") as f:
                f.write(changelog_text)


def compile_binaries():
    print("\n[2/6] Compiling native C acceleration engine...")
    gcc_cmd = W64DEVKIT_GCC if os.path.exists(W64DEVKIT_GCC) else "gcc"

    os.makedirs(DIST_DIR, exist_ok=True)

    # Compile fastfilter.dll
    run_cmd([gcc_cmd, "-O3", "-shared", "-o", FASTFILTER_DLL, FASTFILTER_C])

    # Compile standalone fastfilter.exe CLI
    cli_out = os.path.join(DIST_DIR, "fastfilter.exe")
    run_cmd([gcc_cmd, "-O3", "-DBUILD_CLI", "-o", cli_out, FASTFILTER_C])

    print("\n[3/6] Packaging standalone GUI executable with PyInstaller...")
    run_cmd(["python", "-m", "PyInstaller", "--clean", "-y", SPEC_FILE])


def archive_version_locally(version_str):
    print(f"\n[4/6] Archiving v{version_str} binaries locally in releases/v{version_str}/...")
    archive_dir = os.path.join(RELEASES_DIR, f"v{version_str}")
    os.makedirs(archive_dir, exist_ok=True)

    gui_src = os.path.join(DIST_DIR, "WordLengthFilter.exe")
    cli_src = os.path.join(DIST_DIR, "fastfilter.exe")

    if os.path.exists(gui_src):
        shutil.copy2(gui_src, os.path.join(archive_dir, "WordLengthFilter.exe"))
    if os.path.exists(cli_src):
        shutil.copy2(cli_src, os.path.join(archive_dir, "fastfilter.exe"))

    print(f"  -> Successfully archived v{version_str} binaries to {archive_dir}")


def git_commit_tag_and_push(version_str, notes=""):
    tag = f"v{version_str}"
    commit_msg = f"chore(release): release {tag}"
    if notes:
        commit_msg += f" - {notes}"

    print(f"\n[5/6] Committing changes and creating Git tag {tag}...")
    run_cmd(["git", "add", "version.json", "VERSION", "filter_app.py", "fastfilter.c", "fastfilter.dll", "README.md", "CHANGELOG.md"])
    run_cmd(["git", "commit", "-m", commit_msg])
    run_cmd(["git", "tag", "-a", tag, "-m", f"Release {tag}"])

    print("  -> Pushing main branch and tags to GitHub...")
    run_cmd(["git", "push", "origin", "main", "--tags"])


def publish_github_release(version_str, notes=""):
    tag = f"v{version_str}"
    print(f"\n[6/6] Publishing release {tag} on GitHub with attached standalone binaries...")
    archive_dir = os.path.join(RELEASES_DIR, tag)
    gui_bin = os.path.join(archive_dir, "WordLengthFilter.exe")
    cli_bin = os.path.join(archive_dir, "fastfilter.exe")

    # Extract notes for this version from CHANGELOG.md
    release_notes = notes
    if os.path.exists(CHANGELOG_MD):
        with open(CHANGELOG_MD, "r", encoding="utf-8") as f:
            lines = f.readlines()
        capture = False
        captured_lines = []
        for line in lines:
            if line.startswith(f"## [{version_str}]"):
                capture = True
                continue
            elif capture and line.startswith("## ["):
                break
            elif capture:
                captured_lines.append(line)
        if captured_lines:
            release_notes = "".join(captured_lines).strip()

    gh_cmd = [
        "gh", "release", "create", tag,
        gui_bin, cli_bin,
        "--title", f"WordLengthFilter {tag}",
        "--notes", release_notes or f"Release {tag}"
    ]
    res = run_cmd(gh_cmd, check=False)
    if res.returncode == 0:
        print(f"\n[SUCCESS] GitHub Release {tag} published successfully!")
        print(f"URL: https://github.com/fied1k/WordLengthFilter/releases/tag/{tag}")
    else:
        print(f"[WARNING] gh release create returned: {res.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Build, archive, and publish iteration release to GitHub.")
    parser.add_argument("bump", nargs="?", default="patch", help="Version bump: 'patch' (default), 'minor', 'major', or explicit 'X.Y.Z'")
    parser.add_argument("--notes", "-n", default="", help="Description of changes for changelog and release notes")
    args = parser.parse_args()

    current_data = load_current_version()
    new_data = compute_next_version(current_data, args.bump)
    new_v = new_data["version"]

    print("=================================================================")
    print(f" WordLengthFilter Iteration Release Pipeline: v{current_data['version']} -> v{new_v} ")
    print("=================================================================")

    update_code_and_metadata(new_data, args.notes)
    compile_binaries()
    archive_version_locally(new_v)
    git_commit_tag_and_push(new_v, args.notes)
    publish_github_release(new_v, args.notes)

    print("\n=================================================================")
    print(f" Iteration v{new_v} has been compiled, archived, and released! ")
    print(f" - Local Archive: releases/v{new_v}/")
    print(f" - GitHub Release: https://github.com/fied1k/WordLengthFilter/releases/tag/v{new_v}")
    print("=================================================================")


if __name__ == "__main__":
    main()
