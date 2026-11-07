#define MyAppName "Commandes CAHPP Horizon"
#define MyAppVersion "2.0.0a7"
#define MyAppExeName "CommandesCAHPP-Horizon.exe"

[Setup]
AppId={{E6691A62-74A8-4880-B920-621F7EA457DA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Commandes CAHPP
DefaultDirName={localappdata}\Programs\CommandesCAHPP-Horizon
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
OutputDir=dist-installer-horizon
OutputBaseFilename=CommandesCAHPP-Horizon-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=2.0.0.7
CloseApplications=yes
CloseApplicationsFilter=CommandesCAHPP-Horizon.exe
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[InstallDelete]
Type: files; Name: "{app}\{#MyAppExeName}"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\CommandesCAHPP-Horizon-portable\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\CommandesCAHPP-Horizon-portable\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "docs\horizon.md"; DestDir: "{app}"; DestName: "LISEZMOI.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci Horizon sur le Bureau"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Horizon"; Flags: nowait postinstall skipifsilent
