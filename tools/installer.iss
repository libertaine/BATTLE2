; Bytefray Windows installer (Inno Setup 6). Build from the repository root with:
;   ISCC.exe tools\installer.iss

#define AppName "Bytefray"
#define AppVersion "4.0.0a4"
; Release-artifact filenames use the hyphenated tag spelling (matching the
; "v4.0.0-alpha4" Git tag/GitHub release name) while AppVersion keeps the
; normalized PEP 440 spelling used by the Python package/CLI. ReleaseTag is
; kept separate because prerelease tag and package spellings differ. See
; docs/ROADMAP.md and
; CHANGELOG.md for context.
#define ReleaseTag "4.0.0-alpha4"
#define AppPublisher "Bytefray Project"
#define DistRoot "..\dist\windows"
#define OutputRoot "..\dist\installer"

[Setup]
; Stable Bytefray product identity. Keep this AppId unchanged across upgrades.
AppId={{A5B86D38-9A6C-4D7F-9B4E-BA7720000002}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
UninstallDisplayName={#AppName} {#AppVersion}
SetupIconFile=..\assets\branding\bytefray-icon.ico
UninstallDisplayIcon={app}\bin\bytefray\bytefray.exe
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename=Bytefray-Setup-{#ReleaseTag}
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
; /BYTEFRAYDATAROOT=... is supported for isolated validation installations.
Name: "{code:GetDataRoot}"; Permissions: users-modify
Name: "{code:GetDataRoot}\agents"
Name: "{code:GetDataRoot}\replays"
Name: "{code:GetDataRoot}\logs"
Name: "{code:GetDataRoot}\runs\_loose"

[Files]
; Preserve each canonical PyInstaller onedir tree and their sibling relationship.
Source: "{#DistRoot}\bytefray\*"; DestDir: "{app}\bin\bytefray"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\bytefray-cli\*"; DestDir: "{app}\bin\bytefray-cli"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\bytefray-agent-designer\*"; DestDir: "{app}\bin\bytefray-agent-designer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\bytefray-replay-viewer\*"; DestDir: "{app}\bin\bytefray-replay-viewer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\Bytefray Agent Designer"; Filename: "{app}\bin\bytefray-agent-designer\bytefray-agent-designer.exe"; WorkingDir: "{app}\bin"
Name: "{group}\Bytefray Replay Viewer"; Filename: "{app}\bin\bytefray-replay-viewer\bytefray-replay-viewer.exe"; WorkingDir: "{app}\bin"
Name: "{commondesktop}\Bytefray Agent Designer"; Filename: "{app}\bin\bytefray-agent-designer\bytefray-agent-designer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons
Name: "{commondesktop}\Bytefray Replay Viewer"; Filename: "{app}\bin\bytefray-replay-viewer\bytefray-replay-viewer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons

[Registry]
; BYTEFRAY_ROOT points every installed application at shared writable data.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "BYTEFRAY_ROOT"; ValueData: "{code:GetDataRoot}"; Flags: preservestringtype uninsdeletevalue

[Code]
function GetDataRoot(Param: String): String;
begin
  Result := ExpandConstant('{param:BYTEFRAYDATAROOT|}');
  if Result = '' then
    Result := ExpandConstant('{commonappdata}\Bytefray');
end;
