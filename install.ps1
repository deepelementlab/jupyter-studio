# Copyright (c) Jupyter Studio AI.
# Distributed under the terms of the Modified BSD License.
#
# One-click installer & deployer for the jupyter-studio monorepo:
#
#   clawcode/              -> Python coder agent library (editable install)
#   jupyter_studio_ai/     -> jupyter-server extension wrapping clawcode (editable)
#   open-jupyter/
#     jupyterlab-main/     -> JupyterLab source tree with ai-coder packages
#     <root>               -> Electron desktop shell ("Open Jupyter")
#
# What the script does, in order:
#
#   1.  Check Python (>=3.12) and Node (>=20).
#   2.  Create / reuse a venv at c:\jupyter-studio\.venv .
#   3.  pip install -e clawcode .
#   4.  pip install -e jupyter_studio_ai .
#   5.  pip install -e "open-jupyter\jupyterlab-main[dev]" (gives us jlpm).
#   6.  jlpm install  +  jlpm run build:dev   (in jupyterlab-main).
#   7.  yarn (or npm) install  +  build      (in open-jupyter root).
#   8.  Pre-write %APPDATA%\open-jupyter\settings.json so the shell uses the
#       local JupyterLab source by default (the path you just built).
#   9.  Optionally launch the Electron shell.
#
# Anything that already exists is skipped; rerunning the script is idempotent
# and safe. Use the -Force* switches to redo specific steps.
#
# Usage:
#
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1               # full install
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1 -Start        # ... and launch
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1 -SkipShell    # backend only
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1 -Recreate     # nuke .venv first
#
# All switches:
#   -PythonExe   <path>   Python interpreter to seed the venv from (default: python)
#   -VenvPath    <path>   venv directory (default: $repo\.venv)
#   -Recreate             Delete & recreate the venv before installing
#   -SkipPython           Skip clawcode / jupyter_studio_ai / jupyterlab pip installs
#   -SkipJlpm             Skip jlpm install + build:dev
#   -SkipShell            Skip the Electron desktop shell build
#   -SkipSettingsWrite    Don't pre-write open-jupyter settings.json
#   -Start                Run `npm start` in open-jupyter at the end
#   -UseYarn              Prefer yarn over npm for the Electron shell (default: auto)
#   -Verbose              Echo each command line before running it

