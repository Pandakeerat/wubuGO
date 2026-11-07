# CI acceptance test of the real Inno installer, including paths with spaces.
# Runs only on the disposable Windows runner; never installs or launches a game.
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$env:WUBUGO_LOADER_PROBE_DIR = Join-Path $Root 'build\loader-probe'
if ($env:CI -ne 'true') { throw 'This acceptance script is intended for a disposable CI runner.' }
$Installer = Join-Path $Root 'dist\wubuGO-6.0.1-windows-x64-setup.exe'
if (!(Test-Path -LiteralPath $Installer)) { throw 'Build the Windows installer first.' }
$Sandbox = Join-Path $env:RUNNER_TEMP ('wubuGO installer test ' + [guid]::NewGuid().ToString('N'))
$InstallDir = Join-Path $Sandbox 'Installed Application'
$StateDir = Join-Path $env:LOCALAPPDATA 'wubuGO'
$Sentinel = Join-Path $StateDir ('ci-retained-' + [guid]::NewGuid().ToString('N') + '.txt')
$Report = Join-Path $Root 'dist\installed-selftest.json'
$Log = Join-Path $Root 'dist\installer-test.log'
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{938583B8-D1F5-4634-B24C-BF9F463001BE}_is1'
$Shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'wubuGO\wubuGO.lnk'
New-Item -ItemType Directory -Path $Sandbox, $StateDir -Force | Out-Null
Set-Content -LiteralPath $Sentinel -Value 'keep this user state' -NoNewline

function Invoke-BoundedProcess([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds = 120) {
    $Process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    $null = $Process.Handle  # Keep the process handle for reliable ExitCode after fast exits.
    if (!$Process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "Process timed out: $File"
    }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) { throw "Process exited with code $($Process.ExitCode): $File" }
}

try {
    # Reinstall the same candidate as a repeatable upgrade/repair exercise.
    foreach ($Attempt in 1..2) {
        Invoke-BoundedProcess $Installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
            ('/DIR="' + $InstallDir + '"'), ('/LOG="' + $Log + '"'))
        $Executable = Join-Path $InstallDir 'wubuGO.exe'
        if (!(Test-Path -LiteralPath $Executable)) { throw 'Installer did not publish the executable.' }
        if (!(Test-Path -LiteralPath $UninstallKey)) { throw 'Per-user uninstall registration is missing.' }
        if (!(Test-Path -LiteralPath $Shortcut)) { throw 'Start-menu shortcut is missing.' }
        $SavedPath, $SavedPythonHome, $SavedPythonPath = $env:PATH, $env:PYTHONHOME, $env:PYTHONPATH
        try {
            # The installed program must not need Python or build tools on PATH.
            $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
            $env:PYTHONHOME = ''
            $env:PYTHONPATH = ''
            Invoke-BoundedProcess $Executable @('--self-test', ('"' + $Report + '"'))
        } finally {
            $env:PATH, $env:PYTHONHOME, $env:PYTHONPATH = $SavedPath, $SavedPythonHome, $SavedPythonPath
        }
        if (!(Test-Path -LiteralPath $Report)) { throw 'Installed executable did not write its self-test report.' }
        $Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
        if ($Result.ok -ne $true -or $Result.isolated_state -ne $true) { throw 'Installed GUI self-test failed.' }
        if ((Get-Content -LiteralPath $Sentinel -Raw) -ne 'keep this user state') { throw 'Install changed user state.' }
    }
    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    if (!(Test-Path -LiteralPath $Uninstaller)) { throw 'Registered application uninstaller is missing.' }
    Invoke-BoundedProcess $Uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ((Test-Path -LiteralPath (Join-Path $InstallDir 'wubuGO.exe')) -and [DateTime]::UtcNow -lt $Deadline) {
        Start-Sleep -Milliseconds 200
    }
    if (Test-Path -LiteralPath (Join-Path $InstallDir 'wubuGO.exe')) { throw 'Uninstall left the application executable.' }
    if (Test-Path -LiteralPath $UninstallKey) { throw 'Uninstall left its registry entry.' }
    if (Test-Path -LiteralPath $Shortcut) { throw 'Uninstall left its Start-menu shortcut.' }
    if ((Get-Content -LiteralPath $Sentinel -Raw) -ne 'keep this user state') { throw 'Uninstall changed user state.' }
    @{
        ok = $true
        platform = 'Windows x64'
        tests = @('silent install', 'path with spaces', 'per-user uninstall registration', 'Start-menu shortcut',
            'installed GUI self-test without Python on PATH', 'repeat install', 'silent uninstall', 'user state retained')
        game_started = $false
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Root 'dist\installer-smoke.json') -Encoding utf8
} finally {
    # Clean only the uniquely named sentinel; all other user state is retained.
    Remove-Item -LiteralPath $Sentinel -Force -ErrorAction SilentlyContinue
    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    if (Test-Path -LiteralPath $Uninstaller) {
        try { Invoke-BoundedProcess $Uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') } catch { Write-Warning $_ }
    }
}
