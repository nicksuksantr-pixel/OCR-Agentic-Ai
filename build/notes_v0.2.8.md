## v0.2.8 — quality pass

Builds on v0.2.7 (auto-update or run the installer below).

### 🔎 Extraction quality
- **Seam scanning is more thorough** — the pass that reads text sitting exactly on a tile boundary no longer skips a seam just because text there is sparse, so a label crossing a grid cut is more likely to be read whole. It can only add readings (everything is confidence-filtered and de-duplicated), never drop one.

### 🧾 Data consistency
- **`created_at` now matches** between a job's `result.json` and the database row (previously the file recorded the time the scan *finished*, which for a long page differed from the DB by minutes).

Both changes are additive and contract-safe. **14/14 smoke suites green.**

**Install:** download `OCR-Agentic-Ai_Setup_v0.2.8.exe` and run it.
