; BATTLE2 v0.2 Windows installer (Inno Setup 6)
; Build from the repository root with:
;   ISCC.exe tools\installer.iss

#define AppName "BATTLE2"
#define AppVersion "0.2.0"
#define AppPublisher "BATTLE2 Project"
#define DistRoot "..\dist\windows"
#define OutputRoot "..\dist\installer"

[Setup]
; Stable product identity. Keep this AppId unchanged for all BATTLE2 v0.2 upgrades.
AppId={{A5B86D38-9A6C-4D7F-9B4E-BA7720000002}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
UninstallDisplayName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename=BATTLE2-Setup-{#AppVersion}
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicons"; Description: "Create desktop shortcuts"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Dirs]
; This is writable shared application data, not a bundled-resource directory.
; /BATTLE2DATAROOT=... is supported for isolated validation installations.
Name: "{code:GetDataRoot}"; Permissions: users-modify
Name: "{code:GetDataRoot}\agents"
Name: "{code:GetDataRoot}\replays"
Name: "{code:GetDataRoot}\logs"
Name: "{code:GetDataRoot}\runs\_loose"

[Files]
; Preserve each canonical PyInstaller onedir tree and their sibling relationship.
Source: "{#DistRoot}\battle2\*"; DestDir: "{app}\bin\battle2"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\battle-cli\*"; DestDir: "{app}\bin\battle-cli"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\match-runner\*"; DestDir: "{app}\bin\match-runner"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\battle-agent-designer\*"; DestDir: "{app}\bin\battle-agent-designer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\battle-replay-viewer\*"; DestDir: "{app}\bin\battle-replay-viewer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\BATTLE2 Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"; WorkingDir: "{app}\bin"
Name: "{group}\BATTLE2 Replay Viewer"; Filename: "{app}\bin\battle-replay-viewer\battle-replay-viewer.exe"; WorkingDir: "{app}\bin"
Name: "{commondesktop}\BATTLE2 Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons
Name: "{commondesktop}\BATTLE2 Replay Viewer"; Filename: "{app}\bin\battle-replay-viewer\battle-replay-viewer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons

[Registry]
; Only the v0.2 variable is installed. BATTLE_ROOT remains a runtime fallback.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "BATTLE2_ROOT"; ValueData: "{code:GetDataRoot}"; Flags: preservestringtype uninsdeletevalue

[Code]
function GetDataRoot(Param: String): String;
begin
  Result := ExpandConstant('{param:BATTLE2DATAROOT|}');
  if Result = '' then
    Result := ExpandConstant('{commonappdata}\BATTLE2');
end;
