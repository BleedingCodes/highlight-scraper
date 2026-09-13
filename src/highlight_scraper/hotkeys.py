"""
hotkeys.py — global keyboard shortcuts for tagging the most recent
capture without breaking your reading flow to switch windows.

Default bindings:
    Ctrl+Alt+1   tag last capture "important"
    Ctrl+Alt+2   tag last capture "question"
    Ctrl+Alt+3   tag last capture "followup"

Requires: pip install pynput --break-system-packages
(same dependency paste_on_hold.py uses)
"""

from pynput import keyboard

DEFAULT_BINDINGS = {
    "<ctrl>+<alt>+1": "important",
    "<ctrl>+<alt>+2": "question",
    "<ctrl>+<alt>+3": "followup",
}


class TagHotkeys:
    def __init__(self, on_tag, bindings: dict = None):
        self.on_tag = on_tag  # callable(tag_name)
        self.bindings = bindings or DEFAULT_BINDINGS
        self._listener = None

    def start(self):
        mapping = {
            combo: (lambda tag=tag: self.on_tag(tag))
            for combo, tag in self.bindings.items()
        }
        self._listener = keyboard.GlobalHotKeys(mapping)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
