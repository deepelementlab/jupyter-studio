# JupyterLab editable install helper for Windows.
# Prerequisites: Python 3.10+, Git recommended. Use Node 20 from conda-forge to match CI:
#   conda install -c conda-forge "nodejs=20.*"

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$drive = (Resolve-Path $RepoRoot).Path.Substring(0, 2)
$vol = Get-Volume -DriveLetter $drive.TrimEnd(":")
if ($vol.FileSystem -eq "exFAT" -or $vol.FileSystem -eq "FAT32") {
    Write-Error @"
Current repo is on $($vol.FileSystem) ($drive). Yarn workspace installs require directory junctions/symlinks, which NTFS supports but exFAT/FAT32 do not.

Fix: clone or copy this repo to an NTFS path (e.g. %USERPROFILE%\source\jupyterlab or C:\dev\jupyterlab), then re-run:

  .\scripts\install-dev-windows.ps1
"@
}

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Warning "No .git directory found. Setting SKIP_INTEGRITY_CHECK=true (required for ensure-repo / integrity step)."
    $env:SKIP_INTEGRITY_CHECK = "true"
}

$nodeCmd = (Get-Command node -ErrorAction SilentlyContinue)?.Source
if ($nodeCmd) {
    $nv = (& node -v)
    Write-Host "Using Node at $nodeCmd ($nv)"
} else {
    Write-Error "node not found in PATH. Install Node 20+, e.g.: conda install -c conda-forge 'nodejs=20.*'"
}

Write-Host "Installing editable JupyterLab with dev+test extras..."
python -m pip install -U pip hatchling "jupyter-builder>=0.9"
python -m pip install -e ".[dev,test]"

Write-Host "Done. Verify with: jupyter lab --version"
