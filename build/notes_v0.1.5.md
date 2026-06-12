# v0.1.5 — Smart page-aware scanning

The Sectioned-Scan grid is now driven by the REAL document, not raw pixels:

- **Paper-size grid** — the physical page size (mm) is measured before every scan; tiles target ~11 cm of paper. An A4 splits ~2×3, an A3 ~3×4 — no more shredding small pages into 15 tiny edge tiles.
- **Whole-page orientation** — pages whose content is rotated inside the PDF (common in drawing sets) are detected empirically and turned upright before scanning. Rotated drawing pages go from garbage to fully readable.
- **Frame-aware tiling** — the drawing's border frame and zone-letter strips are detected and excluded; tiles cover only the content inside the frame.
- **Valley-snapped cuts** — grid cuts move to the emptiest nearby gap so they split between content instead of through words.
- **Seam pass** — a wide strip across every grid cut is scanned separately, so labels sitting exactly on a tile boundary are read whole.
- **Smarter AI queue** — tile verdicts are made after stitching all passes; tiles already solved by the full/seam pass and tiles containing only ruled table/frame lines are no longer sent to AI Boost.
- result.json gains additive fields `page_rotation` and `page_size_mm`; the overlay viewer follows the page rotation.

Full smoke-test regression green (12 suites, incl. new smoke_grid 15/15).
