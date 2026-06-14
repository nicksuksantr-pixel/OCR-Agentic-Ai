# CONTEXT.md — OCR-Agentic-Ai

> Living glossary + boundaries. Updated inline during kickoff grilling (2026-06-12). English per rule #17.

## Purpose

A desktop program that performs **maximum-detail OCR** on visual inputs (photos containing text, technical drawings, diagrams, PDFs) and produces **rich raw structured data** for the Open-Claw core AI ("the Heart") to analyze further. This project is the *eyes*; Open-Claw is the *brain*. The OCR side must extract everything it can — it does NOT interpret meaning; interpretation belongs to the Heart.

## Glossary

### Source
- **Means:** any input handed to the OCR system — a photo with text/details, a technical drawing, a diagram, or a PDF file.
- **Example:** a phone photo of an electrical drawing with small component labels.

### The Heart (Open-Claw core)
- **Means:** the separate Open-Claw agentic AI (its own project, own model — being installed as of 2026-06-12) that consumes this system's output and does the analysis/thinking.
- **Not:** part of this codebase. Per rule #1 we never edit Open-Claw from here — we only define a clean hand-off interface.

### Raw Extract
- **Means:** the maximum-detail output of one Source: all recognized text with positions/confidence, assembled so the Heart can analyze it without re-seeing the image.
- **Not:** a summary or interpretation — no meaning is added at this layer.

### Sectioned Scan (Nick's core idea)
- **Means:** splitting one Source image into overlapping sections (e.g. a 3×3 grid), scanning each section at high resolution separately, then stitching the per-section results back into one Raw Extract — because whole-image OCR misses small/dense text.
- **Example:** a drawing split into a grid; tiny pin labels readable only when each tile is scanned zoomed-in.
- **Coverage (v0.2.9):** the **whole inked sheet** is tiled — there is **no pre-scan crop**, so edge content (e.g. a left title-block strip, terminal-number columns, border NOTES) is never dropped before scanning; empty border/zone tiles are filtered out of the AI queue instead, not cropped away. A **staggered offset second grid** (shifted half a tile) reads any label the main grid's cuts split, whole and with full surrounding context — Nick's blue+red dual grid; it replaces the older thin seam-strip pass. This only ADDS confidence-filtered, de-duplicated reads — never loses or duplicates one. (Not a schema change: more complete `words`/`full_text`, same fields.)

### Hybrid mode (decided 2026-06-12)
- **Means:** local OCR is ALWAYS the primary pass and must work fully offline; Gemini Vision is a booster used only on unclear sections, only when internet is available, and within free-tier limits. Local + AI results for the same section are merged into the final Raw Extract.
- **Not:** cloud-first — the system must never require internet to produce a usable Raw Extract.

### Boost Queue
- **Means:** persistent local storage of every low-confidence section — the cropped section image + its local OCR attempt — waiting to be sent to Gemini when online. After the AI answer comes back, both results are merged and the Raw Extract is updated.
- **Example:** offline on the ship → 5 blurry tiles queued; back online → sent to Gemini in small batches under RPD limits → Raw Extract upgraded.

### Symbol Tag (decided 2026-06-12, tightened same day)
- **Means:** when a Source contains a technical symbol or graphic that OCR cannot render faithfully as text, the Raw Extract writes a bracketed English descriptor instead — `(diode)`, `(resistor)`, `(diameter)` — **only when the identification is confident**.
- **Not:** a guess. Nick: a wrongly named symbol means the whole job is wrong. If unsure → write `(unknown symbol)` + send that section to the Boost Queue for AI identification when online. Never label on low confidence.
- **Example:** a schematic diode symbol → `(diode)` if confident; an unclear glyph → `(unknown symbol)` + queued crop.

