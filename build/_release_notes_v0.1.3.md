## Fixes

**Thai gibberish on English drawings - FIXED.** Pages with no real Thai text are auto-detected after the first pass and re-scanned English-only, so Tesseract stops hallucinating stray Thai glyphs over line work. Real Thai documents still read tha+eng. (Settings > OCR > Auto language detect, on by default.)

**"Closed and reopened - no update" - FIXED.** The updater used to check GitHub only once per day, so same-day releases were invisible. It now checks on every app start, and Settings > Updates has a "Check now" button.

**Interrupted batch = lost work - FIXED.** Quitting mid-PDF used to kill the batch with no way back. Now: stuck jobs are closed out on next start, and re-picking the same PDF offers "skip the N pages already scanned" so a 45-page run resumes where it stopped.

## Install / update

This release still requires ONE manual install (older versions carry the once-per-day check). Run the Setup exe below - after that, every future release lands automatically on app start.
