@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-wubuGO.ps1"
if errorlevel 1 (
 echo.
 echo The installer did not finish. Check that this ZIP was fully extracted.
 pause
)
