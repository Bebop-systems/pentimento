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

[Setup]
AppId={{7B2F5A64-9C3E-4D18-9A6F-2E5C1D0B7A43}
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
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

OutputDir=..\dist
OutputBaseFilename=Pentimento-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}

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
