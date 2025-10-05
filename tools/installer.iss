; BATTLE2 Windows Installer (Inno Setup 6)
; Build with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" tools\installer.iss

#define AppName       "BATTLE2"
#define AppVersion    "1.0.0"
#define AppPublisher  "Your Org"
#define RepoRoot      ".."                   ; relative to this .iss file (tools\.. = repo root)
#define DistRoot      "..\dist"              ; PyInstaller output
#define AgentsSrc     "..\agents"            ; adjust if needed
#define ExamplesSrc   "..\examples"          ; adjust if needed

[Setup]
AppId={{A5B86D38-9A6C-4D7F-9B4E-BATTLE2-0001}}   ; generate your own GUID once and keep it
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#DistRoot}
OutputBaseFilename=BATTLE2-Setup-{#AppVersion}
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicons"; Description: "Create desktop shortcuts"; GroupDescription: "Additional shortcuts:"
Name: "addtopath";    Description: "Add BATTLE2\bin to PATH (for all users)"; GroupDescription: "Environment:"

[Dirs]
; Install binaries to Program Files
Name: "{app}\bin"

; Put writable data under ProgramData
Name: "{commonappdata}\BATTLE2"
Name: "{commonappdata}\BATTLE2\runs\_loose"
Name: "{commonappdata}\BATTLE2\resources\agents"
Name: "{commonappdata}\BATTLE2\resources\examples"
Name: "{commonappdata}\BATTLE2\resources\docs"

; Ensure users can write runs and maybe agents/examples
; (uncomment if you want relaxed ACLs)
; Name: "{commonappdata}\BATTLE2\runs"; Permissions: users-modify
; Name: "{commonappdata}\BATTLE2\resources\agents"; Permissions: users-modify

[Files]
; --- Executables (copy WHOLE PyInstaller output directories) ---
Source: "{#DistRoot}\battle-agent-designer\*"; DestDir: "{app}\bin\battle-agent-designer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\match_runner\*";        DestDir: "{app}\bin\match_runner";        Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DistRoot}\battle-cli\*";          DestDir: "{app}\bin\battle-cli";          Flags: ignoreversion recursesubdirs createallsubdirs


; --- Copy resources (adjust sources if your repo differs) ---
Source: "{#RepoRoot}\README.md"; DestDir: "{commonappdata}\BATTLE2\resources\docs"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE";   DestDir: "{commonappdata}\BATTLE2\resources\docs"; Flags: ignoreversion

; sample agents/examples (skip if folders don’t exist)
Source: "{#AgentsSrc}\*";   DestDir: "{commonappdata}\BATTLE2\resources\agents";   Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git*"
Source: "{#ExamplesSrc}\*"; DestDir: "{commonappdata}\BATTLE2\resources\examples"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git*"

[Icons]
Name: "{group}\Battle Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"
Name: "{group}\Match Runner (Pygame)"; Filename: "{app}\bin\match_runner\match_runner.exe"
Name: "{group}\Battle Engine CLI";     Filename: "{app}\bin\battle-cli\battle-cli.exe"

; optional desktop icons
Name: "{commondesktop}\Battle Agent Designer"; Filename: "{app}\bin\battle-agent-designer\battle-agent-designer.exe"; Tasks: desktopicons
Name: "{commondesktop}\Match Runner (Pygame)"; Filename: "{app}\bin\match_runner\match_runner.exe"; Tasks: desktopicons

[Run]
; Show README after install (optional)
Filename: "{cmd}"; Parameters: "/c start "" ""{commonappdata}\BATTLE2\resources\docs\README.md"""; Flags: postinstall skipifsilent

[Registry]
; Make app root discoverable for code: prefer ProgramData for writable data
; BATTLE2_ROOT tells your app where runs/resources live.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "BATTLE2_ROOT"; ValueData: "{commonappdata}\BATTLE2"; Flags: preservestringtype

; Optional PATH addition (so users can type battle-cli anywhere)
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}\bin"; Tasks: addtopath; Flags: preservestringtype

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  { Keep empty or add future logic here. }
end;

