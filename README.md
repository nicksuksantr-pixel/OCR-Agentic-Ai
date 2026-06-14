# OCR-Agentic-Ai

**The eyes of Open-Claw** — a desktop program that performs maximum-detail OCR on photos, technical drawings, diagrams and PDFs, and writes rich Raw Extracts into a local Shared Store (SQLite + job folders) for the Open-Claw core AI ("the Heart") to analyze.

## Stack & version

- Python 3.13 + CustomTkinter 5.2.2 · Tesseract OCR (local, offline, tha+eng) · SQLite
- Current version: **v0.2.6** (3-place versioning per Nick, 2026-06-12) · releases: [github.com/nicksuksantr-pixel/OCR-Agentic-Ai](https://github.com/nicksuksantr-pixel/OCR-Agentic-Ai/releases)
- Gemini AI Boost: AI Studio key in `.env` (`GEMINI_API_KEY=...`), default model `gemini-3.1-flash-lite`, free-tier throttled (15 RPM / 500 RPD)

## Run / build

```powershell
# run (dev)
.venv\Scripts\python.exe main.py

# smoke tests (headless)
.venv\Scripts\python.exe tests\smoke_pipeline.py   # local OCR pipeline
.venv\Scripts\python.exe tests\smoke_boost.py      # Boost sender, Gemini faked (offline)
.venv\Scripts\python.exe tests\smoke_boost.py --live  # one real Gemini request
.venv\Scripts\python.exe tests\smoke_gui.py        # window builds all tabs
.venv\Scripts\python.exe tests\smoke_watcher.py    # inbox auto-scan loop
.venv\Scripts\python.exe tests\smoke_api.py        # local API, all endpoints
.venv\Scripts\python.exe tests\smoke_pdf.py        # PDF → one job per page
.venv\Scripts\python.exe tests\smoke_tray.py       # close-to-tray / restore / quit
.venv\Scripts\python.exe tests\smoke_rescue.py     # self-rescue: vertical/inverted/tiny text
.venv\Scripts\python.exe tests\smoke_manage.py     # jobs browser: search/label/archive/export/overlay/pause-cancel
.venv\Scripts\python.exe tests\smoke_lang.py       # auto language detect / batch resume / orphan cleanup
```

- First-time setup: `python -m venv .venv` → `pip install -r requirements.txt` → Tesseract via `winget install UB-Mannheim.TesseractOCR` → language models already in `data\tessdata\` (eng/tha/osd).
- **Release build (one command):** `powershell -ExecutionPolicy Bypass -File build\build.ps1` → `dist\installer\OCR-Agentic-Ai_Setup_vX.Y.Z.exe` + `.sha256`. Installer bundles Tesseract+models (end users install nothing else), installs to Program Files, optional autostart. Release = GitHub release tagged `vX.Y.Z` with both files attached (see `docs\adr\ADR-001`).

## Features

- **Scan (deep-detail)** — pick an image or PDF → preprocess (upscale to ≥2000 px) → dual full pass (block + sparse) + overlapping Sectioned Scan (3× zoom, dual pass per tile, grid auto-scales up to 7×7 and covers only the **content bounding box**, not the paper margin; tiles holding only frame/border lines are never queued or saved) → stitched Raw Extract (text + positions + confidence). A PDF becomes one Job per page (rendered at 400 DPI via pypdfium2; source recorded as `path#page=N`). Deliberately slow and thorough (Nick's order, v0.0.8).
- **Self-rescue (deep merge)** — sections below the quality bar (`rescue_trigger_conf` 75) run ALL local variants and merge the union: 4× zoom → Otsu binarize → sparse mode → inversion (white-on-black) → 90°/270° rotation (vertical labels). Below `low_conf_threshold` 60 they still queue for AI Boost. Rescued sections carry `rescued`/`rescue_method` in result.json.
- **Live page streaming** — multi-page PDFs show each page's result the moment it finishes (Scan tab streams, Jobs list refreshes live); scans can be **paused/resumed/cancelled** mid-batch (finished pages are kept). Re-picking a partially scanned PDF offers **batch resume** (skips finished pages); jobs orphaned by an app exit are auto-marked on next start.
- **Auto language detect** — pages with no real Thai text re-run English-only, eliminating Thai-glyph hallucination on line drawings (`auto_language` setting, default on; `languages_used` recorded in result.json).
- **Jobs browser** — scans grouped per Source file (a PDF's pages collapse into one expandable group), full-text **search**, image **preview**, **overlay viewer** (word boxes coloured by confidence — green ≥75 / yellow ≥60 / red <60, saved as `overlay.png`), **open job folder / data folder** in Explorer, per-job **label/tag**, **export** a whole Source as `.txt`/`.json`, copy text, **archive** (folder → `jobs\_trash`), **delete** (one page, the whole file, or any **multi-selection** via per-row checkboxes — permanent, confirmed), **Empty trash**. Every operation runs off the UI thread so the tab never freezes (v0.2.0).
- **Dashboard** — live library stats (jobs / avg confidence / inbox processed+failed), current batch progress with ETA, AI Boost budget used today vs cap, and a scrolling **Activity log**: every background event (scan, inbox watcher, local API, updater, AI Boost) is timestamped here with a source tag (also echoed on the always-visible bottom status strip). Auto-refreshes.
- **AI Boost** — unclear sections queue on disk + DB; when online (and enabled in Settings) they are sent to Gemini one-by-one under free-tier limits and the answers are merged back into the Raw Extract (`[AI Boost]` block + `ai_boosts` in result.json). Auto-runs after each scan, or manually via Settings → "Send Boost Queue now".
- **Settings** — Gemini key (stored in `.env`), model dropdown (8 main Gemini models), **paid-tier unlock** (consent dialog: no throttle, no daily cap, all models; locked = forced `gemini-3.1-flash-lite`), daily request cap, AI Boost on/off, inbox watcher on/off, API on/off + port, tray on/off.
- **Inbox watcher** — drop an image or PDF into `data\inbox\` → scanned automatically; originals move to `inbox\processed` (or `inbox\failed`), never deleted.
- **Local API for Open-Claw** — `http://127.0.0.1:8765`: `GET /health · /introduce · /jobs · /jobs/{id} · /jobs/{id}/result`, `POST /scan · /boost/run`. Localhost only.
- **Self-introduction (handshake)** — `data\introduction.json` (refreshed every start) + `GET /introduce`: identity, Shared Store paths/schema, interfaces and conventions in one machine-readable document — Open-Claw self-configures from one read.
- **Tray mode** — closing the window hides the app to the system tray; watcher + API keep serving Open-Claw. Tray menu: Open / Quit. Single-instance (mutex).
- **Auto-update (visible + one-click, v0.2.1)** — GitHub-Releases check on every start **and every 6 h** (so a tray-resident app still updates). When a newer Setup is downloaded and SHA-256-verified, a **prominent update bar** appears across the top — "🔄 Update vX ready" + **[⬇ Install & restart now]** + [Later]; Settings → Updates shows the installed version + a live status + the same Install button. Clicking it installs immediately and relaunches (no manual Quit). One UAC popup per update (Program Files — Windows requirement).
- **Data location** — ONE Shared Store for both dev and installed runs: `%LOCALAPPDATA%\OCR-Agentic-Ai\` (`OCR_AGENTIC_DATA_DIR` overrides — tests use a throwaway store). Before v0.2.0 dev and installed diverged, which made "open folder" land on the wrong tree and deleted jobs seem to reappear; the legacy `<project>\data` store is migrated once on first run.
- **Branding** — icon (scanning eye) = identity: taskbar/installer/shortcuts. Mascot "Scout" (one-eyed scanner robot, `assets\mascot.png`) = helper: Scan tab + installer wizard pages. Never swap roles (#3). Regenerate: `build\make_icon.py` / `build\make_mascot.py`.

## 🧭 Doc map

| File | Job |
|---|---|
| [CONTEXT.md](CONTEXT.md) | requirements, glossary, design decisions (grill output) |
| [docs/CODEMAP.md](docs/CODEMAP.md) | which file/function to edit — open before every change |
| [V-Log.md](V-Log.md) | version timeline |
| [memory/MEMORY.md](memory/MEMORY.md) | session-start snapshot (read first every session) |
| `data\` | Shared Store: `ocr.db` + `jobs\job_NNNN\` + `inbox\` + `tessdata\` |
