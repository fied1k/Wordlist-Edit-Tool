<#
.SYNOPSIS
    Bumps the project version, updates version metadata files, and optionally commits/tags in Git.

.DESCRIPTION
    Automates Semantic Versioning (SemVer) for Wordlist-Edit-Tool.
    Updates version.json, VERSION, filter_app.py, fastfilter.c, and CHANGELOG.md.

.PARAMETER Bump
    The bump type: 'patch' (default), 'minor', 'major', or a specific version like '1.2.0'.

.PARAMETER Commit
    Switch to automatically run git commit and git tag.

.PARAMETER Push
    Switch to automatically push commit and tags to origin main.

.EXAMPLE
    .\scripts\bump_version.ps1 patch
    .\scripts\bump_version.ps1 minor -Commit
    .\scripts\bump_version.ps1 -Bump "1.2.0" -Commit -Push
#>
[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [string]$Bump = "patch",

    [switch]$Commit,
    [switch]$Push
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $scriptDir "bump_version.py"

$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue).Source
}

if (-not $pythonCmd) {
    Write-Error "Python not found in PATH."
    exit 1
}

$argsList = @($pythonScript, $Bump)
if ($Commit) {
    $argsList += "--git"
}

Write-Host "Running automated version bump..." -ForegroundColor Cyan
& $pythonCmd $argsList

if ($LASTEXITCODE -eq 0 -and $Push) {
    Write-Host "Pushing main and tags to remote origin..." -ForegroundColor Green
    git -C $repoRoot push origin main --tags
}
