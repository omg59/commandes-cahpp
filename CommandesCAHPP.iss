#define MyAppName "Commandes CAHPP"
#define MyAppVersion "1.4.2"
#define MyAppPublisher "Commandes CAHPP"
#define MyAppExeName "CommandesCAHPP.exe"

[Setup]
AppId={{6824A1B6-9ED6-4DD4-9126-410BB72CF3F0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\CommandesCAHPP
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
OutputDir=dist-installer
OutputBaseFilename=CommandesCAHPP-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app_icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=1.4.2.0
VersionInfoProductVersion=1.4.2
VersionInfoDescription=Installeur Commandes CAHPP
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[InstallDelete]
; Une mise à jour remplace uniquement le programme. Les données de
; l'utilisateur et les documents restent volontairement intacts.
Type: files; Name: "{app}\{#MyAppExeName}"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\CommandesCAHPP-portable\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\CommandesCAHPP-portable\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\CommandesCAHPP-portable\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist skipifsourcedoesntexist
Source: "README.md"; DestDir: "{app}"; DestName: "LISEZMOI.md"; Flags: onlyifdoesntexist

[Dirs]
Name: "{app}\assets"
Name: "{app}\data"
Name: "{app}\documents"
Name: "{app}\envois"
Name: "{app}\exports"
Name: "{app}\sauvegardes"

[Icons]
Name: "{group}\Commandes CAHPP"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{autodesktop}\Commandes CAHPP"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"; Check: ShouldCreateDesktopShortcut

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: checkedonce

[Code]
function ShouldCreateDesktopShortcut(): Boolean;
begin
  Result := WizardIsTaskSelected('desktopicon') or
    FileExists(ExpandConstant('{autodesktop}\Commandes CAHPP.lnk'));
end;

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Commandes CAHPP"; Flags: nowait postinstall skipifsilent
