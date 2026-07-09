@echo off
chcp 65001 >nul
title Job Radar - Start
set "JOB_RADAR_ROOT=%~dp0"

echo.
echo ==================================================
echo   Job Radar - Start
echo   Backend + built frontend on http://127.0.0.1:8765
echo ==================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=(Get-Item -LiteralPath $env:JOB_RADAR_ROOT).FullName;" ^
  "$launcher=Join-Path $root 'launcher.py';" ^
  "$py=$null;" ^
  "$cmd=Get-Command python -ErrorAction SilentlyContinue; if ($cmd) { $py=$cmd.Source };" ^
  "if (-not $py) { foreach ($candidate in @('D:\Anaconda\envs\UI\python.exe','D:\Anaconda\python.exe')) { if (Test-Path -LiteralPath $candidate) { $py=$candidate; break } } };" ^
  "if (-not $py) { Write-Host 'Python not found. Please install Python or update launcher settings.' -ForegroundColor Red; exit 1 };" ^
  "& $py $launcher start;" ^
  "exit $LASTEXITCODE"

echo.
echo --------------------------------------------------
echo   Press any key to close this window...
pause >nul
