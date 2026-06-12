# CODEMAP — OCR-Agentic-Ai

## Layer A — where to edit (hand-written)

| Task | File | Entry point |
|---|---|---|
| Change OCR pipeline (sectioning/stitch/queueing) | `src/features/scan/service.py` | `run_source()` → `run_job()` → `_scan()` |
| Change the self-rescue variants / order | `src/features/scan/service.py` | `_rescue()` |
| Change adaptive grid / binarize / rotation math | `src/core/utils/imaging.py` | `auto_grid()` / `binarize()` / `unrotate_box()` |
| Change preprocessing or tiling math | `src/core/utils/imaging.py` | `preprocess()` / `grid_sections()` |
| Change PDF rendering (DPI, page cap) | `src/core/utils/pdfio.py` | `render_page()` / `PDF_DPI` |
| Swap or tune the local OCR engine | `src/core/services/engine.py` | `configure()` / `ocr_words()` |
| Change DB schema / Shared Store queries | `src/core/services/store.py` | `_SCHEMA` + helpers |
| Change data shapes (Word/Section/Job) | `src/core/models/ocr.py` | dataclasses |
| Change defaults (grid, threshold, languages) | `src/core/config/settings.py` | `Settings` |
| Change file locations | `src/core/config/paths.py` | constants |
| Scan tab UI | `src/features/scan/view.py` | `ScanView` |
| Scan threading/orchestration | `src/features/scan/controller.py` | `ScanController.scan_file()` |
| Jobs tab UI | `src/features/jobs/view.py` | `JobsView` |
| Jobs queries for UI | `src/features/jobs/service.py` | `recent_jobs()` / `job_detail()` |
| Change the Gemini call / prompt / .env key handling | `src/core/services/gemini.py` | `boost_section()` / `BOOST_PROMPT` |
| Change Boost throttle / merge / daily cap | `src/features/boost/service.py` | `send_pending()` |
| Boost threading for the GUI | `src/features/boost/controller.py` | `BoostController` |
| Settings tab UI | `src/features/settings/view.py` | `SettingsView` |
| Change inbox watching (poll/stability/move rules) | `src/features/watcher/service.py` | `InboxWatcher` |
| Change the Open-Claw API (endpoints/contract) | `src/features/api/service.py` | `ApiServer._route_get/_route_post` |
| Change the self-introduction payload (handshake) | `src/core/services/introduce.py` | `build_introduction()` |
| System tray (hide-on-close, Open/Quit menu) | `src/features/tray/service.py` | `TrayIcon` |
| Auto-update (check/stage/apply, GitHub Releases) | `src/features/updater/service.py` | `AutoUpdater` |
| Release build pipeline | `build\build.ps1` (+ `OCR-Agentic-Ai.spec` · `installer.iss` · `make_icon.py`) | run build.ps1 |
| Window shell / tabs / close-to-tray wiring | `src/app/app.py` | `App` · `_on_close()` |
| Headless tests | `tests/smoke_*.py` (pipeline · boost · gui · watcher · api · pdf · tray · rescue · updater) | `main()` |
| Regenerate this map (layer B) | `gen_codemap.py` | run before every build |

## Layer B — per feature (auto-generated)

<!-- CODEMAP:AUTO:START -->
### api
- `src/features/api/service.py`
    • `class ApiServer` — Owns the HTTP server thread; one instance per app.
        ↳ running, start, stop

### boost
- `src/features/boost/controller.py`
    • `class BoostController` — Bridges Settings/Scan views and the Boost sender; keeps the UI thread free.
        ↳ send_pending, auto_send
- `src/features/boost/service.py`
    • `class BoostRunSummary` — What one drain run did — shown in the UI and logged.
    • `send_pending(settings, on_progress)` — Send every pending Boost Queue item to Gemini, oldest first, until done,

### jobs
- `src/features/jobs/service.py`
    • `recent_jobs()` — Latest jobs for the list view.
    • `job_detail(job_id)` — One job with its sections, for the detail pane.
    • `boost_pending()` — Count of sections waiting for AI Boost.
- `src/features/jobs/view.py`
    • `class JobsView` — The Jobs tab: refreshable job list (left) + detail viewer (right).
        ↳ refresh

### scan
- `src/features/scan/controller.py`
    • `class ScanController` — Bridges the Scan view and the pipeline; keeps the UI thread free.
        ↳ engine_ready, scan_file
- `src/features/scan/service.py`
    • `run_source(source_path, settings, on_progress, on_page_done)` — Process one Source of any supported kind. A PDF becomes one Job per page
    • `run_job(source_path, settings, on_progress)` — Process one Source end-to-end and persist everything to the Shared Store.
- `src/features/scan/view.py`
    • `class ScanView` — The Scan tab: select-file button + progress label + result textbox.

### settings
- `src/features/settings/view.py`
    • `class SettingsView` — The Settings tab: AI Boost configuration + manual queue drain.
        ↳ refresh_queue

### tray
- `src/features/tray/service.py`
    • `class TrayIcon` — Owns the pystray icon; App provides the open/quit callbacks.
        ↳ visible, start, stop

### updater
- `src/features/updater/service.py`
    • `parse_version(tag)` — 'v0.0.9' → (0, 0, 9); tolerant of missing 'v' and junk suffixes.
    • `fetch_latest_release(repo, timeout)` — GET the latest release metadata from the GitHub API (None on any failure).
    • `pick_assets(release)` — Find the Setup exe asset and its optional .sha256 sibling.
    • `download(url, dest, timeout)` — 
    • `sha256_of(path)` — 
    • `make_apply_script(setup_path, app_exe)` — Write the detached updater script: wait for app exit → silent install → relaunch.
    • `class AutoUpdater` — Owns the staged update state; App calls check_async() at start and
        ↳ check_async, apply_on_exit

### watcher
- `src/features/watcher/service.py`
    • `class InboxWatcher` — Background thread that turns files dropped in inbox\ into Jobs.
        ↳ running, start, stop
<!-- CODEMAP:AUTO:END -->
