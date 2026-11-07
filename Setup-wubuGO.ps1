# Compatibility entry point. Release setup is the compiled Inno installer;
# source archives intentionally do not claim to contain a Python runtime.
$ErrorActionPreference = 'Stop'
$Installer = Join-Path $PSScriptRoot 'dist\wubuGO-6.0.0-windows-x64-setup.exe'
if (Test-Path -LiteralPath $Installer) {
    Start-Process -FilePath $Installer -Wait
    exit 0
}
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    "This is the source package, not the bundled Windows installer.`n`nUse the compiled wubuGO-6.0.0-windows-x64-setup.exe release for offline setup with Python included.`n`nTo build it on Windows, follow packaging\README.md. To run the source, install Python 3.10+ with Tcl/Tk and use START_WINDOWS.bat. No Steam files have been changed.",
    'wubuGO source package', 'OK', 'Information') | Out-Null
exit 1
