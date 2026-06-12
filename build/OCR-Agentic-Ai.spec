# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — folder mode (faster startup; updates replace the folder).

Built by build\\build.ps1; do not run pyinstaller without it (the script also
stages the bundled Tesseract and compiles the installer).
"""
from pathlib import Path

import customtkinter

ROOT = Path(SPECPATH).parent              # project root (spec lives in build\)
CTK = Path(customtkinter.__file__).parent  # bundle the whole package (pitfall #3)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "assets"), "assets"),
        (str(CTK), "customtkinter"),
    ],
    hiddenimports=[
        "google.genai",        # loaded lazily by the boost feature
        "pystray._win32",      # pystray picks its backend dynamically
        "PIL._tkinter_finder",
    ],
    excludes=["matplotlib", "scipy", "numpy.f2py", "IPython", "jupyter",
              "pytest", "sphinx", "setuptools"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="OCR-Agentic-Ai",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,                # GUI app — no console window
    version=str(ROOT / "build" / "_version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="OCR-Agentic-Ai",
)
