; Inno Setup 6 — OCR Agentic AI professional installer
; Compiled by build\build.ps1, which passes /DMyAppVersion=x.y.z
; Standard pro behaviors: modern wizard, versioned metadata, in-place upgrades
; (fixed AppId), running-app close, optional desktop icon + autostart,
; silent-mode support for the auto-updater (/SILENT), and an uninstaller
; that asks before touching user data.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "OCR Agentic AI"
#define MyAppExeName "OCR-Agentic-Ai.exe"
#define MyAppPublisher "Nick (Suksan Trisaranasart)"

[Setup]
; Fixed GUID = every future version upgrades the same install in place.
AppId={{B7C2A6F4-3E0D-4A14-9C6B-5D9E2F7A1C44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\OCR-Agentic-Ai
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
WizardImageFile=stage\wizard.bmp
WizardSmallImageFile=stage\wizard_small.bmp
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=OCR-Agentic-Ai_Setup_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Start {#MyAppName} with Windows (runs in the tray)"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\OCR-Agentic-Ai\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundled Tesseract engine + tha/eng models — end users install nothing else.
Source: "stage\tesseract\*"; DestDir: "{app}\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; All-users autostart (machine install) — removed automatically on uninstall.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Relaunch after install. NOT skipifsilent — the auto-updater installs with
; /SILENT and the app must still come back up (a missing relaunch made it look
; like the update "killed" the app). This is a backstop to the apply script's own
; relaunch; the single-instance mutex dedups a double launch. (v0.3.0)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall

[UninstallRun]
; Make sure the tray instance is gone before files are removed.
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName}"; \
  Flags: runhidden; RunOnceId: "KillApp"

[Code]
// Uninstall: user data (scans, DB, settings, API key) is NEVER deleted silently.
// Interactive uninstall asks; silent uninstall always keeps data.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then begin
    DataDir := ExpandConstant('{localappdata}\OCR-Agentic-Ai');
    if (not UninstallSilent) and DirExists(DataDir) then begin
      if MsgBox('Also delete the Shared Store (scans, results, settings, API key)?'
                + #13#10 + DataDir + #13#10#13#10
                + 'Open-Claw reads this data — keep it unless you are removing everything.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
