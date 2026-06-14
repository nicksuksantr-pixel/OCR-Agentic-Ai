"""The ONE supported-Source extension allow-list.

Defined here in core so every ingest door — GUI picker, inbox watcher, local API —
and the /introduce handshake all derive from a single source and can never drift
apart (audit P3: the set was previously copy-pasted into three files). Core owns it
because `introduce` (core) advertises it and cannot import a feature module.
"""

SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}

# Bare extensions (no leading dot), sorted — the form the Open-Claw handshake
# advertises in introduction.json `interfaces.scan.formats`.
FORMAT_LIST = sorted(ext.lstrip(".") for ext in SUPPORTED_EXT)