### Job
- **Means:** one Source processed once, end-to-end. Each Job gets its own folder (original image, section crops, `result.json`) plus rows in the shared database.
- **Example:** `jobs\job_0001\` containing the photo, 9 section crops, and the stitched result.

### Shared Store (decided 2026-06-12)
- **Means:** the single local hand-off storage both programs use: a **SQLite database** (jobs, sections, text, confidence, Boost Queue state — queryable in sets/batches) + **asset folders on disk** (original images and section crops, referenced by path from the DB). OCR-Agentic-Ai writes; the Heart reads/pulls whatever sets it needs.
- **Not:** a server database — no installation, just files on the machine, works offline.

## Boundaries

- **In:** ingesting Sources, preprocessing, sectioning, OCR, stitching, exporting Raw Extracts, hand-off to Open-Claw.
- **Out:** semantic analysis / reasoning over the content (the Heart's job) · editing the Open-Claw project.
- **Relationship:** OCR-Agentic-Ai → produces Raw Extract into the Shared Store → consumed by Open-Claw. Interface: **both** a watched folder (`inbox\` → auto-scan) **and** a local API (localhost) — both are thin shells over the same engine; everything lands in the Shared Store either way.

## Invariants

- The Raw Extract must never silently drop a region of the Source — every section is either scanned or explicitly marked unreadable.
- Offline must always produce a usable Raw Extract (local pass) — AI Boost only upgrades it, never blocks it.
- Every unclear section keeps its cropped image on disk until the AI Boost pass has resolved it.
- Gemini usage always respects free-tier limits (RPM 15 / RPD 500) — batches are throttled, never dumped.

## Language policy (decided 2026-06-12)

- **Recognition:** local OCR reads **Thai + English** Sources.
- **System language:** everything produced for machines — Raw Extract metadata, labels, Symbol Tags, AI prompts, DB fields — is **English only** (cheaper tokens for the Heart). Recognized Thai text itself stays as-is (it is data, not labels).

## App form (decided 2026-06-12)

- CustomTkinter GUI (stack rule #14) that keeps working when the window is closed (tray/background): drop zone for manual scans, Job list + status, section/result viewer, Settings (Gemini key, AI Boost on/off). The folder watcher and local API run inside the same process. v0.0.x starts with the GUI + engine; watcher/API/tray arrive in later versions.

## Data location (Nick's order, 2026-06-12 — "installed = like a normal program")

- **Dev (run from source):** Shared Store = `<project>\data\` (as before).
- **Installed (.exe):** Shared Store = `%LOCALAPPDATA%\OCR-Agentic-Ai\` — standard Windows per-user app data; survives updates; `.env` lives there too. Folders are self-created on first run (the app heals itself if the user deletes them; the installer only helps with tessdata).
- `OCR_AGENTIC_DATA_DIR` env var overrides both (tests / custom Open-Claw setups).
- ⚠ The data location is part of the Shared Store contract with Open-Claw — moving it is a breaking change (V-Log + tell the Heart side).

## Local API (v0.0.3 — the Heart's second door)

- `http://127.0.0.1:8765` (port in Settings) — localhost only, never network-reachable. Endpoint contract documented in `src/features/api/service.py` docstring: `GET /health · /introduce · /jobs · /jobs/{id} · /jobs/{id}/result` and `POST /scan · /boost/run`. Changes to these payloads are breaking changes.
- **Auth (v0.2.4):** POST routes (`/scan`, `/boost/run`) require a shared token in the `X-OCR-Token` header — 401 without it; GET routes stay open (CORS is never granted, so a browser page cannot read a GET response either; the gap was unauthenticated POST *actions* that spend Gemini quota). The token is generated once per Shared Store (`meta.api_token`) and published in `introduction.json` + `GET /introduce` under `interfaces.api.auth`. **Open-Claw must read it from the handshake and send it on every POST** — the requirement is a breaking change for POST callers (the token field itself is additive).

## Self-introduction (v0.0.4, Nick's request — the handshake)

- **Means:** one machine-readable self-description (identity, role, Shared Store paths + schema map, both interfaces with usage, conventions) so Open-Claw can connect and self-configure from a single read.
- **Where:** `data\introduction.json` (rewritten every app start) and `GET /introduce` (always current). Adding fields is safe; renaming/removing fields is a breaking change.

## Versioning (Nick's order, 2026-06-12)

- **This project uses 3-place versioning `v0.0.0`** (Nick: version is three places, not two). Starts at `v0.0.0`; no place may exceed 9 — carry instead.
