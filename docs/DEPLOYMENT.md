# Deploying Pentimento to a fleet

For administrators. Everyday users want the
[README](../README.md); nothing here is needed to run the application.

Every value below was read back from a real install rather than written from
memory. Commands show a concrete version for copy-and-paste; substitute
whichever one you downloaded.

## What the application does on an endpoint

Worth knowing before it lands on a managed machine.

| Behaviour | Detail |
|---|---|
| Network | None. No update check, no telemetry, no licence call. The only fetch is ExifTool at *build* time, never at run time. |
| Listener | A loopback HTTP server on `127.0.0.1`, random high port, for the app's own window. It rejects any request whose `Host` header it did not issue. |
| Child processes | One `exiftool.exe`, spawned from the install folder, living as long as the app. It is bound to the parent with a Job Object, so it cannot be orphaned. |
| Writes | Cleaned copies to the user's Pictures folder; a session scratch directory under `%TEMP%\pentimento-*`, removed on exit. |
| Reads | Only files the user opens. |
| Elevation | None. Per-user install, per-user runtime. |
| Persistence | A Start menu shortcut. No service, no scheduled task, no run key. |

## Why there is no single portable .exe

A PyInstaller one-file build unpacks **737 files and 69 MB into `%TEMP%` on
every launch** and then executes an unsigned binary from there. Measured on a
reference machine, it also spawns a second copy of its own image.

Self-extraction to temp, execution from temp, and a duplicated process image
are three behaviours that endpoint detection products score heavily, and one
of the reasons PyInstaller one-file builds have a reputation for false
positives. It saves 0.5 seconds of startup and costs a great deal of
plausibility.

The installer does that unpacking **once**, at install, into a stable
directory — which is what every other Windows application does.

## Intune, start to finish

### First, the app type

An `.exe` installer is a **Win32 app**, not a line-of-business app. Intune's
LoB type only accepts `.msi`, `.appx`/`.msix` and a few mobile formats, so
pointing it at this installer will not work. Choose **Windows app (Win32)**.

If your estate mandates MSI, say so on the issue tracker — producing one is a
build change rather than an application change.

### Package it

