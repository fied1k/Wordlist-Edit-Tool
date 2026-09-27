<#
.SYNOPSIS
    Compiles, archives, tags, and publishes a new iteration release to GitHub.

.DESCRIPTION
    Automates the full iteration release lifecycle:
    1. Bumps semantic version in version.json, VERSION, filter_app.py, fastfilter.c, and README.md.
    2. Updates CHANGELOG.md with release notes while keeping all previous versions archived.
    3. Compiles fastfilter.dll, dist\fastfilter.exe, and dist\WordLengthFilter.exe.
    4. Copies and preserves the versioned binaries in releases\vX.Y.Z\.
    5. Commits to Git, tags vX.Y.Z, and pushes to remote GitHub repository.
    6. Publishes a GitHub Release with WordLengthFilter.exe and fastfilter.exe attached.

.PARAMETER Bump
    The version bump: 'patch' (default), 'minor', 'major', or specific version (e.g. '1.1.0').

.PARAMETER Notes
    Summary notes of what changed in this iteration.

.EXAMPLE
    .\scripts\publish_release.ps1
    .\scripts\publish_release.ps1 patch -Notes "Fixed buffer flush on small files"
    .\scripts\publish_release.ps1 minor -Notes "Added custom charset regex presets"
#>
[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [string]$Bump = "patch",

    [Parameter(Position = 1)]
    [string]$Notes = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "publish_release.py"

$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue).Source
}

if (-not $pythonCmd) {
    Write-Error "Python not found in system PATH."
    exit 1
}

$argsList = @($pythonScript, $Bump)
if ($Notes) {
    $argsList += @("--notes", $Notes)
}

& $pythonCmd $argsList
