<#
.SYNOPSIS
    Fast Markdown Cache & Token Saver for Wordlist-Edit-Tool.

.DESCRIPTION
    Checks file size and modification timestamps of all repository .md files.
    Avoids re-reading full markdown files unless changes are detected.

.PARAMETER Action
    'check' (default, fast 1-line check), 'status' (summary table), 'update' (refresh cache).

.EXAMPLE
    .\scripts\md_cache.ps1
    .\scripts\md_cache.ps1 status
    .\scripts\md_cache.ps1 update
#>
[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [ValidateSet("check", "status", "update")]
    [string]$Action = "check"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "md_cache.py"

$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue).Source
}

if (-not $pythonCmd) {
    Write-Error "Python not found in system PATH."
    exit 1
}

& $pythonCmd $pythonScript $Action
