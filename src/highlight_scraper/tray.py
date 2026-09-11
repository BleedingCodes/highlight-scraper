#!/usr/bin/env python3
"""
tray.py — system tray icon: the "just leave it running" daily-driver
front end, as an alternative to a terminal (cli.py) or a full window
(gui.py).

Menu: Start, Pause capture, Stop, Open data folder, Quit.

Unlike cli.py, this doesn't spawn a background subprocess or use a PID
file — the tray icon process IS the running app for as long as it sits
in your system tray, so there's nothing extra to manage.

Requires: pip install pystray pillow --break-system-packages
"""

import subprocess
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from highlight_scraper.config import load_config
from highlight_scraper.session_manager import CaptureSession


def _dot(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


ICON_STOPPED = _dot((150, 150, 150, 255))
ICON_ACTIVE = _dot((60, 170, 90, 255))
ICON_PAUSED = _dot((210, 170, 40, 255))


class TrayApp:
    def __init__(self):
        self.config = load_config()
        self.session = None
        self.icon = pystray.Icon(
            "highlight_scraper", ICON_STOPPED, "Highlight Scraper (stopped)",
            menu=self._build_menu(),
        )

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Start", self._start,
                              enabled=lambda item: self.session is None),
            pystray.MenuItem("Pause capture", self._toggle_pause,
                              checked=lambda item: bool(self.session and self.session.paused),
                              enabled=lambda item: self.session is not None),
            pystray.MenuItem("Stop", self._stop,
                              enabled=lambda item: self.session is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open data folder", self._open_data_folder),
            pystray.MenuItem("Quit", self._quit),
        )

    def _start(self, icon=None, item=None):
        session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session = CaptureSession(self.config["db_path"], session_name, self.config)
        try:
            self.session.start()
        except RuntimeError as e:
            self.session = None
            self.icon.notify(str(e), "Highlight Scraper — error")
            return
        self.icon.icon = ICON_ACTIVE
        self.icon.title = f"Highlight Scraper — {self.session.watcher.backend_name}"
        self.icon.update_menu()

    def _toggle_pause(self, icon=None, item=None):
        if not self.session:
            return
        self.session.toggle_pause()
        self.icon.icon = ICON_PAUSED if self.session.paused else ICON_ACTIVE
        self.icon.update_menu()

    def _stop(self, icon=None, item=None):
        if self.session:
            self.session.stop()
            self.session = None
        self.icon.icon = ICON_STOPPED
        self.icon.title = "Highlight Scraper (stopped)"
        self.icon.update_menu()

    def _open_data_folder(self, icon=None, item=None):
        folder = str(Path(self.config["db_path"]).parent)
        subprocess.Popen(["xdg-open", folder])

    def _quit(self, icon=None, item=None):
        self._stop()
        self.icon.stop()

    def run(self):
        self.icon.run()


def main():
    TrayApp().run()


if __name__ == "__main__":
    main()
