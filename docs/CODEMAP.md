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
| Jobs off-UI-thread work (no freeze) | `src/features/jobs/controller.py` | `JobsController.run()` |
| Jobs queries / file ops / path healing | `src/features/jobs/service.py` | `job_detail()` / `resolve_job_dir()` / `archive_job()` |
| Shared design tokens (spacing/colour/fonts) | `src/shared/ui/theme.py` | constants + `font_*()` |
| Activity log + hover tooltip widgets | `src/shared/ui/widgets.py` | `ActivityLog` · `add_tooltip()` |
| One-store migration (dev↔installed) | `src/core/config/paths.py` | `migrate_legacy_store()` |
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
| Shared activity log routing + bottom strip | `src/app/app.py` | `App.log()` |
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
    • `used_today()` — Public read of today's request count — shown on the Dashboard.

### dashboard
- `src/features/dashboard/view.py`
    • `class DashboardView` — The Dashboard tab: live stat cards + a scrolling activity feed.

### jobs
- `src/features/jobs/controller.py`
    • `class JobsController` — Bridges the Jobs view and the (DB + file + image) service off the UI thread.
        ↳ run
- `src/features/jobs/service.py`
    • `recent_jobs(limit)` — Latest jobs for the list view.
    • `grouped_jobs(limit)` — Jobs grouped by Source file — a PDF's pages collapse into one group.
    • `page_of(job)` — Page number from a 'path#page=N' source, None for single images.
    • `search(term)` — Jobs whose text, source path or label contains the term.
    • `job_detail(job_id)` — One job with its sections, for the detail pane.
    • `boost_pending()` — Count of sections waiting for AI Boost.
    • `rename_job(job_id, label)` — Set/clear the user label shown in the job list.
    • `resolve_job_dir(job)` — The job's folder, healed against a stale/foreign stored path.
    • `open_data_folder()` — Open the Shared Store root in Explorer.
    • `open_job_folder(job_id)` — Open one job's folder in Explorer, healing a moved/stale path. Falls back
    • `archive_job(job_id)` — Hide a job and move its folder to jobs/_trash (recycle bin — never deleted).
    • `delete_job(job_id)` — Permanently delete one job: folder gone, all DB rows gone, AND the
    • `delete_source(source)` — Permanently delete every page-job of one Source file; returns the count.
    • `source_job_count(source)` — How many active jobs belong to one Source file (SQL, no cap).
    • `empty_trash()` — Permanently delete everything that was archived (folders in jobs/_trash
    • `original_image_path(job)` — The saved original image inside the job folder (original.*).
    • `export_text(source, dest)` — Write every page of a Source as one .txt (page headers); returns page count.
    • `export_json(source, dest)` — Combine every page's result.json of a Source into one .json list.
    • `render_overlay(job_id, upscale_min_side)` — Draw word boxes (coloured by confidence) over the original image.
- `src/features/jobs/view.py`
    • `class JobsView` — The Jobs tab: grouped, multi-selectable job list (left) + detail (right).
        ↳ refresh

### scan
- `src/features/scan/controller.py`
    • `class ScanController` — Bridges the Scan view and the pipeline; keeps the UI thread free.
        ↳ engine_ready, scan_file, pause, resume, cancel, paused
- `src/features/scan/service.py`
    • `latin_only_page(words)` — True when confident text is overwhelmingly Latin — the page is English
    • `class ScanCancelled` — Raised inside the pipeline when the user cancels a running scan.
    • `class ScanControl` — Pause/cancel signalling for a running scan — checked between sections
        ↳ pause, resume, cancel, paused, cancelled, checkpoint
    • `run_source(source_path, settings, on_progress, on_page_done, control, skip_pages)` — Process one Source of any supported kind. A PDF becomes one Job per page
    • `run_job(source_path, settings, on_progress)` — Process one Source end-to-end and persist everything to the Shared Store.
- `src/features/scan/view.py`
    • `class ScanView` — The Scan tab: select-file + progress + streamed result text.
        ↳ refresh_banners

### settings
- `src/features/settings/view.py`
    • `class SettingsView` — The Settings tab: AI Boost + OCR engine + interfaces + updates + queue.
        ↳ refresh_queue

### tray
- `src/features/tray/service.py`
    • `class TrayIcon` — Owns the pystray icon; App provides the open/quit callbacks.
        ↳ visible, start, stop

### updater
- `src/features/updater/service.py`
    • `parse_version(tag)` — 'v0.0.9' → (0, 0, 9); tolerant of missing 'v' and junk suffixes. ALWAYS a
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
