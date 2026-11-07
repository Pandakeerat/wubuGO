# Open the registered per-user uninstaller; do not recursively delete an inferred path.
$ErrorActionPreference = 'Stop'
$Uninstaller = Join-Path $env:LOCALAPPDATA 'Programs\wubuGO\unins000.exe'
if (Test-Path -LiteralPath $Uninstaller) {
    Start-Process -FilePath $Uninstaller -Wait
    exit 0
}
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    'No compiled wubuGO installation was found. A source/portable copy can be removed by deleting its extracted folder. User data and game backups are separate and are not removed automatically.',
    'wubuGO uninstall', 'OK', 'Information') | Out-Null
