#!/usr/bin/env python3
"""
gui.py — MainbyteLabs-themed Tkinter front end for the research highlight
capture tool.

Improvements over 0.3.4:
  1. Session history browser — dropdown to open and browse any past session
  2. Per-capture right-click context menu — tag, copy to clipboard, delete
  3. Live capture counter and session start time in the status bar
  4. Custom tag input field alongside the three quick-tag buttons
  5. Configurable preview length and entry count (reads from config.py,
     adjustable live via Settings panel)
  6. MainbyteLabs dark theme (#0D0D0D background, #00FF41 green accent)

Run:
    highlight-scraper-gui

Requires (in addition to the base package):
    pip install ttkthemes --break-system-packages
"""

import queue
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from ttkthemes import ThemedTk
    _HAS_TTKTHEMES = True
except ImportError:
    _HAS_TTKTHEMES = False

from highlight_scraper import export as exporters
from highlight_scraper.config import load_config, save_config
from highlight_scraper.session_manager import CaptureSession
from highlight_scraper.storage import CaptureStore

# ── palette ──────────────────────────────────────────────────────────────────
BG          = "#0D0D0D"
BG_PANEL    = "#1A1A1A"
BG_ENTRY    = "#141414"
BG_LIST     = "#111111"
ACCENT      = "#00FF41"
ACCENT_DIM  = "#00C030"
FG          = "#E0E0E0"
FG_MUTED    = "#666666"
FG_TS       = "#00C030"        # timestamps in the capture list
BORDER      = "#2A2A2A"
COL_PAUSED  = "#D4A017"
COL_STOPPED = "#555555"
FONT_MONO   = ("Courier New", 10)
FONT_MONO_S = ("Courier New", 9)
FONT_UI     = ("Courier New", 10)
FONT_TITLE  = ("Courier New", 11, "bold")

QUICK_TAGS = ["important", "question", "followup"]

# ── helpers ───────────────────────────────────────────────────────────────────

def _apply_theme(root: tk.Tk) -> None:
    """Apply the MainbyteLabs dark palette to all ttk widgets."""
    s = ttk.Style(root)

    # Base mapping shared by most widgets
    base_map = {
        "background":  [("active", BG_PANEL), ("disabled", BG)],
        "foreground":  [("disabled", FG_MUTED)],
    }

    s.configure(".",
                 background=BG,
                 foreground=FG,
                 fieldbackground=BG_ENTRY,
                 troughcolor=BG_PANEL,
                 selectbackground=ACCENT_DIM,
                 selectforeground=BG,
                 font=FONT_UI,
                 bordercolor=BORDER,
                 relief="flat")

    s.configure("TFrame",  background=BG)
    s.configure("TLabel",  background=BG, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=FG_MUTED)
    s.configure("Accent.TLabel", background=BG, foreground=ACCENT, font=FONT_TITLE)

    s.configure("TButton",
                 background=BG_PANEL,
                 foreground=ACCENT,
                 relief="flat",
                 padding=(8, 4),
                 borderwidth=1)
    s.map("TButton",
          background=[("active", ACCENT), ("disabled", BG_PANEL)],
          foreground=[("active", BG),     ("disabled", FG_MUTED)])

    s.configure("TEntry",
                 fieldbackground=BG_ENTRY,
                 foreground=FG,
                 insertcolor=ACCENT,
                 bordercolor=BORDER,
                 relief="flat")

    s.configure("TCheckbutton",
                 background=BG,
                 foreground=FG,
                 indicatorcolor=BG_PANEL,
                 selectcolor=ACCENT)
    s.map("TCheckbutton",
          background=[("active", BG)],
          indicatorcolor=[("selected", ACCENT)])

    s.configure("TSpinbox",
                 fieldbackground=BG_ENTRY,
                 foreground=FG,
                 insertcolor=ACCENT,
                 arrowcolor=ACCENT,
                 bordercolor=BORDER)

    s.configure("TCombobox",
                 fieldbackground=BG_ENTRY,
                 foreground=FG,
                 selectbackground=ACCENT_DIM,
                 selectforeground=BG,
                 arrowcolor=ACCENT)
    s.map("TCombobox",
          fieldbackground=[("readonly", BG_ENTRY)],
          foreground=[("readonly", FG)])

    s.configure("TNotebook",       background=BG, bordercolor=BORDER)
    s.configure("TNotebook.Tab",
                 background=BG_PANEL,
                 foreground=FG_MUTED,
                 padding=(10, 4))
    s.map("TNotebook.Tab",
          background=[("selected", BG)],
          foreground=[("selected", ACCENT)])

    s.configure("TSeparator", background=BORDER)

    # Scrollbars
    s.configure("TScrollbar",
                 background=BG_PANEL,
                 troughcolor=BG,
                 arrowcolor=FG_MUTED,
                 bordercolor=BORDER)


