#!/usr/bin/env bash
# install.sh — one-command setup: system packages + the Python package.
#
# What it does, in order:
#   1. Detects X11 vs Wayland and installs the right system packages via apt.
#   2. Installs this package with pip in editable mode, with the "all"
#      extra (pynput/pystray/pillow) so paste-on-hold, tag hotkeys, and
#      the tray icon all work out of the box.
#
# Safe to re-run — every step is idempotent.

set -euo pipefail

echo "== highlight-scraper install =="

# python3-pip: some distros only ship `pip3`/`python3 -m pip`, not a bare
#   `pip` on PATH — we call it via `python3 -m pip` below regardless, but
#   the module itself still has to be installed.
# python3-dev, build-essential: pynput pulls in `evdev` on Linux, which
#   compiles a small C extension against Python.h — missing these two is
#   why that step fails with "fatal error: Python.h: No such file or
#   directory" rather than anything wrong with pynput itself.
# python3-tk: tkinter (the GUI front end's toolkit) is NOT part of the
#   Python standard library on Debian/Ubuntu — it's split into its own
#   apt package. Without it, `highlight-scraper-gui` fails with
#   "ModuleNotFoundError: No module named 'tkinter'" even inside a venv,
#   since a venv inherits the system Python's stdlib rather than bundling
#   its own. The CLI and tray front ends don't need it.
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    echo "Wayland session detected."
    SYSTEM_PACKAGES="wl-clipboard xdotool python3-pip python3-dev python3-tk build-essential"
    echo "Note: xdotool (source-window attribution) and paste/hotkeys need"
    echo "X11 — they won't work under Wayland. Capture itself still will."
else
    echo "X11 session detected."
    SYSTEM_PACKAGES="xclip python3-xlib xdotool python3-pip python3-dev python3-tk build-essential"
fi

echo "Installing system packages: $SYSTEM_PACKAGES"
sudo apt update
sudo apt install -y $SYSTEM_PACKAGES

echo
echo "Installing the Python package (editable, with optional extras)..."
# `python3 -m pip` instead of a bare `pip` call — works whether or not
# a `pip` command is on PATH, and works the same whether you're inside
# an activated venv or installing system-wide. Quoting .[all] so the
# shell doesn't try to glob-expand the brackets.
python3 -m pip install -e '.[all]' --break-system-packages

echo
echo "Done. Try:"
echo "  highlight-scraper start --session my-first-session"
echo "  highlight-scraper-gui"
echo "  highlight-scraper-tray"
echo
echo "Run the test suite with: python3 -m pip install pytest --break-system-packages && pytest"
