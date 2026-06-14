## v0.3.1 — maintenance: order-independent test suite + doc fixes

> 🔁 This is the **first release delivered by auto-update** since the v0.3.0 updater fix. From v0.3.0 you should see the update bar appear → click **Install & restart now** → a visible install progress window → the app reopens itself on v0.3.1. (If anything about that doesn't happen, tell me — that's exactly what this release is here to prove.)

No change to how the app scans, reads, or talks to Open-Claw — this is housekeeping:

- **The test suite is now order-independent.** `smoke_api` and `smoke_watcher` each create and tear down their own data, so the full 14-suite check passes reliably **standalone, in any order, on a clean machine** — no more false failures that depended on another test running first.
- **Doc/comment cleanup** — stale `/VERYSILENT` references corrected to `/SILENT` (the flag the updater has actually used since v0.3.0).
- Added an internal `InboxWatcher.join()` helper used only for clean test shutdown; the app's runtime behavior is unchanged.

**14/14 smoke suites green** (now reliably, in any order). No data-format change.

**Install:** arrives via auto-update from v0.3.0; or download `OCR-Agentic-Ai_Setup_v0.3.1.exe` and run it.
