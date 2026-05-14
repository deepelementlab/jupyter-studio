@echo off
rem One-click launcher for non-PowerShell users.
rem Right-click -> Run, or double-click in Explorer.
rem
rem Forward any extra args (e.g. -Start, -Recreate, -SkipShell).

setlocal
set "SCRIPT_DIR=%~dp0"
rem cd into the script's directory so $PSScriptRoot/Get-Location fall-backs in
rem the .ps1 always resolve to this folder even when launched by double-click.
cd /d "%SCRIPT_DIR%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Install failed with exit code %ERRORLEVEL%.
  pause
  exit /b %ERRORLEVEL%
)

echo.
echo Installation finished successfully.
pause
