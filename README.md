# WordLengthFilter ⚡

[![Release](https://img.shields.io/badge/version-v1.2.0-blue.svg)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010%20(x64)-0078D6.svg?logo=windows)](#)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](#)
[![C Engine](https://img.shields.io/badge/Engine-Native%20C%20(GCC%2016)-00599C.svg?logo=c)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**WordLengthFilter** is a high-performance dictionary and wordlist filtering utility for Windows. Engineered for security engineers, penetration testers, and data researchers, it processes multi-gigabyte wordlists (such as RockYou or custom password dictionaries) in seconds with a minimal memory footprint.

It ships as both a **standalone desktop GUI** (`WordLengthFilter.exe`) and an **ultra-fast native C CLI** (`fastfilter.exe`).

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Presentation ["Presentation Layer"]
        GUI["WordLengthFilter GUI\n(Tkinter / Python 3.14)"]
        CLI["fastfilter.exe\n(Native C CLI)"]
    end

    subgraph Coordination ["Coordination & Fallback"]
        WORKER["Background Worker Thread\n(Non-blocking UI)"]
        PY_STREAM["Python Streaming Engine\n(Custom Regex Fallback)"]
    end

    subgraph Engine ["Native C Acceleration Core (fastfilter.dll)"]
        BUF_IN["4 MB Double-Buffered\nFile Stream Input"]
        TOKENIZER["Fast Tokenizer & Delimiter\nStrip Leading/Trailing Symbols"]
        RULE_ENGINE["Character Rule Validator\n(Letters / Alnum / ASCII Printable / Standard)"]
        HASHSET["64-bit FNV-1a Hash Set\n(Exact / Lower Deduplication)"]
        ROLLOVER["Output Writer & Chunk Rollover\n(Split by Lines or MB on-the-fly)"]
        BUF_OUT["4 MB Buffered Output\n(_part1, _part2... or Single File)"]
    end

    GUI -->|Worker Thread| WORKER
    WORKER -->|Native Rules| Engine
    WORKER -->|Custom Regex| PY_STREAM
    CLI -->|Direct Native Call| Engine

    BUF_IN --> TOKENIZER
    TOKENIZER --> RULE_ENGINE
    RULE_ENGINE --> HASHSET
    HASHSET --> ROLLOVER
    ROLLOVER --> BUF_OUT
```

---

## Key Features

- **⚡ Blazing Fast Native C Engine**: Uses 4 MB buffered disk I/O to stream files continuously without loading entire wordlists into memory.
- **💾 Low Memory Footprint**: Filters 50M+ line wordlists using only ~8–64 MB of RAM (compared to 8–16 GB in pure Python).
- **🖥️ Non-Blocking Windows GUI**: Operations run on background worker threads—the UI remains smooth and responsive without freezing.
- **📁 Destination Folder Selector**: Custom destination directory chooser with automatic fallback to the source file directory.
- **✂️ Output Splitting & Chunk Rollover**: Divide massive dictionaries into manageable parts (e.g. 5,000,000 words or 1,024 MB per part) on-the-fly **without breaking global deduplication** or doubling disk I/O.
- **⚡ Built-in Wi-Fi / Security Presets**:
  - **WPA2 Standard (8-63 chars, ASCII Printable)**: Filters strictly to valid IEEE 802.11i Wi-Fi passphrases.
  - **WPA2 Typical (8-16 chars, ASCII Printable)**: High-probability search range for standard consumer routers.
  - **Alphanumeric (8-16 chars)**: Common password policies omitting punctuation.
  - **Letters Only (4-12 chars)**: Dictionary word lists.
- **🔍 64-bit FNV-1a Deduplication**: Dynamic open-addressing hash set eliminates duplicates at line rate (exact case-sensitive for WPA2, case-insensitive for words).
- **🎯 Flexible Character Set Rules**:
  - **Any characters**: Standard wordlist tokens with hyphens and apostrophes (trims exterior delimiters).
  - **Letters only**: Pure alphabetic words (excludes numbers, punctuation, and symbols).
  - **Alphanumeric only**: Letters and numbers, omitting punctuation.
  - **ASCII printable only (32-126)**: Preserves all ASCII symbols and punctuation (ideal for WPA2 keys/passwords).
  - **Custom Regex**: User-defined regular expressions (via streaming Python engine).
- **📂 Output Formats**: Choose between standard wordlist format (one word per line) or preserving line structures.
- **📦 Zero-Dependency Standalone Binaries**: Single-file executables that run out-of-the-box on Windows 10/11 without requiring Python or runtime installations.

---

## Binaries

| Binary | Type | Description |
| :--- | :--- | :--- |
| **`dist/WordLengthFilter.exe`** | Standalone GUI | Full desktop UI bundled with Tkinter and the embedded C acceleration engine. |
| **`dist/fastfilter.exe`** | Standalone CLI | Lightweight (~95 KB) zero-dependency native C command-line tool. |

---

## CLI Usage (`fastfilter.exe`)

```
fastfilter.exe <source_file> <output_file> [min_len] [max_len] [charset_mode] [output_mode] [dedup] [split_lines] [split_bytes]
```

### Parameters

| Argument | Type | Default | Options |
| :--- | :--- | :--- | :--- |
| `<source_file>` | Required | — | Path to source text or wordlist file |
| `<output_file>` | Required | — | Path where the filtered file will be saved |
| `[min_len]` | Optional | `3` | Minimum word character length |
| `[max_len]` | Optional | `12` | Maximum word character length |
| `[charset_mode]`| Optional | `0` | `0` = All words, `1` = Letters only, `2` = Alphanumeric only, `3` = ASCII printable only (32-126, WPA2) |
| `[output_mode]` | Optional | `0` | `0` = One word per line, `1` = Preserve line structure |
| `[dedup]` | Optional | `0` | `0` = Keep duplicates, `1` = Unique words only |
| `[split_lines]` | Optional | `0` | Max words/lines per output file part (`0` = disabled) |
| `[split_bytes]` | Optional | `0` | Max bytes per output file part, e.g. `1073741824` = 1 GB (`0` = disabled) |

### Practical Examples

```powershell
# 1. Filter a dictionary for strict WPA2-PSK passphrases (8-63 characters, ASCII printable, deduplicated)
.\dist\fastfilter.exe rockyou.txt wpa2_candidates.txt 8 63 3 0 1

# 2. Filter typical WPA2 passphrases (8-16 characters, ASCII printable)
.\dist\fastfilter.exe rockyou.txt wpa2_typical.txt 8 16 3 0 1

# 3. Filter massive 50 GB wordlist and split into 10,000,000-word parts with global deduplication
.\dist\fastfilter.exe huge_dump.txt filtered.txt 8 20 0 0 1 10000000 0

# 4. Filter alphanumeric passwords (exclude punctuation) of length 6 to 16
.\dist\fastfilter.exe passwords.txt alnum_passwords.txt 6 16 2 0 0
```

---

## Building from Source

### Prerequisites
- Python 3.10+ (with `tkinter` included in standard Windows installer)
- GCC Compiler (included in the bundled `w64devkit/` or any MinGW in PATH)
- PyInstaller: `pip install pyinstaller`

### Single-Click Build
Run the automated build script:
```powershell
.\build.bat
```
This automatically compiles:
1. `fastfilter.dll` (optimized `-O3` shared library)
2. `dist\fastfilter.exe` (standalone CLI binary)
3. `dist\WordLengthFilter.exe` (PyInstaller single-file bundle)

---

## Automated Versioning & Releases

This repository includes automated Semantic Versioning (SemVer) tooling:

### Bumping the Version
Use the automated release script:
```powershell
# Publish patch iteration (e.g. 1.2.0 -> 1.2.1)
python scripts/publish_release.py patch --notes "Performance tweaks"

# Publish minor iteration (e.g. 1.2.0 -> 1.3.0)
python scripts/publish_release.py minor --notes "Added new filter presets"

# Publish major release (e.g. 1.2.0 -> 2.0.0)
python scripts/publish_release.py major --notes "Major architecture overhaul"
```

---

## License

This project is licensed under the [MIT License](LICENSE).
