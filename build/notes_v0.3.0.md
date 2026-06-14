## v0.3.0 — auto-update fixed (and visible) + a full reliability pass

> ⚠️ **Install this one manually, once.** The broken v0.2.x updater can't deliver its own fix, so download `OCR-Agentic-Ai_Setup_v0.3.0.exe` below and run it. It upgrades in place and keeps all your scans. From v0.3.0 on, auto-update works.

### 🔧 Auto-update
- **No longer gets stuck.** A guard recorded the "latest installed" version *before* the install actually ran, so an interrupted or UAC-dismissed update made the app think it was already newer than it was — and it then said **"you are on the latest version"** forever. Fixed: it now compares to the version actually running, and a failed install just re-offers next time (self-healing).
- **You can see it happen.** Updates used to install invisibly (the app vanished for a minute with no sign of life). Now the installer shows a **progress window** and the app **relaunches reliably** afterwards.
- **Uninstall** (confirmed working): Apps & Features → OCR Agentic AI → Uninstall removes the program, shortcuts and the Windows-startup entry, and asks before deleting your scans.

### 🤖 AI Boost
- **Sections you scanned before turning Boost on can now be sent — no re-scan.** Previously, anything scanned while Boost was off was stranded on disk; "Send Boost Queue now" did nothing for it. Now every unclear section with a saved crop is picked up automatically the next time the queue drains.
- **Flaky-link hardening:** the Gemini call now has a timeout (a stalled marine/mobile connection used to freeze all future Boost runs until restart); a request that never completes no longer burns a daily-cap slot; the daily counter is written crash-safely.

### 📥 Inbox watcher
- **No more duplicate jobs.** A re-dropped file, or one left half-scanned across a restart, now resumes (skips finished PDF pages / already-scanned images) instead of re-scanning from page 1.
- **One bad page no longer loses the rest.** If a single PDF page errors, the remaining pages still scan (the file used to be dropped to `failed\` whole).

### 🧹 Internal
- One shared list of supported file types across all three doors (no drift); a wrong/changed Tesseract path is now picked up without a restart; minor cleanups.

**14/14 smoke suites green.** No data-format change — the Heart just receives more complete, more reliable extraction.

**Install:** download `OCR-Agentic-Ai_Setup_v0.3.0.exe` and run it.
