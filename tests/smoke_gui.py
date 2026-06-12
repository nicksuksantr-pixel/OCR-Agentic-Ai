"""Headless GUI smoke — build the whole window once (all tabs), then tear down."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src.app.app import App


def main() -> None:
    app = App()
    app.update()  # force one full render of every tab
    print("window:", app.title())
    print("boost pending label:", app.settings_view.queue_label.cget("text"))
    app.destroy()
    print("✅ GUI builds and tears down cleanly")


if __name__ == "__main__":
    main()
