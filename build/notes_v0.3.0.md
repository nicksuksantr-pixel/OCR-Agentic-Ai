## v0.3.0 — auto-update actually works now (and you can SEE it)

> ⚠️ **Install this one manually, once.** The broken v0.2.x updater can't deliver its own fix, so download `OCR-Agentic-Ai_Setup_v0.3.0.exe` below and run it. It upgrades in place and keeps all your scans. From v0.3.0 on, auto-update is fixed.

### 🔧 The update channel was getting stuck
- A guard meant to stop a re-install loop recorded the "latest installed" version **before the install actually ran**. If an install was ever interrupted or its UAC prompt dismissed, the app then believed it was already on a newer version than it really was — and reported **"you are on the latest version"** forever, unable to update again. That guard is gone: the app now simply compares the newest release to the version actually running, and a failed install just re-offers next time (self-healing — it also clears the stale record on start).

### 👀 You can see the update happen now
- Updates used to install **completely invisibly** — the app vanished for a minute with no sign of life, so you couldn't tell if it worked, and reopening the app early could collide with the install. Now the installer shows a **progress window**, and the app is **relaunched reliably** afterwards (with a backstop so it always comes back up).

### ✅ Uninstall (confirmed working)
- **Settings → Apps & Features → OCR Agentic AI → Uninstall** removes the program, its Start-menu and desktop shortcuts, and the Windows-startup entry. It asks before deleting your scans/results (Open-Claw reads them — keep them unless you're removing everything).

**14/14 smoke suites green.** No data-format change.

**Install:** download `OCR-Agentic-Ai_Setup_v0.3.0.exe` and run it.
