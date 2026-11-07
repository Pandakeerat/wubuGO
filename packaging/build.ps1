# Requires Windows x64, Python 3.13 with Tcl/Tk, and Inno Setup 6.
param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Push-Location $Root
try {
    py -3.13 -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 with venv and Tcl/Tk is required on the build machine.' }
    $Python = Join-Path $Root '.build-venv\Scripts\python.exe'
    & $Python -m pip install -r packaging\requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
    & $Python -c 'import tkinter; print(tkinter.TkVersion)'
    if ($LASTEXITCODE -ne 0) { throw 'Tcl/Tk is missing from build Python.' }
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing release build.' }
    . (Join-Path $PSScriptRoot 'build-loader-fixture.ps1')
    & $Python -m PyInstaller --clean --noconfirm packaging\wubuGO.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    & $Python packaging\collect_licenses.py dist\wubuGO
    if ($LASTEXITCODE -ne 0) { throw 'Runtime license collection failed.' }
    $Report = Join-Path $Root 'dist\frozen-selftest.json'
    $Smoke = Start-Process -FilePath (Join-Path $Root 'dist\wubuGO\wubuGO.exe') -ArgumentList @('--self-test', ('"' + $Report + '"')) -Wait -PassThru
    if ($Smoke.ExitCode -ne 0 -or !(Test-Path -LiteralPath $Report)) { throw 'Frozen GUI self-test failed.' }
    $Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    if ($Result.ok -ne $true) { throw 'Frozen GUI self-test reported a failure.' }
    Compress-Archive -Path dist\wubuGO -DestinationPath dist\wubuGO-6.0.1-windows-x64-portable.zip -Force
    if (!$SkipInstaller) {
        $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($Compiler) { $Iscc = $Compiler.Source }
        else { $Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
        if (!(Test-Path -LiteralPath $Iscc)) { throw 'Install Inno Setup 6 or use -SkipInstaller to produce the portable bundle.' }
        & $Iscc packaging\wubuGO.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    }
    & $Python packaging\checksums.py dist
} finally { Pop-Location }
