@echo off
setlocal
cd /d "%~dp0"
if exist "wubuGO.exe" (
  start "wubuGO" "%~dp0wubuGO.exe"
  exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m launcher.app
) else (
  python -m launcher.app
)
if errorlevel 1 (
  echo Source checkout needs Python 3.10+ with Tcl/Tk. Release installers bundle it.
  pause
  exit /b 1
)
