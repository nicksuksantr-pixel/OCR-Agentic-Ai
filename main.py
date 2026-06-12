"""Thin entry point — everything lives in src/ (rule #14).

Single-instance guard: a named Windows mutex stops double launches (two tray
icons / two watchers fighting over the inbox) and lets the silent updater know
when the app has fully exited.
"""
import ctypes
import sys

MUTEX_NAME = "OCR-Agentic-Ai-single-instance"
ERROR_ALREADY_EXISTS = 183


def already_running() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if already_running():
        sys.exit(0)  # another instance owns the tray icon already
    from src.app.app import run
    run()
