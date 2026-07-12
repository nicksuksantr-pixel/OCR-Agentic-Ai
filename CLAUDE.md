# CLAUDE.md — OCR-Agentic-Ai (project-specific rules)

> **🔗 Rules-in-repo bootstrap (command_pattern #22, added 2026-07-12).** Any instance — local Coddy OR cloud/GitHub — must follow this:
> **⚡ Session start → read `memory/MEMORY.md` + the newest `chat_log/` file, then `memory/nick-workflow.md` (the synced master-rule brief — currently command_pattern v3.12/24). Follow them.** · chat = **Thai** · records = **English** (#17).
> ⛔ **Agent cap (#16):** ≤3/round · max 5 · >5 STOP+ask · never self-start Tester/Lucifer/supertester (only on Nick's typed trigger) · FAIL = STOP (1 trigger = 1 launch, never blind-retry).
> 🔄 **Git (#20/#21):** session start → `git fetch`, `git pull --ff-only` if behind (diverged = STOP, never force-push) · task done → `git commit` + `git push` automatically (code **and** records).
> 🔐 **Security = approve-before-fix (#24):** the **"supertester security"** review audits **READ-ONLY** → presents a fix plan + per-fix blast-radius → **WAITS for Nick's approval** → fixes on a security branch (backup first) → **never auto-build/deploy**. ❌ Never auto-fix like Tester/supertester.

---

> Universal rules live in `command_pattern.md` (via `memory\MEMORY.md`). Only project extras here.

- **Versioning (Nick, 2026-06-12):** this project uses **3-place `vX.Y.Z`** starting `v0.0.0` — now matches #14.7 (the central rule reverted from 2-place back to 3-place on 2026-06-12; was a project-only override before that). No place exceeds 9, carry instead.
- **Role:** this app is the *eyes* — it extracts, it never interprets. Anything that "understands" content belongs to Open-Claw (the Heart), a separate project we never edit (rule #1).
- **Offline-first invariant:** local OCR must always produce a usable Raw Extract with no internet. Gemini is only a booster for queued unclear sections, throttled under free-tier limits.
- **Never guess symbols:** unconfident symbol → `(unknown symbol)` + Boost Queue. A wrong symbol label = a wrong job (Nick).
- **Shared Store contract:** Open-Claw reads `data\ocr.db` + `data\jobs\job_NNNN\` — schema changes are breaking changes; bump version and note them in V-Log.
- Python venv: `.venv\` · run `main.py` · headless test `tests\smoke_pipeline.py`.