[CmdletBinding()]
param(
  [string]$PythonExe = "python",
  # Default left empty here on purpose: in Windows PowerShell 5.1 the
  # automatic variable `$PSScriptRoot` is occasionally not populated yet when
  # `param()` default expressions are evaluated (especially when the script is
  # invoked through `cmd.exe` -> `powershell.exe -File ...`), which would make
  # `Join-Path $PSScriptRoot ".venv"` throw "parameter Path is empty". We
  # resolve a robust default below, after the param block.
  [string]$VenvPath  = $null,
  [switch]$Recreate,
  [switch]$SkipPython,
  [switch]$SkipJlpm,
  [switch]$SkipShell,
  [switch]$SkipSettingsWrite,
  [switch]$Start,
  [switch]$UseYarn
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Resolve the repo root robustly. Multiple fallbacks, in priority order:
#   1) $PSScriptRoot (works on PS 3.0+ in script body)
#   2) $PSCommandPath -> parent directory
#   3) $MyInvocation.MyCommand.Definition / .Path -> parent
#   4) current working directory (last resort)
# ---------------------------------------------------------------------------
function Resolve-RepoRoot {
  if ($PSScriptRoot) { return $PSScriptRoot }
  if ($PSCommandPath) { return (Split-Path -Parent $PSCommandPath) }
  $inv = $MyInvocation.MyCommand
  if ($inv) {
    $p = $inv.Path
    if (-not $p) { $p = $inv.Definition }
    try {
      if ($p -and (Test-Path -LiteralPath $p -ErrorAction SilentlyContinue)) {
        return (Split-Path -Parent (Resolve-Path -LiteralPath $p))
      }
    } catch { }
  }
  return (Get-Location).Path
}

$Repo                  = Resolve-RepoRoot
if (-not $VenvPath) {
  $VenvPath = Join-Path $Repo ".venv"
}
$ClawCodeDir           = Join-Path $Repo "clawcode"
$JupyterStudioAiDir    = Join-Path $Repo "jupyter_studio_ai"
$OpenJupyterDir        = Join-Path $Repo "open-jupyter"
$JupyterLabMainDir     = Join-Path $OpenJupyterDir "jupyterlab-main"

function Banner([string]$Text) {
  Write-Host ""
  Write-Host ("=" * 72) -ForegroundColor DarkCyan
  Write-Host ">> $Text"            -ForegroundColor Cyan
  Write-Host ("=" * 72) -ForegroundColor DarkCyan
}

function Step([string]$Text) {
  Write-Host ""
  Write-Host "[step] $Text" -ForegroundColor Green
}

function Info([string]$Text) {
  Write-Host "       $Text" -ForegroundColor Gray
}

function Run {
  # NOTE: we use `PositionalBinding=$false` and rename the "rest" parameter to
  # `$ExeArgs` (instead of `$Args`, which collides with the automatic variable)
  # so that callers can pass switches like `-m`, `--legacy-peer-deps`, etc.
  # without PowerShell trying to bind them to other params (in particular
  # `-Cwd`, which previously absorbed `-m` and caused
  # "Set-Location : path '-m' not found").
  [CmdletBinding(PositionalBinding = $false)]
  param(
    [Parameter(Mandatory = $true, Position = 0)] [string]$ExeName,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$ExeArgs,
    [string]$Cwd = ""
  )
  if ($VerbosePreference -eq "Continue" -or $env:JUPYTER_STUDIO_VERBOSE) {
    Write-Host ("       $ ${ExeName} " + ($ExeArgs -join " ")) -ForegroundColor DarkGray
  }
  $pushed = $false
  try {
    if ($Cwd) { Push-Location -LiteralPath $Cwd; $pushed = $true }
    & $ExeName @ExeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed (${ExeName} exit=$LASTEXITCODE): $ExeName $($ExeArgs -join ' ')"
    }
  } finally {
    if ($pushed) { Pop-Location }
  }
}

