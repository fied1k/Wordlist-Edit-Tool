# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-09-27

### Added / Changed
- Add custom destination folder selector, WPA2 presets (8-63 and 8-16), and ASCII printable character rule


## [1.0.0] - 2026-09-27

### Added
- **Native C Engine (`fastfilter.c`)**: High-performance C core with 4 MB double-buffered file I/O for streaming gigabyte-scale wordlists.
- **Dynamic 64-Bit FNV-1a Hash Set**: Open-addressing linear probing hash set for deduplication with sub-millisecond lookup times and auto-resizing.
- **Standalone CLI Binary (`fastfilter.exe`)**: 95 KB zero-dependency native Windows executable with CLI flag support (`--version`, length bounds, character modes, line modes, and deduplication).
- **Windows Unicode Path Support**: Added `process_file_fast_w` using `_wfopen` for seamless handling of non-ASCII file paths and international directories.
- **Tkinter GUI Desktop App (`filter_app.py`)**: Modernized desktop interface with character length controls, charset radio buttons, custom regex input, and wordlist formatting options.
- **Non-Blocking Background Worker Threads**: GUI operations run in a daemon thread so the interface never freezes or enters a "(Not Responding)" state during heavy processing.
- **Streaming Python Fallback**: Integrated line-by-line low-memory fallback for custom regular expressions or systems without the C library.
- **Single-Click Build Script (`build.bat`)**: Automated compilation of both native C binaries and PyInstaller `--onefile` packaging.
- **Automated Versioning System**: Cross-platform Python (`scripts/bump_version.py`) and PowerShell (`scripts/bump_version.ps1`) scripts for managing version bumps across `version.json`, `VERSION`, `filter_app.py`, `fastfilter.c`, and `CHANGELOG.md`.
- **CI/CD Pipeline (`.github/workflows/build-and-release.yml`)**: Automated GitHub Actions workflow to build, verify, and attach standalone Windows `.exe` binaries to tagged GitHub releases.

### Changed
- Standardized character set validation:
  - `letters`: Excludes digits, punctuation, and symbols.
  - `alnum`: Excludes punctuation, allows alphanumeric characters.
  - `all`: Allows words with internal hyphens and apostrophes while trimming outer punctuation.

### Fixed
- Fixed an I/O buffer flush bug where output buffers freed before explicit `fflush()` caused small files to produce truncated or empty outputs.
- Eliminated high memory consumption in Python UI by replacing full file reads (`f.readlines()`) with streaming generators.
