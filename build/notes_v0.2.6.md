## v0.2.6 — Tester audit fixes

Builds on v0.2.5 (auto-update or run the installer below).

### 🔒 Reliability / data-integrity (P1)
- **Inbox watcher & local API now configure the OCR engine themselves** — previously they relied on the GUI tab opening first, so a file dropped in the inbox (or an API scan) could fail with a raw "tesseract not installed" if the Scan tab hadn't initialised the engine.
- **No more silent drops on AI Boost** — an empty or "(nothing readable)" AI answer no longer closes a section as done with empty text; the section is left unresolved so a re-scan can still address it.
- **AI-merge can't lose a reading** — a section whose AI text happened to contain a "section N:" line could make a *later* section's real reading vanish; readings are now collapsed to one line so only true headers match (raw text is still kept in `ai_boosts`).

### 🛠 Hardening (P2 / P3)
- API `POST /scan` rejects non-image/PDF files with a clean 400 instead of creating junk error-jobs.
- AI Boost only queues work when Boost is **enabled** and a key is set (no more swelling queue when Boost is off).
- A rejected API key no longer burns the daily request cap.
- Delete no longer risks removing a different file's processed copy; `GET /jobs?limit` is bounded (1–1000).

Audited by the 3-agent Tester pass; every fix verified against the live code. **14/14 smoke suites green.**

**Install:** download `OCR-Agentic-Ai_Setup_v0.2.6.exe` and run it (verify against the `.sha256` if you like).
