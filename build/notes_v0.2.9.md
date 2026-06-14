## v0.2.9 — read the whole sheet (no edge crop) + blue+red dual grid

Builds on v0.2.8 (auto-update or run the installer below).

### 🖼️ Nothing on the page is cropped before scanning
- The scanner used to trim to the drawing's inner border frame — which on some sheets cut off **real content at the edge**. On a Cummins CIB sheet that meant an entire left-hand **TERMINAL STRIP** column (terminal numbers + the safety NOTES about the external shutdown switch, line-monitoring resistor and E-stop) was thrown away before scanning. It now reads the **whole inked sheet**; only blank paper margin is ignored. Empty border/zone areas are still skipped intelligently, so the AI queue doesn't fill with edge noise.

### 🔵🔴 Blue + red dual grid (Nick's idea)
- A second scan grid, **offset half a tile** from the first, now runs over every page. Anything the first grid happened to slice down the middle, the offset grid reads **whole, with full context** — so a label sitting on a tile boundary comes through cleanly. Watch it live: the main grid highlights in **blue**, the offset grid in **red**. (This replaces the older thin "seam strip" pass — a full tile reads better.)
- It only ever ADDS confidence-checked, de-duplicated reads, so it can't lose or double-count a word. Scans take longer (two grids pass over the page) — deliberately, quality first.

**14/14 smoke suites green.** No data-format change — the Heart just receives more complete text.

**Install:** download `OCR-Agentic-Ai_Setup_v0.2.9.exe` and run it.
