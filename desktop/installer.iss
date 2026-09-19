; Inno Setup script for Pentimento.
;
; This exists so there is one file to download and run, without the
; behaviour a self-extracting executable would have. A PyInstaller onefile
; build writes 737 files and 69 MB into %TEMP% on every launch and then
; runs an unsigned binary from there, which is indistinguishable from a
; dropper to anything watching process and file activity. Installing once
; into a stable folder does that work a single time, at install, where it
; is expected.
;
; Per-user by default: no elevation prompt, nothing written outside the
; user's own profile, and an ordinary Add/Remove Programs entry.

#define AppName       "Pentimento"
#include "version.iss"   ; generated; defines AppVersion
#define AppPublisher  "Bebop.systems"
#define AppURL        "https://github.com/Bebop-systems/pentimento"
#define AppExe        "Pentimento.exe"

#define BaseAppId     "7B2F5A64-9C3E-4D18-9A6F-2E5C1D0B7A43"

[Setup]
; Scripted so a side-by-side install can claim its own identity rather
; than fighting the existing one over a single uninstall entry.
AppId={code:GetAppId}
; Required whenever AppId contains a constant: Inno cannot look up a
; previous language before it knows which application it is.
UsePreviousLanguage=no
; Same reason: the previous scope cannot be read before the identity is
; known. The scope is chosen on the command line or the dialog instead.
UsePreviousPrivileges=no
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer

