#!/usr/bin/env python3
"""
gui.py — Tkinter front end for the research highlight capture tool.

Session name field, Start/Stop, a Pause checkbox (captures nothing while
paused, without losing your place), three quick tag buttons, a live list
of recent captures (source window + timestamp + tag + text), an Export
button (Markdown/CSV/JSON via a save dialog), and the click-and-hold-to-
paste checkbox. All captures land in one SQLite database shared with
cli.py and tray.py — see config.py for its location.

Run:
    highlight-scraper-gui
"""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from highlight_scraper import export as exporters
from highlight_scraper.config import load_config
from highlight_scraper.session_manager import CaptureSession

RECENT_ENTRIES_SHOWN = 8
ENTRY_TEXT_PREVIEW_CHARS = 200
QUICK_TAGS = ["important", "question", "followup"]


class HighlightScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Research Highlight Capture")
        root.geometry("580x520")

        self.config = load_config()
        self.session = None
        self.paste_helper = None
        self.event_queue = queue.Queue()  # capture thread -> GUI thread

        self._build_widgets()
        self.root.after(100, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Session:").pack(side="left")
        self.session_var = tk.StringVar(value="")
        self.session_entry = ttk.Entry(top, textvariable=self.session_var, width=22)
        self.session_entry.pack(side="left", padx=(4, 16))

        self.start_btn = ttk.Button(top, text="Start", command=self.start)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))

        self.pause_var = tk.BooleanVar(value=False)
        self.pause_chk = ttk.Checkbutton(top, text="Pause", variable=self.pause_var,
                                          command=self._toggle_pause, state="disabled")
        self.pause_chk.pack(side="left", padx=(16, 0))

        self.export_btn = ttk.Button(top, text="Export…", command=self.export, state="disabled")
        self.export_btn.pack(side="left", padx=(16, 0))

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 4)).pack(fill="x")

        tag_row = ttk.Frame(self.root, padding=(10, 0))
        tag_row.pack(fill="x")
        ttk.Label(tag_row, text="Tag most recent:").pack(side="left")
        for tag in QUICK_TAGS:
            ttk.Button(tag_row, text=tag, width=10,
                       command=lambda t=tag: self.apply_tag(t)).pack(side="left", padx=(6, 0))

        paste_row = ttk.Frame(self.root, padding=(10, 8))
        paste_row.pack(fill="x")

        self.paste_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(paste_row, text="Click-and-hold to paste",
                         variable=self.paste_enabled,
                         command=self._toggle_paste).pack(side="left")

        ttk.Label(paste_row, text="Hold (s):").pack(side="left", padx=(16, 4))
        self.hold_seconds = tk.DoubleVar(value=self.config.get("hold_seconds", 0.45))
        ttk.Spinbox(paste_row, from_=0.15, to=2.0, increment=0.05, width=5,
                    textvariable=self.hold_seconds).pack(side="left")

        self.paste_status_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.paste_status_var, padding=(10, 0),
                  foreground="#666").pack(fill="x")

        ttk.Label(self.root, text="Recent captures:", padding=(10, 6)).pack(fill="x")

        self.preview = scrolledtext.ScrolledText(self.root, wrap="word", height=16)
        self.preview.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.preview.configure(state="disabled")

    # ---- session control -----------------------------------------------

    def start(self):
        from datetime import datetime
        session_name = self.session_var.get().strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_var.set(session_name)

        self.session = CaptureSession(self.config["db_path"], session_name, self.config)
        self.session.listeners.append(self._on_capture)
        try:
            self.session.start()
        except RuntimeError as e:
            self.status_var.set(f"Error: {e}")
            return

        self.status_var.set(f"Watching '{session_name}' — backend: {self.session.watcher.backend_name}")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.pause_chk.config(state="normal")
        self.export_btn.config(state="normal")
        self.session_entry.config(state="disabled")
        self._refresh_preview()

    def stop(self):
        if self.session:
            self.session.stop()
        if self.paste_helper:
            self.paste_helper.stop()
            self.paste_helper = None
            self.paste_enabled.set(False)
            self.paste_status_var.set("")
        self.status_var.set("Stopped")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.pause_chk.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.pause_var.set(False)
        self.session_entry.config(state="normal")
        self.session = None

    def _toggle_pause(self):
        if not self.session:
            return
        paused = self.session.toggle_pause()
        self.pause_var.set(paused)
        self.status_var.set("Paused" if paused else
                             f"Watching '{self.session.session_name}' — backend: {self.session.watcher.backend_name}")

    def export(self):
        if not self.session:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("CSV", "*.csv"), ("JSON", "*.json")],
            initialfile=f"{self.session.session_name}_export.md",
        )
        if not path:
            return
        ext = Path(path).suffix.lstrip(".").lower()
        exporter = {"md": exporters.export_markdown, "csv": exporters.export_csv,
                    "json": exporters.export_json}.get(ext, exporters.export_markdown)
        exporter(self.session.store, self.session.session_name, path)
        messagebox.showinfo("Export", f"Written to:\n{path}")

    def apply_tag(self, tag):
        if not self.session:
            return
        row_id = self.session.tag_last(tag)
        if row_id is None:
            messagebox.showinfo("Tag", "No captures yet to tag.")
        else:
            self._refresh_preview()

    # ---- click-and-hold-to-paste ------------------------------------------

    def _toggle_paste(self):
        if self.paste_enabled.get():
            from highlight_scraper.paste_on_hold import ClickHoldPaste
            self.paste_helper = ClickHoldPaste(hold_seconds=self.hold_seconds.get())
            self.paste_helper.start()
            if self.paste_helper.warning:
                self.paste_status_var.set(self.paste_helper.warning)
            else:
                self.paste_status_var.set(
                    f"Listening — hold {self.hold_seconds.get():.2f}s on a field to paste"
                )
        else:
            if self.paste_helper:
                self.paste_helper.stop()
                self.paste_helper = None
            self.paste_status_var.set("")

    # ---- capture events -> GUI ------------------------------------------

    def _on_capture(self, row):
        # Called from the watcher's background thread. Never touch Tkinter
        # widgets from here directly — just wake the main thread's poll loop.
        self.event_queue.put(row)

    def _drain_queue(self):
        updated = False
        while not self.event_queue.empty():
            self.event_queue.get_nowait()
            updated = True
        if updated:
            self._refresh_preview()
        self.root.after(100, self._drain_queue)

    def _refresh_preview(self):
        if not self.session:
            return
        rows = self.session.store.query(session=self.session.session_name,
                                         limit=RECENT_ENTRIES_SHOWN)
        rows = list(reversed(rows))  # oldest of the recent batch first
        lines = []
        for row in rows:
            text = row.text.replace("\n", " ")
            if len(text) > ENTRY_TEXT_PREVIEW_CHARS:
                text = text[:ENTRY_TEXT_PREVIEW_CHARS] + "…"
            source = row.source_app or row.source_window or "unknown source"
            tag = f" [{row.tag}]" if row.tag else ""
            lines.append(f"[{row.captured_at}] ({source}){tag}\n    {text}\n")

        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n".join(lines))
        self.preview.see("end")
        self.preview.configure(state="disabled")

    def _on_close(self):
        if self.session:
            self.session.stop()
        if self.paste_helper:
            self.paste_helper.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    HighlightScraperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
