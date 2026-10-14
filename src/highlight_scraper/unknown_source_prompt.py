"""Small fail-closed prompt used when desktop front ends lack attribution."""

import json
import logging
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)


def prompt_unknown_source(source_window=None, parent=None):
    """Ask on Tk's main thread without showing the highlighted text.

    The GUI passes its existing Tk parent and displays the dialog directly.
    CLI and tray callbacks run on worker threads, so they use a child process
    to ensure Tk is created on that process's main thread.
    """
    if parent is None:
        completed = None
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "highlight_scraper.unknown_source_prompt"],
                input=json.dumps({"source_window": source_window}),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                decision = json.loads(completed.stdout)
                if decision.get("action") in ("continue", "name", "discard"):
                    return decision
        except (OSError, json.JSONDecodeError):
            logger.exception("Could not open the unknown-source prompt; capture discarded")
        if completed is not None and completed.returncode != 0:
            logger.error("Unknown-source prompt exited with status %s; capture discarded",
                         completed.returncode)
        return {"action": "discard", "label": "", "remember": False}
    return _show_prompt(source_window, parent)


def _show_prompt(source_window=None, parent=None):
    own_root = parent is None
    win = tk.Tk() if own_root else tk.Toplevel(parent)
    root = win if own_root else parent
    win.title("Unknown highlight source")
    win.resizable(False, False)
    if not own_root:
        win.transient(root)

    result = {"action": "discard", "label": "", "remember": False}
    ttk.Label(
        win,
        text="The source app could not be identified. This highlight has not been saved.",
        font=("TkDefaultFont", 10, "bold"),
        wraplength=390,
    ).grid(row=0, column=0, columnspan=3, padx=16, pady=(16, 8), sticky="w")
    ttk.Label(win, text=f"Window title: {source_window or 'unavailable'}",
              wraplength=390).grid(row=1, column=0, columnspan=3,
                                   padx=16, pady=(0, 10), sticky="w")

    name_var = tk.StringVar()
    ttk.Label(win, text="Source name (for this capture):").grid(
        row=2, column=0, padx=(16, 6), pady=4, sticky="w")
    entry = ttk.Entry(win, textvariable=name_var, width=28)
    entry.grid(row=2, column=1, columnspan=2, padx=(0, 16), pady=4, sticky="ew")
    remember_var = tk.BooleanVar(value=False)
    remember = ttk.Checkbutton(win, text="Remember this source by window title",
                               variable=remember_var)
    remember.grid(row=3, column=0, columnspan=3, padx=16, pady=(4, 10), sticky="w")
    if not source_window:
        remember.configure(state="disabled")

    buttons = ttk.Frame(win)
    buttons.grid(row=4, column=0, columnspan=3, padx=16, pady=(0, 16), sticky="e")

    def finish(action):
        label = name_var.get().strip()
        if action == "name" and not label:
            entry.focus_set()
            return
        result.update(action=action, label=label,
                      remember=bool(remember_var.get()) if action == "name" else False)
        win.destroy()

    ttk.Button(buttons, text="Don’t capture", command=lambda: finish("discard")).pack(side="right")
    ttk.Button(buttons, text="Name source & save", command=lambda: finish("name")).pack(side="right", padx=6)
    ttk.Button(buttons, text="Continue anyway", command=lambda: finish("continue")).pack(side="right", padx=6)
    win.protocol("WM_DELETE_WINDOW", lambda: finish("discard"))
    win.grab_set()
    entry.focus_set()
    if own_root:
        win.mainloop()
    else:
        root.wait_window(win)
    return result


def main():
    """Child-process entry point for CLI/tray prompts."""
    request = json.loads(sys.stdin.read() or "{}")
    decision = _show_prompt(request.get("source_window"))
    print(json.dumps(decision), flush=True)


if __name__ == "__main__":
    main()
