# Wordlist-Edit-Tool Guidelines & Automation Rules

## 1. Release & Versioning Policy
- **Formal Release**: Every completed iteration must be versioned, compiled, tagged, and published to GitHub.
- **Auto-Versioning (SemVer)**: Single source of truth is `version.json` and `VERSION`. Sync `__version__` in `filter_app.py`, `FASTFILTER_VERSION` in `fastfilter.c`, and `README.md` badges.
- **Changelog Preservation**: Add `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md`. Never delete or overwrite historical versions.
- **Local Binary Archival**: Archive compiled binaries locally in `releases/vX.Y.Z/`. Keep all past versions.
- **Publish Script**:
  ```powershell
  .\scripts\publish_release.ps1 [patch|minor|major] -Notes "Summary of changes"
  ```

## 2. Token & Context Efficiency Rules
- **Markdown Caching**: Do NOT scan full `.md` files (`CHANGELOG.md`, `README.md`, `AGENTS.md`) into context.
- **Cache Check First**: Run `python scripts/md_cache.py check` or check file size/mtime via `stat`. If unchanged, rely on cached metadata.
- **Changelog Slicing**: Inspect only top lines or run `python scripts/md_cache.py get CHANGELOG.md --latest`.
- **Targeted Code Viewing**: Always provide `StartLine` and `EndLine` when viewing files to conserve prompt tokens.
