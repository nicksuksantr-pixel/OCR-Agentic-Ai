## v0.2.7 — UI/UX + bug fixes

Builds on v0.2.6 (auto-update or run the installer below).

### 🖱️ UX / data safety
- **A running scan is no longer lost silently on exit** — quitting (window or tray menu) or clicking "Install & restart now" while a scan is in progress now warns you first and, if you confirm, stops cleanly so every finished page is saved.
- **Missing OCR language is handled gracefully** — if a selected language model isn't installed, scans fall back to the languages that are (an English page still reads on `eng`) instead of failing, and the Scan tab warns you up front.
- **Re-scanning an archived image** now prompts the same way a PDF page does on resume (no more silent duplicate jobs).

### ⚡ Polish
- Dashboard / Settings stop refreshing the database and inbox every 2 s while the app is hidden in the tray.
- Hover tooltips on the update bar's buttons.

Reviewed by the Lucifer 3-agent relay; every change verified against the live code. **14/14 smoke suites green.**

**Install:** download `OCR-Agentic-Ai_Setup_v0.2.7.exe` and run it.
