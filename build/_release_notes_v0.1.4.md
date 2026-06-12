## Fixes & features

**No more "scanning the document edges".** The section grid now covers only the content bounding box of the page (the actual ink), not the empty paper margin. And tiles that contain nothing but frame/border lines are recognized as line-only: they are NOT queued for AI Boost and NO crop image is saved into the job folder. Job folders stay clean - only real unclear content gets kept for boosting.

**Real delete, finally.**
- Jobs tab: red "Delete" button - removes one page or ALL pages of a file (choice dialog), permanently: folder gone, database rows gone. Double-confirmed.
- Toolbar: "Empty trash" - purges everything previously archived in one click.
- "Archive" stays as the recoverable option (moves the folder to jobs\_trash).

## Install / update

Existing v0.1.3 installs pick this up automatically on next app start (installs on quit). Older versions: run the Setup exe once.