# ── main window ───────────────────────────────────────────────────────────────

class HighlightScraperGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("MainbyteLabs — Highlight Scraper")
        root.geometry("700x620")
        root.minsize(600, 500)
        root.configure(bg=BG)

        _apply_theme(root)

        self.config = load_config()
        self.session: CaptureSession | None = None
        self.paste_helper = None
        self.event_queue: queue.Queue = queue.Queue()

        # live settings (read from config, adjustable in Settings panel)
        self._preview_chars = tk.IntVar(value=self.config.get("preview_chars", 200))
        self._entries_shown = tk.IntVar(value=self.config.get("entries_shown", 10))

        # capture counter for live status
        self._capture_count = 0
        self._session_start: datetime | None = None

        self._build_widgets()
        self.root.after(100, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── widget construction ──────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        # ── green left accent bar
        accent_bar = tk.Frame(self.root, width=4, bg=ACCENT)
        accent_bar.pack(side="left", fill="y")

        main = tk.Frame(self.root, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        self._build_header(main)
        self._build_controls(main)
        self._build_tag_row(main)
        self._build_paste_row(main)
        self._build_session_browser(main)
        self._build_status_bar(main)
        self._build_capture_list(main)

    def _build_header(self, parent: tk.Frame) -> None:
        hdr = tk.Frame(parent, bg=BG, pady=10)
        hdr.pack(fill="x", padx=12)

        tk.Label(hdr, text="● HIGHLIGHT SCRAPER", bg=BG, fg=ACCENT,
                 font=("Courier New", 13, "bold")).pack(side="left")
        tk.Label(hdr, text=" by MainbyteLabs", bg=BG, fg=FG_MUTED,
                 font=("Courier New", 10)).pack(side="left")

        # settings gear button (top right)
        self._settings_btn = ttk.Button(hdr, text="⚙ Settings",
                                         command=self._open_settings)
        self._settings_btn.pack(side="right")

    def _build_controls(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG, pady=4)
        row.pack(fill="x", padx=12)

        tk.Label(row, text="Session:", bg=BG, fg=FG_MUTED,
                 font=FONT_UI).pack(side="left")

        self.session_var = tk.StringVar()
        self.session_entry = ttk.Entry(row, textvariable=self.session_var, width=24)
        self.session_entry.pack(side="left", padx=(6, 16))

        self.start_btn = ttk.Button(row, text="▶ Start", command=self.start)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(row, text="■ Stop",
                                    command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))

        self.pause_var = tk.BooleanVar(value=False)
        self.pause_chk = ttk.Checkbutton(row, text="Pause",
                                           variable=self.pause_var,
                                           command=self._toggle_pause,
                                           state="disabled")
        self.pause_chk.pack(side="left", padx=(16, 0))

        self.export_btn = ttk.Button(row, text="↓ Export…",
                                      command=self.export, state="disabled")
        self.export_btn.pack(side="left", padx=(16, 0))

    def _build_tag_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG, pady=2)
        row.pack(fill="x", padx=12)

        tk.Label(row, text="Tag last:", bg=BG, fg=FG_MUTED,
                 font=FONT_UI).pack(side="left")

        for tag in QUICK_TAGS:
            ttk.Button(row, text=tag, width=10,
                        command=lambda t=tag: self.apply_tag(t)).pack(side="left", padx=(6, 0))

        # ── custom tag input (improvement #4)
        tk.Label(row, text="|", bg=BG, fg=BORDER, font=FONT_UI).pack(side="left", padx=(12, 0))
        self._custom_tag_var = tk.StringVar()
        _ctag_entry = ttk.Entry(row, textvariable=self._custom_tag_var, width=14)
        _ctag_entry.pack(side="left", padx=(6, 4))
        _ctag_entry.bind("<Return>", lambda _e: self._apply_custom_tag())
        ttk.Button(row, text="Tag", width=5,
                    command=self._apply_custom_tag).pack(side="left")

    def _build_paste_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG, pady=2)
        row.pack(fill="x", padx=12)

        self.paste_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Click-and-hold to paste",
                         variable=self.paste_enabled,
                         command=self._toggle_paste).pack(side="left")

        tk.Label(row, text="Hold (s):", bg=BG, fg=FG_MUTED,
                 font=FONT_UI).pack(side="left", padx=(16, 4))
        self.hold_seconds = tk.DoubleVar(value=self.config.get("hold_seconds", 0.45))
        ttk.Spinbox(row, from_=0.15, to=2.0, increment=0.05, width=5,
                    textvariable=self.hold_seconds).pack(side="left")

        self.paste_status_var = tk.StringVar()
        tk.Label(row, textvariable=self.paste_status_var, bg=BG, fg=FG_MUTED,
                 font=FONT_MONO_S).pack(side="left", padx=(12, 0))

    def _build_session_browser(self, parent: tk.Frame) -> None:
        """Improvement #1 — history browser: dropdown of all past sessions."""
        row = tk.Frame(parent, bg=BG, pady=4)
        row.pack(fill="x", padx=12)

        tk.Label(row, text="Browse session:", bg=BG, fg=FG_MUTED,
                 font=FONT_UI).pack(side="left")

        self._browse_var = tk.StringVar()
        self._browse_combo = ttk.Combobox(row, textvariable=self._browse_var,
                                           state="readonly", width=28)
        self._browse_combo.pack(side="left", padx=(6, 6))
        self._browse_combo.bind("<<ComboboxSelected>>", self._on_browse_select)

        ttk.Button(row, text="↻ Refresh", width=9,
                    command=self._refresh_session_list).pack(side="left")

        ttk.Button(row, text="↓ Export session…", width=16,
                    command=self._export_browsed_session).pack(side="left", padx=(6, 0))

        self._refresh_session_list()

    def _build_status_bar(self, parent: tk.Frame) -> None:
        """Improvement #3 — live counter and backend in a two-part status bar."""
        bar = tk.Frame(parent, bg=BG_PANEL, pady=4)
        bar.pack(fill="x", padx=0)

        self.status_var = tk.StringVar(value="● IDLE")
        tk.Label(bar, textvariable=self.status_var, bg=BG_PANEL, fg=FG_MUTED,
                 font=FONT_MONO_S, anchor="w").pack(side="left", padx=12)

        self._counter_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._counter_var, bg=BG_PANEL, fg=ACCENT,
                 font=FONT_MONO_S, anchor="e").pack(side="right", padx=12)

    def _build_capture_list(self, parent: tk.Frame) -> None:
        # ── header row: label + search bar (improvement: search/filter)
        lbl_row = tk.Frame(parent, bg=BG)
        lbl_row.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(lbl_row, text="Captures", bg=BG, fg=FG,
                 font=("Courier New", 10, "bold")).pack(side="left")
        tk.Label(lbl_row, text="(right-click for options)", bg=BG, fg=FG_MUTED,
                 font=("Courier New", 9)).pack(side="left", padx=(8, 0))

        # search field — right side of the same row
        tk.Label(lbl_row, text="Search:", bg=BG, fg=FG_MUTED,
                 font=FONT_UI).pack(side="right", padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        _search_entry = ttk.Entry(lbl_row, textvariable=self._search_var, width=20)
        _search_entry.pack(side="right")
        ttk.Button(lbl_row, text="✕", width=2,
                    command=self._clear_search).pack(side="right", padx=(0, 2))

        # coloured left rail inside the list frame
        list_outer = tk.Frame(parent, bg=BORDER)
        list_outer.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.preview = tk.Text(list_outer, wrap="word", bg=BG_LIST, fg=FG,
                                font=FONT_MONO_S, relief="flat",
                                insertbackground=ACCENT,
                                selectbackground=ACCENT_DIM,
                                selectforeground=BG,
                                spacing3=4,
                                state="disabled", cursor="arrow")

        sb = ttk.Scrollbar(list_outer, command=self.preview.yview)
        self.preview.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)

        # text tags for colour coding
        self.preview.tag_configure("ts",     foreground=FG_TS,    font=FONT_MONO_S)
        self.preview.tag_configure("source", foreground=FG_MUTED, font=FONT_MONO_S)
        self.preview.tag_configure("tag",    foreground=ACCENT,   font=("Courier New", 9, "bold"))
        self.preview.tag_configure("body",   foreground=FG,       font=FONT_MONO_S)
        self.preview.tag_configure("sep",    foreground=BORDER)

        # right-click context menu (improvement #2)
        self._ctx_menu = tk.Menu(self.root, tearoff=0,
                                  bg=BG_PANEL, fg=FG,
                                  activebackground=ACCENT,
                                  activeforeground=BG,
                                  font=FONT_UI)
        self._ctx_menu.add_command(label="Copy text",       command=self._ctx_copy)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Tag: important",  command=lambda: self.apply_tag("important"))
        self._ctx_menu.add_command(label="Tag: question",   command=lambda: self.apply_tag("question"))
        self._ctx_menu.add_command(label="Tag: followup",   command=lambda: self.apply_tag("followup"))
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Delete last capture", command=self._ctx_delete_last)

        self.preview.bind("<Button-3>", self._show_ctx_menu)

    # ── session control ───────────────────────────────────────────────────────

    def start(self) -> None:
        name = self.session_var.get().strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_var.set(name)

        self.session = CaptureSession(self.config["db_path"], name, self.config)
        self.session.listeners.append(self._on_capture)
        try:
            self.session.start()
        except RuntimeError as e:
            self.status_var.set(f"✖ Error: {e}")
            self.session = None
            return

        self._capture_count = 0
        self._session_start = datetime.now()
        backend = self.session.watcher.backend_name
        self.status_var.set(f"● LIVE  [{backend}]  session: {name}")
        self._counter_var.set("0 captures")

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.pause_chk.config(state="normal")
        self.export_btn.config(state="normal")
        self.session_entry.config(state="disabled")
        self._refresh_preview()

    def stop(self) -> None:
        if self.session:
            self.session.stop()
        if self.paste_helper:
            self.paste_helper.stop()
            self.paste_helper = None
            self.paste_enabled.set(False)
            self.paste_status_var.set("")

        self.status_var.set("■ STOPPED")
        self._counter_var.set("")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.pause_chk.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.pause_var.set(False)
        self.session_entry.config(state="normal")
        self._refresh_session_list()
        self.session = None

    def _toggle_pause(self) -> None:
        if not self.session:
            return
        paused = self.session.toggle_pause()
        self.pause_var.set(paused)
        if paused:
            self.status_var.set(f"⏸ PAUSED  session: {self.session.session_name}")
        else:
            backend = self.session.watcher.backend_name
            self.status_var.set(f"● LIVE  [{backend}]  session: {self.session.session_name}")

    def export(self) -> None:
        """Export current (active) session."""
        if not self.session:
            return
        self._do_export(self.session.store, self.session.session_name)

    # ── tag actions ───────────────────────────────────────────────────────────

    def apply_tag(self, tag: str) -> None:
        if not self.session:
            messagebox.showinfo("Tag", "No active session.")
            return
        row_id = self.session.tag_last(tag)
        if row_id is None:
            messagebox.showinfo("Tag", "No captures yet.")
        else:
            self._refresh_preview()

    def _apply_custom_tag(self) -> None:
        tag = self._custom_tag_var.get().strip()
        if not tag:
            return
        self.apply_tag(tag)
        self._custom_tag_var.set("")

    # ── paste helper ──────────────────────────────────────────────────────────

    def _toggle_paste(self) -> None:
        if self.paste_enabled.get():
            from highlight_scraper.paste_on_hold import ClickHoldPaste
            self.paste_helper = ClickHoldPaste(hold_seconds=self.hold_seconds.get())
            self.paste_helper.start()
            self.paste_status_var.set(
                self.paste_helper.warning or
                f"hold {self.hold_seconds.get():.2f}s on a field to paste"
            )
        else:
            if self.paste_helper:
                self.paste_helper.stop()
                self.paste_helper = None
            self.paste_status_var.set("")

    # ── session history browser (improvement #1) ──────────────────────────────

    def _refresh_session_list(self) -> None:
        store = CaptureStore(self.config["db_path"])
        try:
            rows = store.sessions()
        finally:
            store.close()

        names = [r[0] for r in rows]
        self._browse_combo["values"] = names
        if names and not self._browse_var.get():
            self._browse_var.set(names[0])

    def _on_browse_select(self, _event=None) -> None:
        name = self._browse_var.get()
        if not name:
            return
        store = CaptureStore(self.config["db_path"])
        try:
            rows = store.query(session=name,
                                limit=self._entries_shown.get())
        finally:
            store.close()
        self._render_rows(list(reversed(rows)), readonly=True)

    def _export_browsed_session(self) -> None:
        name = self._browse_var.get()
        if not name:
            messagebox.showinfo("Export", "Select a session first.")
            return
        store = CaptureStore(self.config["db_path"])
        try:
            self._do_export(store, name)
        finally:
            store.close()

    # ── context menu (improvement #2) ────────────────────────────────────────

    def _show_ctx_menu(self, event: tk.Event) -> None:
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _ctx_copy(self) -> None:
        try:
            sel = self.preview.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # nothing selected — grab the whole content
            sel = self.preview.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(sel)

    def _ctx_delete_last(self) -> None:
        if not self.session:
            messagebox.showinfo("Delete", "No active session.")
            return
        rows = self.session.store.query(
            session=self.session.session_name, limit=1
        )
        if not rows:
            messagebox.showinfo("Delete", "No captures to delete.")
            return
        row = rows[0]
        preview = row.text[:60] + ("…" if len(row.text) > 60 else "")
        if not messagebox.askyesno(
            "Delete capture",
            f"Permanently delete this capture?\n\n\"{preview}\""
        ):
            return
        deleted = self.session.store.delete_capture(row.id)
        if deleted:
            self._refresh_preview()

    # ── capture events → GUI ──────────────────────────────────────────────────

    def _on_capture(self, row) -> None:
        # Called from watcher background thread — only queue, never touch widgets
        self.event_queue.put(row)

    def _drain_queue(self) -> None:
        updated = False
        while not self.event_queue.empty():
            self.event_queue.get_nowait()
            self._capture_count += 1
            updated = True
        if updated:
            self._refresh_preview()
            # improvement #3 — live counter
            elapsed = ""
            if self._session_start:
                secs = int((datetime.now() - self._session_start).total_seconds())
                h, r = divmod(secs, 3600)
                m, s = divmod(r, 60)
                elapsed = f"  {h:02d}:{m:02d}:{s:02d}"
            self._counter_var.set(f"{self._capture_count} captures{elapsed}")
        self.root.after(100, self._drain_queue)

    # ── preview rendering ─────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        if not self.session:
            return
        rows = self.session.store.query(
            session=self.session.session_name,
            limit=self._entries_shown.get(),
        )
        self._render_rows(list(reversed(rows)))

    def _render_rows(self, rows: list, readonly: bool = False) -> None:
        max_chars = self._preview_chars.get()
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")

        if not rows:
            self.preview.insert("end", "  no captures yet\n", "source")
        else:
            for i, row in enumerate(rows):
                text = row.text.replace("\n", " ")
                if len(text) > max_chars:
                    text = text[:max_chars] + "…"
                source = row.source_app or row.source_window or "unknown"
                tag_str = f" [{row.tag}]" if row.tag else ""

                self.preview.insert("end", f"  {row.captured_at}", "ts")
                self.preview.insert("end", f"  ({source})", "source")
                if tag_str:
                    self.preview.insert("end", tag_str, "tag")
                self.preview.insert("end", "\n")
                self.preview.insert("end", f"    {text}\n", "body")
                if i < len(rows) - 1:
                    self.preview.insert("end", "  " + "─" * 60 + "\n", "sep")

        self.preview.see("end")
        self.preview.configure(state="disabled")

    # ── export helper ─────────────────────────────────────────────────────────

    def _do_export(self, store, session_name: str) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("CSV", "*.csv"), ("JSON", "*.json")],
            initialfile=f"{session_name}_export.md",
        )
        if not path:
            return
        ext = Path(path).suffix.lstrip(".").lower()
        exporter = {
            "md":   exporters.export_markdown,
            "csv":  exporters.export_csv,
            "json": exporters.export_json,
        }.get(ext, exporters.export_markdown)
        exporter(store, session_name, path)
        messagebox.showinfo("Export", f"Written to:\n{path}")

    # ── search / filter (0.4.0) ───────────────────────────────────────────────

    def _on_search_change(self, *_) -> None:
        query = self._search_var.get().strip()
        if not query:
            # empty search — show the normal live/browse view
            if self.session:
                self._refresh_preview()
            else:
                name = self._browse_var.get()
                if name:
                    self._on_browse_select()
            return
        # search across all sessions when browsing, or current session when live
        session_filter = None
        if self.session:
            session_filter = self.session.session_name
        elif self._browse_var.get():
            session_filter = self._browse_var.get()

        store = CaptureStore(self.config["db_path"])
        try:
            rows = store.search(query, session=session_filter,
                                limit=self._entries_shown.get())
        finally:
            store.close()
        self._render_rows(list(reversed(rows)), readonly=True)

    def _clear_search(self) -> None:
        self._search_var.set("")

    # ── settings panel (improvement #5) ──────────────────────────────────────

    def _open_settings(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.configure(bg=BG)
        win.geometry("420x460")
        win.resizable(False, False)
        _apply_theme(win)

        pad = {"padx": 16, "pady": 5}

        # ── GUI Display ───────────────────────────────────────────────────────
        tk.Label(win, text="GUI Display", bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", **pad)

        row1 = tk.Frame(win, bg=BG)
        row1.pack(fill="x", **pad)
        tk.Label(row1, text="Entries shown in list:", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        ttk.Spinbox(row1, from_=5, to=50, increment=1, width=6,
                    textvariable=self._entries_shown).pack(side="left")

        row2 = tk.Frame(win, bg=BG)
        row2.pack(fill="x", **pad)
        tk.Label(row2, text="Preview characters:", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        ttk.Spinbox(row2, from_=50, to=1000, increment=50, width=6,
                    textvariable=self._preview_chars).pack(side="left")

        ttk.Separator(win).pack(fill="x", padx=16, pady=6)

        # ── Capture Behaviour ─────────────────────────────────────────────────
        tk.Label(win, text="Capture Behaviour", bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", **pad)

        _min_len = tk.IntVar(value=self.config.get("min_length", 3))
        row3 = tk.Frame(win, bg=BG)
        row3.pack(fill="x", **pad)
        tk.Label(row3, text="Min capture length (chars):", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=50, increment=1, width=6,
                    textvariable=_min_len).pack(side="left")

        _merge = tk.DoubleVar(value=self.config.get("merge_window_seconds", 2.0))
        row4 = tk.Frame(win, bg=BG)
        row4.pack(fill="x", **pad)
        tk.Label(row4, text="Merge window (seconds):", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        ttk.Spinbox(row4, from_=0.5, to=10.0, increment=0.5, width=6,
                    textvariable=_merge).pack(side="left")

        ttk.Separator(win).pack(fill="x", padx=16, pady=6)

        # ── Auto-Export (0.4.0) ───────────────────────────────────────────────
        tk.Label(win, text="Auto-Export", bg=BG, fg=ACCENT,
                 font=("Courier New", 10, "bold")).pack(anchor="w", **pad)

        tk.Label(win,
                 text="Automatically export to Markdown every N captures.\n"
                      "Set to 0 to disable.",
                 bg=BG, fg=FG_MUTED,
                 font=("Courier New", 8),
                 justify="left").pack(anchor="w", padx=16)

        _auto_every = tk.IntVar(value=self.config.get("auto_export_every", 0))
        row5 = tk.Frame(win, bg=BG)
        row5.pack(fill="x", **pad)
        tk.Label(row5, text="Export every N captures (0=off):", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        ttk.Spinbox(row5, from_=0, to=500, increment=10, width=6,
                    textvariable=_auto_every).pack(side="left")

        _auto_path_var = tk.StringVar(
            value=self.config.get(
                "auto_export_path",
                str(Path.home() / "highlights_auto.md"),
            )
        )
        row6 = tk.Frame(win, bg=BG)
        row6.pack(fill="x", **pad)
        tk.Label(row6, text="Export file path:", bg=BG, fg=FG,
                 width=28, anchor="w").pack(side="left")
        _path_entry = ttk.Entry(row6, textvariable=_auto_path_var, width=24)
        _path_entry.pack(side="left")

        def _browse_path():
            chosen = filedialog.asksaveasfilename(
                defaultextension=".md",
                filetypes=[("Markdown", "*.md")],
                initialfile="highlights_auto.md",
            )
            if chosen:
                _auto_path_var.set(chosen)

        ttk.Button(row6, text="…", width=2, command=_browse_path).pack(
            side="left", padx=(4, 0))

        ttk.Separator(win).pack(fill="x", padx=16, pady=6)

        def _save():
            self.config["entries_shown"]       = self._entries_shown.get()
            self.config["preview_chars"]        = self._preview_chars.get()
            self.config["min_length"]           = _min_len.get()
            self.config["merge_window_seconds"] = _merge.get()
            self.config["auto_export_every"]    = _auto_every.get()
            self.config["auto_export_path"]     = _auto_path_var.get()
            save_config(self.config)
            self._refresh_preview()
            win.destroy()

        ttk.Button(win, text="Save & Close", command=_save).pack(pady=10)

    # ── close ─────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self.session:
            self.session.stop()
        if self.paste_helper:
            self.paste_helper.stop()
        self.root.destroy()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if _HAS_TTKTHEMES:
        root = ThemedTk(theme="equilux")
    else:
        root = tk.Tk()

    HighlightScraperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
