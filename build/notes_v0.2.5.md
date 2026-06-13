## v0.2.5 — security + reliability (Tester audit backlog; Medium tier via Lucifer)

Bundles **v0.2.4 + v0.2.5** (previous release was v0.2.3). Existing installs auto-update on the next check; or run the installer below.

### 🔒 Local API now authenticated (v0.2.4) — ⚠ breaking for API POST callers
- `POST /scan` and `POST /boost/run` now require an **`X-OCR-Token`** header → **401** without it. GET routes are unchanged.
- The token is published in `GET /introduce` + `introduction.json` under `interfaces.api.auth` (stable per store).
- Closes the gap where any local process or a browser localhost-fetch could trigger scans or spend your Gemini quota.
- **Open-Claw integrators:** read the token from the handshake and send the header on POST — see `docs/OPEN-CLAW-HANDOFF.md`.

### 🛠 Settings + reliability (v0.2.5)
- **OCR language picker** in Settings + a warning if a selected language isn't installed (no more silent scan-death on a portable run without `tha`).
- **Paid-tier + model** now persist the moment you change them (no need to click Save).
- Save now states that **watch-inbox / Local API** changes apply after restart.
- With AI Boost on but **no key**, scans no longer pile up undrainable boost items — local text stays complete.

### ✅ Quality
- New `unrotate_box` round-trip test; **14/14 smoke suites green**.

**Install:** download `OCR-Agentic-Ai_Setup_v0.2.5.exe` and run it (verify against the `.sha256` if you like).
