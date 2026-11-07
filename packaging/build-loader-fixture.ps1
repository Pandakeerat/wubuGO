# Build harmless native DLLs solely to reproduce inherited DLL-search contamination.
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Stage = Join-Path $Root 'build\loader-probe'
$VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (!(Test-Path -LiteralPath $VsWhere)) { throw 'The Windows loader regression needs Visual Studio C++ Build Tools on the build machine.' }
$VsRoot = & $VsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$VsRoot) { throw 'MSVC x64 build tools were not found.' }
$DevCmd = Join-Path $VsRoot 'Common7\Tools\VsDevCmd.bat'
New-Item -ItemType Directory -Path $Stage, (Join-Path $Stage 'probe'), (Join-Path $Stage 'good'), (Join-Path $Stage 'bad') -Force | Out-Null
$Batch = Join-Path $Stage 'compile.cmd'
$Text = @"
@echo off
call "$DevCmd" -arch=x64 -host_arch=x64 >nul
if errorlevel 1 exit /b 1
cl.exe /nologo /W4 /O2 /MT "$Root\tests\native\loader_probe.c" /Fo"$Stage\probe.obj" /Fe"$Stage\probe\loader_probe.exe"
if errorlevel 1 exit /b 1
cl.exe /nologo /W4 /O2 /MT /LD /DVALUE=42 "$Root\tests\native\external_fixture.c" /Fo"$Stage\good.obj" /link /OUT:"$Stage\good\external_fixture.dll" /IMPLIB:"$Stage\good\external_fixture.lib"
if errorlevel 1 exit /b 1
cl.exe /nologo /W4 /O2 /MT /LD /DVALUE=13 "$Root\tests\native\external_fixture.c" /Fo"$Stage\bad.obj" /link /OUT:"$Stage\bad\external_fixture.dll" /IMPLIB:"$Stage\bad\external_fixture.lib"
if errorlevel 1 exit /b 1
"@
Set-Content -LiteralPath $Batch -Value $Text -Encoding ascii
& $env:ComSpec /d /c $Batch
if ($LASTEXITCODE -ne 0) { throw 'Native loader fixture compilation failed.' }
$env:WUBUGO_LOADER_PROBE_DIR = $Stage
