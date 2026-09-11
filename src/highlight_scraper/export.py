"""
export.py — turn the SQLite capture store into a plain file: Markdown,
CSV, or JSON. Read from the database directly if you like (it's just
SQLite), but these give you a portable file to hand to something else
(Obsidian, a spreadsheet, a script).
"""

import csv
import json
from dataclasses import asdict
from pathlib import Path


def _ordered_rows(store, session):
    rows = store.query(session=session, limit=1_000_000)
    rows.reverse()  # oldest first, i.e. chronological
    return rows


def export_markdown(store, session, out_path):
    rows = _ordered_rows(store, session)

    grouped = {}
    for r in rows:
        grouped.setdefault(r.source_app or "Unknown source", []).append(r)

    title = f"Highlights — {session}" if session else "Highlights — all sessions"
    lines = [f"# {title}", ""]
    for source, items in grouped.items():
        lines.append(f"## {source}")
        lines.append("")
        for r in items:
            tag = f" `[{r.tag}]`" if r.tag else ""
            lines.append(f"- **{r.captured_at}**{tag} — {r.text.strip()}")
            if r.source_window:
                lines.append(f"  _from: {r.source_window}_")
        lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def export_csv(store, session, out_path):
    rows = _ordered_rows(store, session)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "captured_at", "session", "source_app", "source_window", "tag", "text"])
        for r in rows:
            writer.writerow([r.id, r.captured_at, r.session, r.source_app, r.source_window, r.tag, r.text])


def export_json(store, session, out_path):
    rows = _ordered_rows(store, session)
    Path(out_path).write_text(
        json.dumps([asdict(r) for r in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
