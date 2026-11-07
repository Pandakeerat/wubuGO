; Compile after packaging/build.ps1 produces the frozen application.
#define AppVersion "6.0.1"
[Setup]
AppId={{938583B8-D1F5-4634-B24C-BF9F463001BE}
AppName=wubuGO
AppVersion={#AppVersion}
AppPublisher=wubuGO
DefaultDirName={localappdata}\Programs\wubuGO
DefaultGroupName=wubuGO
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=wubuGO-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\wubuGO.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\wubuGO\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\wubuGO"; Filename: "{app}\wubuGO.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\wubuGO"; Filename: "{app}\wubuGO.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\wubuGO.exe"; Description: "Open wubuGO"; Flags: nowait postinstall skipifsilent
; No Steam writes or downloader scripts. Mutable data lives outside {app};
; uninstall removes only tracked application files and leaves user data intact.
