; Bytefray v0.6 Windows installer (Inno Setup 6)
; Formerly BATTLE2. Build from the repository root with:
;   ISCC.exe tools\installer.iss

#define AppName "Bytefray"
#define AppVersion "1.0.0"
; Release-artifact filenames use the hyphenated tag spelling (matching the
; "v1.0.0" Git tag/GitHub release name) while AppVersion keeps the PEP 440
; spelling used by the Python package/CLI. Both spellings are identical for
; a final release ("1.0.0"); ReleaseTag is kept as its own define (rather
; than folded back into AppVersion) so the same pattern continues to work
; unchanged for a future pre-release identity (e.g. "1.1.0rc1" /
; "1.1.0-rc1"). See docs/ROADMAP.md and CHANGELOG.md for context.
#define ReleaseTag "1.0.0"
#define AppPublisher "Bytefray Project"
#define DistRoot "..\dist\windows"
#define OutputRoot "..\dist\installer"

[Setup]
; Stable product identity, unchanged across the BATTLE2 -> Bytefray rebrand.
; Keep this AppId unchanged for all upgrades so existing BATTLE2 installs
; upgrade in place as Bytefray rather than installing side-by-side.
AppId={{A5B86D38-9A6C-4D7F-9B4E-BA7720000002}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
UninstallDisplayName={#AppName} {#AppVersion}
SetupIconFile=..\assets\branding\bytefray-icon.ico
UninstallDisplayIcon={app}\bin\battle2\battle2.exe
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
Source: "{#DistRoot}\battle-agent-designer\*"; DestDir: "{app}\bin\battle-agent-designer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\battle-replay-viewer\*"; DestDir: "{app}\bin\battle-replay-viewer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\Bytefray Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"; WorkingDir: "{app}\bin"
Name: "{group}\Bytefray Replay Viewer"; Filename: "{app}\bin\battle-replay-viewer\battle-replay-viewer.exe"; WorkingDir: "{app}\bin"
Name: "{commondesktop}\Bytefray Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons
Name: "{commondesktop}\Bytefray Replay Viewer"; Filename: "{app}\bin\battle-replay-viewer\battle-replay-viewer.exe"; WorkingDir: "{app}\bin"; Tasks: desktopicons

[Registry]
; BYTEFRAY_ROOT is the preferred variable for new installs. BATTLE2_ROOT is
; written alongside it for compatibility with tooling that still reads the
; old name; BATTLE_ROOT remains a runtime-only fallback (see paths.py) and is
; not written here. Both values point at the same writable data directory.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "BYTEFRAY_ROOT"; ValueData: "{code:GetDataRoot}"; Flags: preservestringtype uninsdeletevalue
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "BATTLE2_ROOT"; ValueData: "{code:GetDataRoot}"; Flags: preservestringtype uninsdeletevalue

[Code]
function GetDataRoot(Param: String): String;
begin
  Result := ExpandConstant('{param:BATTLE2DATAROOT|}');
  if Result = '' then
    // Deliberately still "BATTLE2": this is the writable data directory an
    // existing BATTLE2 install already uses. Renaming it to "Bytefray" would
    // point upgraded installs at an empty new folder and orphan existing
    // agents/replays/logs. Only the registry variable names are rebranded.
    Result := ExpandConstant('{commonappdata}\BATTLE2');
end;