Wrap the installer with the
[Win32 Content Prep Tool](https://github.com/microsoft/Microsoft-Win32-Content-Prep-Tool):

```
IntuneWinAppUtil.exe -c .\dist -s Pentimento-0.1.0-windows-setup.exe -o .\intune
```

That produces `Pentimento-0.1.0-windows-setup.intunewin`.

### Add it in the portal

**Intune admin center → Apps → All apps → Add → Windows app (Win32)**, then
upload the `.intunewin` file.

**App information**

| Field | Value |
|---|---|
| Name | `Pentimento` |
| Description | Inspect and rewrite photo metadata locally. Shows what a photo reveals about where it was taken, which device took it and who is in it, then removes or rewrites any of it. Runs entirely on the device with no network access. |
| Publisher | `Bebop.systems` |
| App version | `0.1.0` |
| Category | `Photo & Design`, or `Computer management` |
| Information URL | `https://github.com/Bebop-systems/pentimento` |
| Privacy URL | `https://github.com/Bebop-systems/pentimento/blob/main/SECURITY.md` |
| Developer | `Bebop.systems` |
| Notes | Unsigned build; see the signing section below |
| **Logo** | `desktop/icon-intune-256.png` in this repository |

The logo is a 256x256 PNG of about 5 KB, well inside Intune's 1 MB limit. It
is generated rather than drawn by hand: `python desktop/make_icon.py` rebuilds
it alongside the Windows and macOS icons, so the tile in Company Portal cannot
drift from the application's own icon.

**Program**

| Field | Value |
|---|---|
| Install command | `Pentimento-0.1.0-windows-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /CURRENTUSER` |
| Uninstall command | `"%LOCALAPPDATA%\Programs\Pentimento\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` |
| Install behavior | **User** |
| Device restart behavior | **No specific action** |

For a machine-wide install, swap `/CURRENTUSER` for `/ALLUSERS`, set install
behavior to **System**, and point the uninstall command at
`"%ProgramFiles%\Pentimento\unins000.exe"`.

**Return codes** — the Inno Setup defaults are already correct:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1602` | Cancelled by the user, treat as failed |
| `1603` | Fatal error during installation |
| `3010` | Soft reboot |

**Requirements**

| Field | Value |
|---|---|
| Operating system architecture | `x64` |
| Minimum operating system | `Windows 10 1809` |
| Disk space required | `100 MB` |

**Assignments** — a user group for a per-user install, a device group for
`/ALLUSERS`. *Available for enrolled devices* suits a tool people opt into;
*Required* if it is standard issue.

## Detection rules

Any one of these is sufficient. The registry key is the most precise.

**Registry** — per-user installs write to `HKCU`, machine-wide to `HKLM`:

```
Key:   HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{7B2F5A64-9C3E-4D18-9A6F-2E5C1D0B7A43}_is1
Value: DisplayVersion
Rule:  Version comparison, greater than or equal to  0.1.0
```

**File** — the executable carries a proper version resource:

```
Path:    %LOCALAPPDATA%\Programs\Pentimento
File:    Pentimento.exe
Rule:    File or folder exists, or String version >= 0.1.0
```

The product identity in that resource is `Bebop.systems` / `Pentimento`, which
is also what Task Manager and the file's Properties dialog display.

## Requirements

| Requirement | Note |
|---|---|
| Architecture | x64 |
| Windows | 10 1809 or later, 11 recommended |
| Disk | ~80 MB installed |
| Edge WebView2 Runtime | For the native window. Present on Windows 11 and on Windows 10 since 2021. |

WebView2 is worth adding as an Intune **dependency** if your estate includes
older or stripped Windows 10 images. It is not strictly required: without it
the application opens the user's default browser instead and everything else
works identically.

## Code signing and Attack Surface Reduction

Release builds are **not code signed**. On a managed estate that matters more
than it does for an individual:

- SmartScreen will warn until the binary earns reputation.
- The ASR rule *Block executable files from running unless they meet a
  prevalence, age or trusted list criterion* will block it outright, because a
  freshly published unsigned binary has neither prevalence nor age.

Three ways out, in order of preference:

1. **Sign it yourself.** The build is reproducible from source; an internal
   code-signing certificate applied to `Pentimento.exe` and the installer
   solves this permanently, and is the reason the project is MIT licensed.
2. **Add an ASR exclusion** for the install path.
3. **Deploy the portable zip** to a trusted location covered by an existing
   allow rule.

If a signed release from this project would be useful to you, say so on the
issue tracker — it is a cost question rather than a technical one.

## The Pictures folder question

Cleaned copies are written to the user's **Pictures** folder by default. On a
managed estate that folder is frequently redirected into OneDrive by Known
Folder Move.

The consequence is worth stating plainly: a photograph a user just cleaned
**would then sync to OneDrive**. That is not a leak of the original, which is
never modified or moved, but it may not be what someone reaching for a privacy
tool expects.

Set `PENTIMENTO_OUTPUT` to redirect it anywhere:

```
setx PENTIMENTO_OUTPUT "%USERPROFILE%\Pentimento"
```

Deploy that as an environment variable in the same Intune configuration
profile as the application, and cleaned files stay local.

## Supersedence and updates

The application never checks for updates. It shows its version and a link to
the releases page, which opens in the user's browser only if they click it.

For managed estates, that is the intended shape: updates arrive through your
deployment pipeline, not from the endpoint reaching out. Use Intune
**supersedence** against the version detection rule above, and the installer
will upgrade in place over a previous version.

## Auditing the build

Nothing needs to be taken on trust:

```bash
git clone https://github.com/Bebop-systems/pentimento
cd pentimento
python -m pip install -r requirements.txt -r requirements-build.txt
python scripts/fetch_exiftool.py
python -m pytest -q
python desktop/build.py --installer
```

ExifTool is pinned to a specific version and fetched from the author's
SourceForge project. The application contains no other third-party binaries.
