# ADR-001 — Distribution & Auto-Update

**Status:** accepted (Nick, 2026-06-12) · **Version:** introduced in v0.0.9

## Decisions (Nick's choices)

| Question | Decision |
|---|---|
| Update channel | **GitHub Releases** (repo set in Settings → `update_repo`; empty = updater off) |
| Install scope | **All users — `C:\Program Files\OCR-Agentic-Ai\`** (admin) |
| Update behavior | **Fully silent** — staged in background, installs on app exit, relaunches |

## Architecture

```
build\build.ps1  (one command)
  icon → CODEMAP → PyInstaller (folder mode) → stage Tesseract → Inno Setup → SHA-256
  ⇒ dist\installer\OCR-Agentic-Ai_Setup_vX.Y.Z.exe  (+ .exe.sha256)

GitHub Release (tag vX.Y.Z, both files attached)
  ⇓  daily check (data\update_check.json throttle)
AutoUpdater (src\features\updater\service.py)
  newer tag → download to %TEMP% → verify SHA-256 → STAGE
  on app quit → detached bat: wait-for-exit → Setup /SILENT → relaunch
```

## Key points

- **Installer (Inno Setup 6):** fixed AppId GUID → in-place upgrades · modern wizard ·
  versioned exe metadata · optional desktop icon + all-users autostart (HKLM Run) ·
  `CloseApplications=force` + taskkill on uninstall · uninstaller asks before deleting
  the Shared Store (silent uninstall always keeps data — Open-Claw reads it).
- **Bundled Tesseract:** engine + tha/eng/osd models ship inside `{app}\tesseract\` —
  end users install nothing else. Resolution: Settings path → bundled → PATH.
  Models staged from the project's `data\tessdata` (winget Tesseract is English-only).
- **Single instance:** named mutex in `main.py` — no double tray icons; lets the
  updater script know when the app has fully exited.
- **Data location unchanged:** `%LOCALAPPDATA%\OCR-Agentic-Ai\` per user (the
  Open-Claw contract) — installs/updates never touch it.

## Accepted trade-offs

- **One UAC consent popup per update** — Program Files needs admin; Windows will not
  allow a truly invisible elevation (by design; bypassing it is malware behavior).
- **Unsigned binaries** — SmartScreen may warn on other machines ("More info → Run
  anyway"). A code-signing certificate (~$100+/yr) removes this; not bought for now.
- **Per-user autostart vs machine install:** autostart task writes HKLM (all users).

## Operating the release channel

1. Bump `APP_VERSION` in `src\app\app.py` → run `build\build.ps1`.
2. Create a GitHub release tagged `vX.Y.Z`; upload **both** the Setup exe and the
   `.sha256` sidecar (asset names must keep the `OCR-Agentic-Ai_Setup_` prefix).
3. Installed apps pick it up within a day (or instantly on next app start).

**Prerequisite still open:** the GitHub repo itself — Nick creates it (or approves
creation), then sets `owner/repo` in Settings → Updates.