function CommandExists([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# JupyterLab's editable install runs hatch-jupyter-builder, which transitively
# calls `npm run integrity` -> `node buildutils/lib/ensure-repo.js`. That
# script invokes `git ls-tree -r HEAD --name-only` to enumerate tracked files.
# Source checkouts that were not cloned via git (zip download, tarball, etc.)
# therefore make the editable pip install fail with
#   fatal: not a git repository (or any of the parent directories): .git
# This helper turns the JupyterLab source tree into a local git repo with a
# single seed commit, just enough for `ensure-repo.js` to succeed. The repo's
# own `.gitignore` already excludes node_modules / lib / build / dev_mode
# artifacts, so this stays cheap.
# Patch JupyterLab's buildutils so its `ensureBuildUtils` step doesn't EPERM
# on Windows. The function unconditionally calls `fs.symlinkSync` on Windows
# accounts that lack the SeCreateSymbolicLinkPrivilege; we wrap that call in
# try/catch + copyFileSync fallback. Idempotent: sentinel marker keeps us from
# re-patching on rerun. The patch is also applied directly to the file in
# this repo; this function is the safety net if you ever wipe and re-fetch
# jupyterlab-main.
function Update-EnsureRepoSymlinkPatch([string]$JupyterLabMain) {
  $files = @(
    @{ Path = (Join-Path $JupyterLabMain "buildutils\lib\ensure-repo.js")
       Find = @"
        try {
            fs.lstatSync(dest);
            fs.removeSync(dest);
        }
        catch (_a) {
            // no-op
        }
        fs.symlinkSync(src, dest, 'file');
        fs.chmodSync(dest, 0o777);
"@
       Replace = @"
        try {
            fs.lstatSync(dest);
            fs.removeSync(dest);
        }
        catch (_a) {
            // no-op
        }
        // OPEN_JUPYTER_INSTALLER_PATCH: Windows non-admin accounts cannot
        // create file symlinks (EPERM). Fall back to a regular file copy.
        try {
            fs.symlinkSync(src, dest, 'file');
            fs.chmodSync(dest, 0o777);
        }
        catch (_b) {
            fs.copyFileSync(src, dest);
            try {
                fs.chmodSync(dest, 0o777);
            }
            catch (_c) {
                // best effort
            }
        }
"@
    },
    @{ Path = (Join-Path $JupyterLabMain "buildutils\src\ensure-repo.ts")
       Find = @"
    try {
      fs.lstatSync(dest);
      fs.removeSync(dest);
    } catch {
      // no-op
    }
    fs.symlinkSync(src, dest, 'file');
    fs.chmodSync(dest, 0o777);
"@
       Replace = @"
    try {
      fs.lstatSync(dest);
      fs.removeSync(dest);
    } catch {
      // no-op
    }
    // OPEN_JUPYTER_INSTALLER_PATCH: Windows non-admin accounts cannot create
    // file symlinks (EPERM). Fall back to a regular file copy, which is
    // functionally equivalent for these tiny wrapper JS scripts under
    // buildutils/lib (they are invoked via ``node ...``, not exec).
    try {
      fs.symlinkSync(src, dest, 'file');
      fs.chmodSync(dest, 0o777);
    } catch (err) {
      fs.copyFileSync(src, dest);
      try {
        fs.chmodSync(dest, 0o777);
      } catch {
        // best effort
      }
    }
"@
    }
  )
  foreach ($entry in $files) {
    $p = $entry.Path
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $text = Get-Content -LiteralPath $p -Raw -Encoding UTF8
    if ($text -match "OPEN_JUPYTER_INSTALLER_PATCH") {
      Info ("Already patched: " + $p)
      continue
    }
    if ($text.IndexOf($entry.Find) -lt 0) {
      Info ("Patch anchor not found in " + $p + " (file may have changed upstream); skipping.")
      continue
    }
    $patched = $text.Replace($entry.Find, $entry.Replace)
    Set-Content -LiteralPath $p -Value $patched -Encoding UTF8 -NoNewline
    Info ("Patched: " + $p)
  }
}

function Initialize-JupyterLabGitRepo([string]$Path) {
  if (Test-Path (Join-Path $Path ".git")) {
    Info "JupyterLab source is already a git repo, skipping init."
    return
  }
  if (-not (CommandExists "git")) {
    throw @"
JupyterLab's editable install requires `git` on PATH (it shells out to
`git ls-tree HEAD --name-only` to enumerate tracked files). Install Git for
Windows (https://git-scm.com/download/win) and rerun the installer.
"@
  }
  Info "Seeding local git history in $Path (one-time)"
  $identity = @("-c", "user.email=installer@open-jupyter.local",
                "-c", "user.name=open-jupyter installer")
  Run "git" "init" "-q" -Cwd $Path
  $addArgs = @() + $identity + @("add", "-A")
  Run "git" @addArgs -Cwd $Path
  $commitArgs = @() + $identity + @("commit", "-q",
                                    "-m", "init (open-jupyter installer)",
                                    "--allow-empty")
  Run "git" @commitArgs -Cwd $Path
  Info "Done. (jupyterlab-main is now a local-only git repo; not pushed anywhere.)"
}

function CheckMinVersion([string]$Label, [string]$Have, [version]$Min) {
  try {
    $clean = ($Have -replace '[^\d\.]+', '').Trim('.')
    if (-not $clean) { return $false }
    return ([version]$clean) -ge $Min
  } catch {
    Write-Host "       Could not parse $Label version '$Have'; continuing." -ForegroundColor DarkYellow
    return $true
  }
}

# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------

Banner "jupyter-studio one-click installer"
Info  "Repo: $Repo"
Info  "Venv: $VenvPath"

Step "Checking host tools"

if (-not (CommandExists $PythonExe)) {
  throw "Python executable '$PythonExe' not found in PATH. Pass -PythonExe <full path>."
}
$pyver = & $PythonExe --version 2>&1
Info "Python : $pyver"
if (-not (CheckMinVersion "python" $pyver ([version]"3.12"))) {
  Write-Host "       WARNING: clawcode requires Python >= 3.12 (you have $pyver)." -ForegroundColor Yellow
}

if (-not (CommandExists "node")) {
  throw "Node.js not found in PATH. Install Node.js 20+ first (https://nodejs.org)."
}
$nodever = (node --version) -replace "^v",""
Info "Node   : v$nodever"
if (-not (CheckMinVersion "node" $nodever ([version]"20.0.0"))) {
  Write-Host "       WARNING: dev_mode rspack build needs Node >= 20 (you have v$nodever)." -ForegroundColor Yellow
}

$hasYarn = CommandExists "yarn"
$hasNpm  = CommandExists "npm"
if (-not $hasNpm -and -not $hasYarn) {
  throw "Neither yarn nor npm found in PATH; cannot build open-jupyter."
}
Info ("Yarn   : " + ($(if ($hasYarn) { yarn --version } else { '(not found)' })))
Info ("npm    : " + ($(if ($hasNpm)  { npm  --version } else { '(not found)' })))

# ---------------------------------------------------------------------------
# 1. Venv
# ---------------------------------------------------------------------------

Step "Preparing virtual environment"
if ($Recreate -and (Test-Path $VenvPath)) {
  Info "Removing existing venv: $VenvPath"
  Remove-Item -LiteralPath $VenvPath -Recurse -Force
}
if (-not (Test-Path $VenvPath)) {
  Info "Creating venv with $PythonExe -m venv $VenvPath"
  Run $PythonExe "-m" "venv" $VenvPath
} else {
  Info "Reusing existing venv at $VenvPath"
}

$VenvPython = if ($IsLinux -or $IsMacOS) {
  Join-Path $VenvPath "bin/python"
} else {
  Join-Path $VenvPath "Scripts\python.exe"
}
if (-not (Test-Path $VenvPython)) {
  throw "Failed to find venv Python at: $VenvPython"
}

$VenvScripts = Split-Path $VenvPython -Parent

Info "Upgrading pip / setuptools / wheel"
Run $VenvPython "-m" "pip" "install" "--upgrade" "pip" "setuptools" "wheel"

# ---------------------------------------------------------------------------
# 2. Python packages (editable installs)
# ---------------------------------------------------------------------------

if (-not $SkipPython) {
  Step "Installing clawcode (editable)"
  Run $VenvPython "-m" "pip" "install" "-e" $ClawCodeDir

  Step "Installing jupyter_studio_ai (editable)"
  Run $VenvPython "-m" "pip" "install" "-e" $JupyterStudioAiDir

  Step "Preparing JupyterLab source tree for editable install"
  Initialize-JupyterLabGitRepo $JupyterLabMainDir
  Update-EnsureRepoSymlinkPatch $JupyterLabMainDir

  Step "Installing JupyterLab from local source (editable + dev extras)"
  # The bracketed dev extra pulls jlpm, lerna, etc.
  $jlabSpec = "$JupyterLabMainDir[dev]"
  Run $VenvPython "-m" "pip" "install" "-e" $jlabSpec

  Step "Verifying clawcode + jupyterlab importability"
  Run $VenvPython "-c" "import clawcode, jupyter_studio_ai, jupyterlab; print('clawcode', clawcode.__version__ if hasattr(clawcode,'__version__') else 'ok'); print('jupyterlab', jupyterlab.__version__); print('jupyter_studio_ai', jupyter_studio_ai.__version__)"

  Info "Listing server extensions (should include jupyter_studio_ai)"
  # Best effort; not fatal if the binary path is unusual.
  $jupyterCli = Join-Path $VenvScripts "jupyter.exe"
  if (-not (Test-Path $jupyterCli)) {
    $jupyterCli = Join-Path $VenvScripts "jupyter"
  }
  if (Test-Path $jupyterCli) {
    try { Run $jupyterCli "server" "extension" "list" } catch { Info "(extension list failed; continuing)" }
  }
} else {
  Info "Skipping Python installs (-SkipPython)"
}

# ---------------------------------------------------------------------------
# 3. JupyterLab front-end (jlpm install + build:dev)
# ---------------------------------------------------------------------------

if (-not $SkipJlpm) {
  Step "Building JupyterLab dev_mode (jlpm install + build:dev)"
  $jlpm = Join-Path $VenvScripts "jlpm.exe"
  if (-not (Test-Path $jlpm)) { $jlpm = Join-Path $VenvScripts "jlpm" }
  if (-not (Test-Path $jlpm)) {
    throw "jlpm not found in venv (looked in $VenvScripts). Did the JupyterLab pip install succeed?"
  }
  Run $jlpm "install"                -Cwd $JupyterLabMainDir
  Run $jlpm "run" "build:packages"   -Cwd $JupyterLabMainDir
  Run $jlpm "run" "build:dev"        -Cwd $JupyterLabMainDir
  Info "OK: dev_mode/static/index.html should now exist."
} else {
  Info "Skipping JupyterLab dev_mode build (-SkipJlpm)"
}

# ---------------------------------------------------------------------------
# 4. Electron shell (open-jupyter)
# ---------------------------------------------------------------------------

if (-not $SkipShell) {
  Step "Installing open-jupyter shell dependencies"
  $useYarnHere = $UseYarn -and $hasYarn
  if ($useYarnHere) {
    Run "yarn" "install"             -Cwd $OpenJupyterDir
    Run "yarn" "build"               -Cwd $OpenJupyterDir
  } else {
    if (-not $hasNpm) { throw "npm is required (yarn unavailable). Install Node.js." }
    Run "npm" "install" "--legacy-peer-deps" -Cwd $OpenJupyterDir
    Run "npm" "run" "build"          -Cwd $OpenJupyterDir
  }
} else {
  Info "Skipping Electron shell build (-SkipShell)"
}

# ---------------------------------------------------------------------------
# 5. Pre-write open-jupyter settings.json so it auto-binds to our local source
# ---------------------------------------------------------------------------

if (-not $SkipSettingsWrite) {
  Step "Writing open-jupyter settings.json (local-dev defaults)"
  # On Windows this matches app.getPath('userData') for `appName = "open-jupyter"`
  $appDataDir = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE "AppData\Roaming" }
  $userDataDir = Join-Path $appDataDir "open-jupyter"
  if (-not (Test-Path $userDataDir)) {
    New-Item -ItemType Directory -Force -Path $userDataDir | Out-Null
  }
  $settingsPath = Join-Path $userDataDir "settings.json"

  $existing = @{}
  if (Test-Path $settingsPath) {
    try {
      $existing = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json -AsHashtable
      if ($null -eq $existing) { $existing = @{} }
    } catch {
      Info "Existing settings.json is unreadable; will be overwritten."
      $existing = @{}
    }
  }

  $existing["useLocalDevJupyterLab"]  = $true
  $existing["localJupyterLabPath"]    = $JupyterLabMainDir
  $existing["localJupyterLabPython"]  = $VenvPython
  $existing["localJupyterLabDevMode"] = $true

  ($existing | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $settingsPath -Encoding UTF8
  Info "Wrote $settingsPath"
} else {
  Info "Skipping settings.json write (-SkipSettingsWrite)"
}

# ---------------------------------------------------------------------------
# 6. Done. Optionally launch.
# ---------------------------------------------------------------------------

Banner "Installation complete"

@"
Next steps:

  * Configure your LLM API keys in clawcode settings if you haven't yet
    (env vars: ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY).

  * Activate the venv in any new shell to use jupyter / jlpm directly:
      $VenvScripts\Activate.ps1

  * Standalone Lab:
      jupyter lab --dev-mode --notebook-dir="$Repo"
    (run from inside the activated venv).

  * Desktop shell:
      cd "$OpenJupyterDir"; npm start
    The Local Dev settings have been pre-populated; the shell will auto-bind
    to the local JupyterLab source and fall back if anything goes wrong.

"@ | Write-Host

if ($Start) {
  Banner "Launching open-jupyter (npm start)"
  Set-Location $OpenJupyterDir
  if ($UseYarn -and $hasYarn) {
    yarn start
  } else {
    npm start
  }
}
