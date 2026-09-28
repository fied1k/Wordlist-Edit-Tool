# Wordlist-Edit-Tool Project Guidelines & Automation Rules

## 1. Iteration & Release Policy
Whenever modifications, features, optimizations, or bug fixes are made to this codebase:
1. **Always Publish as a Formal Release**:
   - Every completed iteration must be versioned, compiled, tagged, and published as a GitHub Release.
2. **Auto-Versioning (Semantic Versioning)**:
   - Increments must follow SemVer (`major`, `minor`, or `patch`).
   - Single source of truth is [`version.json`](./version.json) and [`VERSION`](./VERSION).
   - Sync `__version__` in [`filter_app.py`](./filter_app.py) and `FASTFILTER_VERSION` in [`fastfilter.c`](./fastfilter.c).
   - Update version badges in [`README.md`](./README.md).
3. **Preserve Version History in CHANGELOG.md**:
   - Document all changes under `## [X.Y.Z] - YYYY-MM-DD`.
   - **Never overwrite or delete previous version sections** in [`CHANGELOG.md`](./CHANGELOG.md). All past iteration logs must remain permanently stored.
4. **Local Binary Archival (Keep Old Versions Stored)**:
   - Archive each version's compiled binaries into [`releases/vX.Y.Z/`](./releases/).
   - Keep all historical binaries stored locally (`releases/v1.0.0/`, `releases/v1.0.1/`, etc.) alongside the cloud GitHub Releases.
5. **Release Publishing**:
   - Use the automated release script:
     ```powershell
     .\scripts\publish_release.ps1 [patch|minor|major] -Notes "Summary of iteration changes"
     ```
   - This script automatically updates version metadata, compiles native and GUI binaries, archives them locally in `releases/vX.Y.Z/`, commits, tags, pushes, and creates the GitHub Release with attached standalone binaries.