; Per-user install: no UAC prompt, and nothing lands outside the profile.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
DefaultDirName={code:GetDefaultDir}
DefaultGroupName={code:GetGroupName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

OutputDir=..\dist
OutputBaseFilename=Pentimento-{#AppVersion}-windows-setup
SetupIconFile=icon.ico

; The installer wears the application's own colours rather than the
; default grey: same dark background, same geodesic mark. Several sizes
; so Windows can pick one for the display scaling.
WizardImageFile=wizard-large-164x314.png,wizard-large-192x386.png,wizard-large-246x459.png,wizard-large-273x556.png
WizardSmallImageFile=wizard-small-55x55.png,wizard-small-64x68.png,wizard-small-83x80.png,wizard-small-92x97.png
WizardImageStretch=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={code:GetDisplayName}

; LZMA2 over the whole payload: one solid block compresses 74 MB of Perl
; and Python down to about 30.
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

LicenseFile=..\LICENSE
InfoBeforeFile=installer-notes.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Pentimento\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE";   DestDir: "{app}"; DestName: "LICENSE.txt";   Flags: ignoreversion
Source: "..\NOTICE.md"; DestDir: "{app}"; DestName: "NOTICE.txt";    Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt";    Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} releases"; Filename: "{#AppURL}/releases"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The session scratch folder, if the app was ever killed before it tidied.
Type: filesandordirs; Name: "{localappdata}\Temp\pentimento-*"

[Code]
{ ---------------------------------------------------------------------
  Upgrade, or install alongside.

  With a fixed AppId an installer silently replaces whatever is already
  there, which is the right default and was already the behaviour. What
  was missing is saying so, and offering the alternative to anyone who
  wants to keep an old build around while trying a new one.

  Side by side needs a distinct identity or the two installs fight over
  one uninstall entry, so AppId, the directory, the Start menu group and
  the displayed name all gain a version suffix.
  --------------------------------------------------------------------- }

const
  ModeUpgrade  = 0;
  ModeParallel = 1;

var
  InstalledVersion: String;
  InstalledPath: String;
  ChoicePage: TInputOptionWizardPage;
  ForcedParallel: Boolean;

function BaseKey(): String;
begin
  Result := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#BaseAppId}_is1';
end;

procedure DetectExisting();
var
  Root: Integer;
  Found: Boolean;
begin
  InstalledVersion := '';
  InstalledPath := '';
  Found := False;

  for Root := 0 to 1 do
  begin
    if Root = 0 then
    begin
      if RegQueryStringValue(HKCU, BaseKey(), 'DisplayVersion', InstalledVersion) then
        Found := True;
      if Found then
        RegQueryStringValue(HKCU, BaseKey(), 'InstallLocation', InstalledPath);
    end
    else if not Found then
    begin
      if RegQueryStringValue(HKLM, BaseKey(), 'DisplayVersion', InstalledVersion) then
        Found := True;
      if Found then
        RegQueryStringValue(HKLM, BaseKey(), 'InstallLocation', InstalledPath);
    end;
  end;

  if not Found then
    InstalledVersion := '';
end;

function WantsParallel(): Boolean;
begin
  { /PARALLEL forces it without the wizard, which makes the behaviour
    scriptable and, just as usefully, testable. }
  if ForcedParallel then
  begin
    Result := True;
    Exit;
  end;

  { Nested rather than a single expression: Pascal's `and` does not
    short-circuit here, so the page must be known to exist before its
    selection is read. }
  Result := False;
  if InstalledVersion = '' then
    Exit;
  if not Assigned(ChoicePage) then
    Exit;
  Result := (ChoicePage.SelectedValueIndex = ModeParallel);
end;

function GetAppId(Param: String): String;
begin
  if WantsParallel() then
    Result := '{#BaseAppId}_{#AppVersion}'
  else
    Result := '{#BaseAppId}';
end;

function GetDefaultDir(Param: String): String;
begin
  if WantsParallel() then
    Result := ExpandConstant('{autopf}\{#AppName} {#AppVersion}')
  else if InstalledPath <> '' then
    Result := RemoveBackslashUnlessRoot(InstalledPath)
  else
    Result := ExpandConstant('{autopf}\{#AppName}');
end;

function GetGroupName(Param: String): String;
begin
  if WantsParallel() then
    Result := '{#AppName} {#AppVersion}'
  else
    Result := '{#AppName}';
end;

function GetDisplayName(Param: String): String;
begin
  { Two entries reading the same thing in Add or Remove Programs would be
    a puzzle, so a parallel install says what it is. }
  if WantsParallel() then
    Result := '{#AppName} {#AppVersion} (side by side)'
  else
    Result := '{#AppName} {#AppVersion}';
end;

function InitializeSetup(): Boolean;
begin
  ForcedParallel := ExpandConstant('{param:PARALLEL|no}') <> 'no';
  DetectExisting();
  Result := True;
end;

procedure InitializeWizard();
var
  Caption: String;
begin
  if InstalledVersion = '' then
    Exit;

  if InstalledVersion = '{#AppVersion}' then
    Caption := 'Pentimento ' + InstalledVersion + ' is already installed.'
  else
    Caption := 'Pentimento ' + InstalledVersion + ' is already installed.';

  ChoicePage := CreateInputOptionPage(
    wpWelcome,
    'Existing installation',
    Caption,
    'Choose what to do with it. Upgrading is almost always what you want:'
    + ' your cleaned photos and settings are untouched either way, because'
    + ' neither lives in the program folder.',
    True, False);

  ChoicePage.Add('Upgrade it to {#AppVersion}  (recommended)');
  ChoicePage.Add('Install {#AppVersion} alongside it, keeping both');
  ChoicePage.SelectedValueIndex := ModeUpgrade;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if Assigned(ChoicePage) and (CurPageID = ChoicePage.ID) then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if Assigned(ChoicePage) and (CurPageID = ChoicePage.ID) then
  begin
    { The directory page has to re-read the default, which now depends on
      the choice just made. }
    WizardForm.DirEdit.Text := GetDefaultDir('');
    if WantsParallel() then
      Result := MsgBox(
        'Two installed copies share one Pictures folder and one settings'
        + ' location, which is usually fine but occasionally surprising.'
        + #13#10#13#10
        + 'If you only want to try a new version without disturbing the old'
        + ' one, the portable build from the releases page is the tidier'
        + ' way: it runs from any folder and writes nothing to the'
        + ' registry.'
        + #13#10#13#10
        + 'Continue with a side-by-side install?',
        mbConfirmation, MB_YESNO) = IDYES;
  end;
end;
