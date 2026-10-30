#!/usr/bin/env python3

"""
ClipStack is a lightweight clipboard history manager.

It stores recently copied text, allows searching, pinning, editing and
reusing clipboard entries, and supports both system tray and window-based
operation depending on the desktop environment.
"""

import argparse
import base64
import clipstack_locale as locale
from datetime import datetime
import io
import json
import os
from PIL import Image
import pystray
import sys
import time
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional
import urllib.request

# -------- Configuration --------
APP_NAME = "ClipStack"
APP_VERSION = "1.3.0"
MAX_ITEMS_DEFAULT = 50
POLL_MS_DEFAULT = 600
SAVE_FILENAME = ".clipstack_history.json"
FILETYPES = [ ('clip files', '*.json') ]

# -------- UI Columns --------
PIN_COL_W = 26
PREVIEW_COL_MIN_W = 120
PREVIEW_MIN_W = 520

# -------- Icon --------
ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAEKklEQVR4AeybPXYTMRSF52MToaSl"
    "p6BPk5KeBdBzTlaRc+hZAD0bSJ+CnpaSrML4evI8sixpJM0b2yHJ8T1Pen9691oeJ0XeDC/855wC"
    "bLbaG7bL87zOIcCO9P39/WDYUt/5tvbkr3MIsCN+fX09GCTEyZk/HXhqATYiK+K3t7eDQXv5tzPp"
    "JmzN6V5rCCASOdQwy9XKX1PflFMrgA6vxe6K6x2NUTNZXGP7p9raGSzvqSxvagUYvn9+VwU7Stc6"
    "hq68fCJ1d3c3GLSX3+Jah7CetTMoz2rmbLUAanR19XaYg/IMIhTC/CIn0gbtLRbma21+2bmzFVde"
    "C5oEaGmcyxUpQaQN2gu5mjX9XQJ8+vYw5BAOa1c8tsoRYYP2cY7tFTPkzjS/5bXYLgF0wGazGVJQ"
    "TLDrnbI3NzdDjFSe+dRPSJ1nPsV70C1A6TC72p62dN6SmLsA9o6sYZcQzdW6C5A76FL9L06A+I1w"
    "FwAYII348EvYuwgAE+HSZx9w4wzshF7a0EWAkHRpIOXBODgc21KtxWCsUy/B/L3WRYCWwzV0DjCS"
    "g7y12pYzS7knF6A0jJEr2VJ9T+yiBOghsLTGVQA4vrpLB1y73k0AIPm3AYyirE2kt7+LADCSTw1h"
    "n2cgFT67z0UAkZxjohxg990Nk03VwRSH/DpV2+pzEaD2UIkQA44Jxjm5fe25pbyTCpAaJEUulbeW"
    "7+wCrEWstu+rALVK/a95bjcApodZSiyY4jCtU7mevrleLgLA+HuAPdCAg3PhMG55snCYGxYCR1+b"
    "MPnC3N61iwAiEg6gPUyDah/Gw7ViMOXCtFashLBP79pFgNTh4eCpeOgLc8N1mLPWejUB1hrYu++r"
    "AN6KzvWD6TMO03qubq24yw0AivMB+6d5+BkP10Cxx1pBFwFEBNiThMO14oYcEcWBXHjvB/bn7J0L"
    "Fi4C6HwRyEHxGqgeJoJwvFaOoabnXI6bAHMH1caNXM7W9qnNuzgBagf3yrs4AeDw2nsRzfVxFQAO"
    "h4f0PhwGDnPiqw+HcSAsX7x2EwDyf/CUSMWxmFEc1x78RHARAEby8fC5vUgYcjklv2pL8ZaYiwCe"
    "A7UMn8pt9bkI0HroJeVfvADA/jc/yK97RXUTAKiaASgSSjX5/ethKEE1P79+lGmGiwAwPgSB7ADA"
    "jrieFyXAmAdke4WB9x/6iFsPFwFEyBqmLIwCzeWpVjkGKIsg8spVnfD4+FemCS4C2IkaBti90zBZ"
    "+S2nxZbqYvItfcNcVwHUWEPHkN8TXuQ1k7sAaromcuR7rr/mfFYC5MiLSC+ejQAiL5IwPVtgXMvf"
    "i2chgMjrez4F/XuMcHIBYFQf1rUiJuKyIfSZF0Jfz7rrBmigU8KIibDBfEttkwB2+LnsUrKp+iYB"
    "Ug2eu69agC8//gyXiNxMtW/MPwAAAP//EMEB7gAAAAZJREFUAwAyE5yPUtMdygAAAABJRU5ErkJg"
    "gg=="
)

ICON_IMAGE = Image.open(
    io.BytesIO(base64.b64decode(ICON_B64))
).convert("RGBA")

# -------- Utilities --------

def get_save_path() -> str:
    """Return the path to the ClipStack save file in the user's home directory."""
    home = os.path.expanduser("~")
    return os.path.join(home, SAVE_FILENAME)

def comparison_key(text: str) -> str:
    """Return a normalized key for comparisons and searches."""
    return normalize_line_endings(text).strip()

def is_blank(text: str) -> bool:
    """Return True if the text contains only whitespace."""
    return not text.strip()

def normalize_line_endings(text: str) -> str:
    """Normalize line endings without modifying the text content."""
    return text.replace("\r\n", "\n").replace("\r", "\n")

##################
# ClipItem Class #
##################

class ClipItem:
    """Single clipboard entry.

    Attributes:
        text: Clipboard text (raw, may contain newlines).
        ts: Unix timestamp (float) of the last insertion, editing or recapture.
        pinned: If True, item is protected from bulk cleanup and (optionally) limits.
    """

    __slots__ = ("text", "ts", "pinned", "use_count")

    def __init__(self, text: str, ts: Optional[float] = None, pinned: bool = False, use_count: int = 0):
        """Create a new clipboard item.

        Args:
            text: Clipboard text.
            ts: Optional timestamp. If None, current time is used.
            pinned: Whether the item is pinned.
            use_count: Number of times the item has been copied from ClipStack.
        """
        self.text = text
        self.ts = ts if ts is not None else time.time()
        self.pinned = pinned
        self.use_count = use_count

    def to_dict(self):
        """Serialize the item to a JSON-compatible dictionary."""
        return {"text": self.text, "ts": self.ts, "pinned": self.pinned,"use_count": self.use_count}

    @staticmethod
    def from_dict(d):
        """Create a ClipItem from a dictionary (loaded from JSON)."""
        return ClipItem(d.get("text", ""), d.get("ts", time.time()), bool(d.get("pinned", False)),d.get("use_count", 0))

######################
# HistoryStore Class #
######################

class HistoryStore:
    """In-memory clipboard history + JSON persistence.

    Responsibilities:
        - Maintain items in MRC (most-recently-copied) order.
        - De-duplicate: re-copying an existing text promotes it instead of duplicating.
        - Enforce max_items (typically for non-pinned items).
        - Load/save JSON (history + settings).

    Notes:
        This class has no UI logic.
    """

    def __init__(self, max_items: int = MAX_ITEMS_DEFAULT):
        """Create a new history store.

        Args:
            max_items: Maximum number of items to keep (subject to pinned policy).
        """
        self.max_items = max_items
        self.items: list[ClipItem] = []
        self.settings = {}

    def add(self, text: str, sort_mode: str = "mrc") -> bool:
        """Add text to the history using MRC ordering and deduplication.

        If the normalized text already exists, moves the existing item to
        the top and updates its timestamp, preserving its pinned state and
        usage counter. Otherwise, inserts a new item at the top.

        Empty or whitespace-only text is ignored. Usage counters are not
        incremented by clipboard captures.

        Args:
            text: Clipboard text to add.

        Returns:
            True if an item was inserted or promoted.
            False if the input is empty after normalization.
        """
        key = comparison_key(text)
        if not key:
            return False

        for i, it in enumerate(self.items):
            if comparison_key(it.text) == key:
                existing = self.items.pop(i)
                existing.ts = time.time()
                self.items.insert(0, existing)
                return True

        self.items.insert(0, ClipItem(text))
        self._enforce_limit(sort_mode)
        return True

    def get_sorted_items(self, sort_mode: str):
        """Return history items sorted by the selected mode."""
        items = list(self.items)

        if sort_mode == "mfu":
            items.sort(key=lambda it: it.use_count, reverse=True)

        return items

    def toggle_pin(self, idx: int):
        """Toggle the pinned flag for the item at index `idx` (if valid)."""
        if 0 <= idx < len(self.items):
            self.items[idx].pinned = not self.items[idx].pinned

    def edit(self, item: ClipItem, new_text: str) -> ClipItem:
        """Edit an item, promoting it to the top without enforcing the limit.

        Preserve its pinned state and usage counter. If the new text
        matches another item, merge their attributes and usage counters.
        """
        key = comparison_key(new_text)

        if not key or item not in self.items:
            return item

        self.items.remove(item)

        # Look for an existing item with the edited text.
        existing = next(
            (it for it in self.items if comparison_key(it.text) == key),
            None
        )

        if existing is not None:
            self.items.remove(existing)
            existing.pinned = existing.pinned or item.pinned
            existing.use_count += item.use_count
            result = existing
        else:
            item.text = new_text
            result = item

        result.ts = time.time()
        self.items.insert(0, result)

        return result

    def delete(self, idx: int):
        """Delete the item at index `idx` (if valid)."""
        if 0 <= idx < len(self.items):
            self.items.pop(idx)

    def clear_unpinned(self):
        """Remove all non-pinned items."""
        self.items = [it for it in self.items if it.pinned]

    def clear_all(self):
        """Remove all items, including pinned ones."""
        self.items = []

    def clear_not_matching_filter(self, query: str) -> None:
        """Remove all items that do not match the query."""
        if is_blank(query):
            return

        query = query.lower()

        self.items = [
            it for it in self.items
            if query in it.text.lower()
        ]

    def _enforce_limit(self, sort_mode: str = "mrc"):
        """Enforce the history limit using the active sorting mode.

        Remove the last unpinned items in the sorted history.
        Pinned items are always preserved.
        """
        overflow = len(self.items) - self.max_items
        if overflow <= 0:
            return

        sorted_items = self.get_sorted_items(sort_mode)
        to_remove = set()

        for item in reversed(sorted_items):
            if not item.pinned:
                to_remove.add(id(item))

                if len(to_remove) == overflow:
                    break

        self.items = [
            item for item in self.items
            if id(item) not in to_remove
        ]

    def save(self, path: str, settings: Optional[dict] = None):
        """Save history (and optional settings) to a JSON file."""
        data = {
            "max_items": self.max_items,
            "items": [it.to_dict() for it in self.items]
        }
        if settings is not None:
            data["settings"] = settings

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> bool:
        """Load history (and settings) from a JSON file.

        The current state is replaced only if the file is loaded successfully.
        Returns True on success and False if the file does not exist or is invalid.
        """
        if not os.path.exists(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            max_items = data.get("max_items", self.max_items)
            items = [ClipItem.from_dict(x) for x in data.get("items", [])]
            settings = data.get("settings", {})
        except Exception:
            return False

        self.max_items = max_items
        self.items = items
        self.settings = settings
        return True

######################
# ClipStackApp Class #
######################

class ClipStackApp(tk.Tk):
    """Tkinter application: UI, clipboard monitoring and tray integration.

    Responsibilities:
        - Render and manage the clipboard history with MRC/MFU sorting.
        - Track item reuse and support copy, pin, edit and delete operations.
        - Poll the system clipboard and capture textual changes.
        - Run a system tray icon and forward its actions to the Tk thread.

    Threading model:
        - Tk must be accessed from the Tk main thread.
        - Tray callbacks must be forwarded to the Tk event loop.
    """

    def __init__(self, no_tray: bool = False):
        """Initialize the application, load settings, build UI and start services."""
        super().__init__()

        # Hide immediately to avoid startup flicker when launching to tray.
        self.withdraw()

        self.title(f"{APP_NAME} v{APP_VERSION}")

        # Window icon. Keep a reference to avoid Tk garbage-collecting it.
        self._window_icon = tk.PhotoImage(data=ICON_B64)
        self.iconphoto(True, self._window_icon)

        # Load persisted history and settings.
        self.store = HistoryStore()
        self.save_path = get_save_path()
        self.store.load(self.save_path)

        self.language = self.store.settings.get("language", "es")
        self.corner = self.store.settings.get("corner", "top-right")
        self.sort_mode = self.store.settings.get("sort_mode", "mrc")
        self.show_timestamp = self.store.settings.get("show_timestamp", True)
        self.hide_after_copy = self.store.settings.get("hide_after_copy", True)
        self.ui_scale = self.store.settings.get("ui_scale", 1.0)
        self.auto_var = True

        # Do not capture the pre-existing clipboard content at startup.
        self._prime_clipboard()

        # Runtime state.
        self.poll_ms = POLL_MS_DEFAULT
        self._last_double_click = 0.0
        self._has_filter = False
        self._filtered_items = []
        self._status_builder = None
        self.modal_window = None
        self.closing = False

        # Tray state.
        self.tray_icon = None
        self.tray_thread = None

        # Tray
        self.tray_has_menu = (not no_tray) and bool(pystray.Icon.HAS_MENU)
        if self.tray_has_menu:
            # Closing the window hides it; real exit is done from the tray.
            self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
            self.setup_tray()
        else:
            # Without tray menu, closing the window must really exit.
            self.protocol("WM_DELETE_WINDOW", self.quit_app)

        # UI
        self._apply_ui_scale()
        self._build_ui()
        self._bind_shortcuts()

        # Delay the first clipboard poll until Tk has fully initialized.
        self.after(1000, self.poll_clipboard)


    # ----- MULTILINGUAL SUPPORT -----

    def tr(self, key: str) -> str:
        """Return the localized text for `key`.

        Falls back to default language if the selected language is unavailable, and to the
        key itself if the translation is missing. Translation keys intentionally
        start with '_' so missing strings are easy to spot in the UI.
        """
        return locale.TEXTS.get(self.language, locale.TEXTS[locale.DEFAULT_LANGUAGE]).get(key, key)

    def set_language(self, lang: str):
        """Set the active UI language and refresh translatable UI elements."""
        if lang not in locale.SUPPORTED_LANGUAGES:
            return

        self.language = lang
        self.save_now()
        self.refresh_ui_texts()
        self.refresh_tray_menu()

    def refresh_ui_texts(self):
        """Refresh visible UI texts after a language change."""
        self.lbl_filter.configure(text=self.tr("_filter"))
        self.lbl_max_items.configure(text=self.tr("_maxitms"))

        self.tree.heading("pin", text="★")
        self.tree.heading("uses", text=self.tr("_uses"))
        self.tree.heading("ts", text=self.tr("_time"))
        self.tree.heading("preview", text=self.tr("_content"))

        self.tree.column("uses", width=self._uses_column_width())
        self.tree.column("ts", width=self._timestamp_column_width())

        self.after(0, self.resize_to_columns)
        self.after(0, self.move_to_corner)

        self.refresh_status()

    # ----- SORTING MODE -----

    def toggle_sort_mode(self):
        """Toggle between MRC and MFU sorting modes."""
        self.set_sort_mode("mrc" if self.sort_mode == "mfu" else "mfu")

    def set_sort_mode(self, mode: str):
        """Set and persist the active history sorting mode.

        Updates the displayed order, adjusts column visibility and refreshes
        the tray menu. The stored history order remains unchanged.

        Args:
            mode: Sorting mode, either "mrc" or "mfu".
        """
        if mode not in ("mrc", "mfu"):
            return

        self.sort_mode = mode
        self.refresh_list()
        self.apply_treeview_columns()
        self.save_now()
        self.refresh_tray_menu()

    # ----- STATUS LINE -----

    def status_default(self):
        """Set the default status line with history counts and sorting mode."""
        def builder() -> str:
            status = f"{self.tr('_history')}: {len(self.store.items)}"

            if not is_blank(self.search_var.get()):
                status += f" ({self.tr('_showing')} {len(self._filtered_items)})"

            status += f" — {self.tr('_' + self.sort_mode)}"

            return status

        self.set_status_builder(builder)

    def set_status_builder(self, builder):
        """Set the function used to rebuild the status line.

        The builder is stored instead of the final text so the status line can be
        regenerated after a language change.
        """
        self._status_builder = builder
        self.refresh_status()

    def refresh_status(self):
        """Rebuild the current status line text."""
        if self._status_builder is None:
            return
        self.status.set(self._status_builder())

    # ----- USER INTERFACE -----

    def _scale(self, value):
        """Scale a pixel-based UI dimension according to the configured UI scale."""
        return round(value * self.ui_scale)

    def _uses_column_width(self):
        """Calculate the usage column width based on its heading and counter.

        The heading uses TkHeadingFont, while the counter is measured in bold.
        Additional padding is scaled according to the UI scale.
        """
        font = tkfont.nametofont("TkHeadingFont")
        heading_width = font.measure(self.tr("_uses"))

        font = tkfont.nametofont("TkDefaultFont").copy()
        font.configure(weight="bold")
        counter_width = font.measure("00000")

        return max(heading_width, counter_width) + self._scale(24)

    def _timestamp_column_width(self):
        """Calculate the timestamp column width based on its heading and content.

        The heading uses TkHeadingFont, while timestamps are measured in bold.
        Additional padding is scaled according to the UI scale.
        """
        heading_font = tkfont.nametofont("TkHeadingFont")
        heading_width = heading_font.measure(self.tr("_time"))

        font = tkfont.nametofont("TkDefaultFont").copy()
        font.configure(weight="bold")
        content_width = font.measure("0000/00/00-00:00")

        return max(content_width, heading_width) + self._scale(8)

    def _apply_ui_scale(self):
        """Apply the configured UI scale to fonts and ttk widget styles.

        Original font sizes are preserved to prevent cumulative scaling.
        Treeview row height and Spinbox arrow size are scaled separately.
        """
        font_names = (
            "TkDefaultFont",
            "TkTextFont",
            "TkFixedFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
        )

        if not hasattr(self, "_base_font_sizes"):
            self._base_font_sizes = {}

        for name in font_names:
            font = tkfont.nametofont(name)

            if name not in self._base_font_sizes:
                self._base_font_sizes[name] = font.cget("size")

            font.configure(
                size=round(self._base_font_sizes[name] * self.ui_scale)
            )

        style = ttk.Style(self)
        style.configure(
            "Treeview",
            rowheight=self._scale(20)
        )

        style.configure(
            "TSpinbox",
            arrowsize=self._scale(14)
        )

    def _build_ui(self):
        """Create and layout the main application widgets.

        The UI consists of:
            - A filter bar.
            - A clipboard history Treeview with configurable columns.
            - A status line showing history counts and sorting mode.

        Widget callbacks and keyboard shortcuts are configured separately.
        """
        # Top bar
        top = ttk.Frame(
            self,
            padding=(self._scale(10), self._scale(10),
                     self._scale(10), self._scale(6))
        )
        top.pack(fill="x")

        if not self.tray_has_menu:
            self.btn_app_menu = ttk.Button(
                top,
                text="☰",
                width=2,
                command=self._build_window_menu
            )
            self.btn_app_menu.pack(side="left", padx=(0, self._scale(8)))

        self.lbl_filter = ttk.Label(top, text=self.tr("_filter"))
        self.lbl_filter.pack(side="left")

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        self.search_entry.pack(side="left", padx=(self._scale(6), self._scale(10)))
        self.search_var.trace_add("write", lambda *_: self.on_search_changed())

        self.lbl_max_items = ttk.Label(top, text=self.tr("_maxitms"))
        self.lbl_max_items.pack(side="left")

        self.max_var = tk.IntVar(value=self.store.max_items)
        self.max_spin = ttk.Spinbox(top, from_=10, to=500, textvariable=self.max_var, width=6, command=self.on_change_max)
        self.max_spin.pack(side="left", padx=(self._scale(6), self._scale(12)))
        self.max_spin.bind("<Return>", self.on_max_enter)
        self.max_spin.bind("<KP_Enter>", self.on_max_enter)

        # Main area: list
        main = ttk.Frame(
            self,
            padding=(self._scale(10), 0, self._scale(10), self._scale(10))
        )
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        cols = ("pin", "uses", "ts", "preview")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")

        bold_font = tkfont.nametofont("TkDefaultFont").copy()
        bold_font.configure(weight="bold")
        self.tree.tag_configure("current_clipboard", foreground="green", font=bold_font)
        self.tree.tag_configure("msx_clipboard", foreground="white", background="#2020FF", font=bold_font)

        self.tree.heading("pin", text="★")
        self.tree.heading("uses", text=self.tr("_uses"))
        self.tree.heading("ts", text=self.tr("_time"))
        self.tree.heading("preview", text=self.tr("_content"))

        self.tree.column("pin", width=self._scale(PIN_COL_W), anchor="center", stretch=False)
        self.tree.column("uses", width=self._uses_column_width(), anchor="e", stretch=False)
        self.tree.column("ts", width=self._timestamp_column_width(), anchor="center", stretch=False)
        self.tree.column("preview", width=self._scale(PREVIEW_MIN_W), anchor="w", stretch=True)

        self.apply_treeview_columns()

        self.vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)


        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.bind("<Configure>", lambda e: self._fit_preview_column(), add="+")

        # Item menu

        idx = 0
        self.ctx_copy_index = idx; idx += 1
        self.ctx_pin_index = idx; idx += 1
        self.ctx_promote_top_index = idx; idx += 1
        self.ctx_edit_index = idx; idx += 1
        idx += 1
        self.ctx_delete_index = idx; idx += 1
        self.ctx_menu = tk.Menu(self, tearoff=0)
        self.ctx_menu.add_command(label="", command=self.copy_selected)
        self.ctx_menu.add_command(label="", command=self.toggle_pin)
        self.ctx_menu.add_command(label=self.tr("_promote_top"), command=self.promote_selected)
        self.ctx_menu.add_command(label=self.tr("_edit"), command=self.edit_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label=self.tr("_delete"), command=self.delete_selected)

        self.tree.bind("<Button-3>", self._show_item_menu)          # Linux/Windows
        self.tree.bind("<Control-Button-1>", self._show_item_menu)  # macOS

        self.status = tk.StringVar(value="")
        ttk.Label(
            self,
            textvariable=self.status,
            padding=(self._scale(10), 0, self._scale(10), self._scale(8))
        ).pack(fill="x")
        self.status_default()

        self.refresh_list(select_first=True)

        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

        if self.tray_has_menu:
            self.after(0, self.hide_to_tray)
        else:
            self.after(0, self.show_from_tray)

    def _bind_shortcuts(self):
        """Register application keyboard shortcuts and window bindings."""
        def _shortcut(action):
            def handler(event):
                if self.modal_window is None:
                    action()
                return "break"
            return handler

        def _ctrl_f(e):
            if self.focus_get() == self.search_entry:
                self.tree.focus_set()
            else:
                self.after(0, self.search_entry.focus_set)
            return "break"

        self.bind("<Return>", _shortcut(self.copy_selected))
        self.bind("<KP_Enter>", _shortcut(self.copy_selected))
        self.bind("<Delete>", _shortcut(self.delete_selected))
        self.bind("<F2>", _shortcut(self.toggle_pin))
        self.bind("<Control-Home>", _shortcut(self.promote_selected))
        self.bind("<Control-E>", _shortcut(self.edit_selected))
        self.bind("<Control-e>", _shortcut(self.edit_selected))
        self.bind("<Control-F>", _ctrl_f)
        self.bind("<Control-f>", _ctrl_f)
        self.bind("<Control-L>", _shortcut(self.import_clips))
        self.bind("<Control-l>", _shortcut(self.import_clips))
        self.bind("<Control-M>", _shortcut(self.toggle_sort_mode))
        self.bind("<Control-m>", _shortcut(self.toggle_sort_mode))
        self.bind("<Control-R>", _shortcut(self.force_capture))
        self.bind("<Control-r>", _shortcut(self.force_capture))
        self.bind("<Control-S>", _shortcut(self.export_clips))
        self.bind("<Control-s>", _shortcut(self.export_clips))
        self.bind("<Control-T>", _shortcut(self.toggle_timestamp))
        self.bind("<Control-t>", _shortcut(self.toggle_timestamp))
        self.bind("<Control-Shift-A>", _shortcut(self.clear_all))
        self.bind("<Control-Shift-a>", _shortcut(self.clear_all))
        self.bind("<Control-Shift-N>", _shortcut(self.clear_not_matching_filter))
        self.bind("<Control-Shift-n>", _shortcut(self.clear_not_matching_filter))
        self.bind("<Control-Shift-U>", _shortcut(self.clear_unpinned))
        self.bind("<Control-Shift-u>", _shortcut(self.clear_unpinned))

        if self.tray_has_menu:
            self.bind("<Escape>", _shortcut(self.hide_to_tray))
            self.bind("<F6>", _shortcut(self.toggle_hide_after_copy))

        self.bind("<Map>", lambda e: self.move_to_corner())

    # -------- MENUS --------

    def menu_state(self, enabled: bool) -> str:
        """Return the Tkinter menu state corresponding to a boolean value."""
        return "normal" if enabled else "disabled"

    def menu_checked(self, checked: bool) -> str:
        """Return the checked or unchecked prefix used in menu labels."""
        return "■ " if checked else "□ "

    def _add_tk_submenu(self,parent_menu,label,callback):
        """Create and attach a Tk submenu populated by a menu builder."""
        submenu = tk.Menu(parent_menu, tearoff=0)
        callback(submenu, tray=False)
        parent_menu.add_cascade(label=label, menu=submenu)

    def _build_file_menu(self,menu = None, tray: bool = True):
        """Build the File submenu for tray or window menu."""
        force_label = f"{self.tr('_force_capture')} (Ctrl+R)"
        import_label = f"{self.tr('_import')} (Ctrl+L)"
        export_label = f"{self.tr('_export')} (Ctrl+S)"

        if tray:
            return pystray.Menu(
                pystray.MenuItem(force_label,self._tray_call(self.force_capture)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(import_label,self._tray_call(self.import_clips)),
                pystray.MenuItem(export_label,self._tray_call(self.export_clips))
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        menu.add_command(label=force_label,command=self.force_capture)
        menu.add_separator()
        menu.add_command(label=import_label, command=self.import_clips)
        menu.add_command(label=export_label, command=self.export_clips)

    def _build_clear_menu(self,menu = None, tray: bool = True):
        """Build the Clear submenu for tray or window menu."""
        unpinned_label = f"{self.tr('_unpinned')} (Ctrl+Shift+U)"
        all_label = f"{self.tr('_all')} (Ctrl+Shift+A)"
        nmf_label = f"{self.tr('_not_matching_filter')} (Ctrl+Shift+N)"

        if tray:
            return pystray.Menu(
                pystray.MenuItem(unpinned_label, self._tray_call(self.clear_unpinned)),
                pystray.MenuItem(all_label, self._tray_call(self.clear_all)),
                pystray.MenuItem(nmf_label, self._tray_call(self.clear_not_matching_filter), enabled=lambda item: self._has_filter)
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        menu.add_command(label=unpinned_label, command=self.clear_unpinned)
        menu.add_command(label=all_label, command=self.clear_all)
        menu.add_command(label=nmf_label, command=self.clear_not_matching_filter, state=self.menu_state(self._has_filter))

    def _build_config_menu(self,menu = None, tray: bool = True):
        """Build the Config submenu for tray or window menu."""
        if tray:
            sort_menu = self._build_sort_menu()
            position_menu = self._build_position_menu()
            scale_menu = self._build_scale_menu()
            language_menu = self._build_language_menu()

            return pystray.Menu(
                pystray.MenuItem(self.tr("_autocapture"), self._tray_call(self.toggle_auto), checked=lambda item: self.auto_var),
                pystray.MenuItem(f"{self.tr('_show_timestamp')} (Ctrl+T)", self._tray_call(self.toggle_timestamp), checked=lambda item: self.show_timestamp),
                pystray.MenuItem(f"{self.tr('_hide_when_copy')} (F6)", self._tray_call(self.toggle_hide_after_copy), checked=lambda item: self.hide_after_copy),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(f"{self.tr('_sort_mode')} (Ctrl+M)", sort_menu),
                pystray.MenuItem(self.tr("_window_pos"), position_menu),
                pystray.MenuItem(self.tr("_ui_scale"), scale_menu),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self.tr("_language"), language_menu),
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        auto_label = self.menu_checked(self.auto_var) + self.tr("_autocapture")
        menu.add_command(label=auto_label,command=self.toggle_auto)

        timestamp_label = self.menu_checked(self.show_timestamp) + self.tr("_show_timestamp") + " (Ctrl+T)"
        menu.add_command(label=timestamp_label,command=self.toggle_timestamp)

        menu.add_separator()
        self._add_tk_submenu(menu, f"{self.tr('_sort_mode')} (Ctrl+M)", self._build_sort_menu)
        self._add_tk_submenu(menu, self.tr("_window_pos"),self._build_position_menu)
        self._add_tk_submenu(menu, self.tr("_ui_scale"), self._build_scale_menu)

        menu.add_separator()
        self._add_tk_submenu(menu,self.tr("_language"),self._build_language_menu)

    def _build_sort_menu(self, menu=None, tray: bool = True):
        """Build the sorting mode submenu for tray or window menu."""
        modes = ("mrc", "mfu")

        if tray:
            return pystray.Menu(
                *[
                    pystray.MenuItem(
                        self.tr("_" + mode),
                        self._tray_call(self.set_sort_mode, mode),
                        checked=self._checked_equals(
                            lambda: self.sort_mode, mode
                        )
                    )
                    for mode in modes
                ]
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        for mode in modes:
            label = (
                self.menu_checked(self.sort_mode == mode)
                + self.tr("_" + mode)
            )
            menu.add_command(
                label=label,
                command=lambda mode=mode: self.set_sort_mode(mode)
            )

    def _build_position_menu(self,menu = None, tray: bool = True):
        """Build the Position submenu for tray or window menu."""
        if tray:
            return pystray.Menu(
                *[
                    pystray.MenuItem(
                        self.tr("_"+vpos)+" "+self.tr("_"+hpos),
                        self._tray_call(self.set_corner, f"{vpos}-{hpos}"),
                        checked=self._checked_equals(lambda vpos=vpos, hpos=hpos: self.corner, f"{vpos}-{hpos}"),
                    )
                    for vpos in ("top","bottom")
                    for hpos in ("left","right")
                ]
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        for vpos in ("top","bottom"):
            for hpos in ("left","right"):
                pos = f"{vpos}-{hpos}"
                label = self.menu_checked(self.corner == pos) + self.tr("_"+vpos)+" "+self.tr("_"+hpos)
                menu.add_command(
                    label=label,
                    command=lambda pos=pos: self.set_corner(pos)
                )

    def _build_scale_menu(self, menu=None, tray: bool = True):
        """Build the UI Scale submenu for tray or window menu."""
        scales = (1.0, 1.25, 1.5, 1.75, 2.0)

        if tray:
            return pystray.Menu(
                *[
                    pystray.MenuItem(
                        f"{round(scale * 100)}%",
                        self._tray_call(self.set_ui_scale, scale),
                        checked=self._checked_equals(
                            lambda scale=scale: self.ui_scale,
                            scale
                        ),
                    )
                    for scale in scales
                ]
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

        for scale in scales:
            label = (
                self.menu_checked(self.ui_scale == scale)
                + f"{round(scale * 100)}%"
            )
            menu.add_command(
                label=label,
                command=lambda scale=scale: self.set_ui_scale(scale)
            )

    def _build_language_menu(self,menu = None, tray: bool = True):
        """Build the Language submenu for tray or window menu."""
        if tray:
            language_menu = pystray.Menu(
                *[
                    pystray.MenuItem(
                        lang.upper(),
                        self._tray_call(self.set_language, lang),
                        checked=lambda item, lang=lang: self.language == lang,
                    )
                    for lang in locale.SUPPORTED_LANGUAGES
                ]
            )
            return language_menu

        if menu is None:
            raise ValueError("menu is required when tray=False")

        for lang in locale.SUPPORTED_LANGUAGES:
            label = self.menu_checked(self.language == lang) + lang.upper()
            menu.add_command(
                label=label,
                command=lambda lang=lang: self.set_language(lang)
            )

    def _build_tray_menu(self):
        """Build the system tray menu.

        The menu is rebuilt when language or dynamic checked/enabled states change.
        """
        file_menu = self._build_file_menu()
        clear_menu = self._build_clear_menu()
        config_menu = self._build_config_menu()

        return pystray.Menu(
            pystray.MenuItem(self.tr("_show"), self._tray_call(self.show_from_tray), default=True),
            pystray.MenuItem(self.tr("_hide"), self._tray_call(self.hide_to_tray)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("_file"), file_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("_clear"), clear_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("_config"), config_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("_about"), self._tray_call(self.show_about)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.tr("_exit"), self._tray_call(self.quit_app)),
        )

    def _build_window_menu(self):
        """Build and show the in-window fallback menu."""
        if self.modal_window is not None:
            return
        menu = tk.Menu(self, tearoff=0)

        self._add_tk_submenu(menu,self.tr("_file"), self._build_file_menu)
        menu.add_separator()

        self._add_tk_submenu(menu,self.tr("_clear"), self._build_clear_menu)
        menu.add_separator()

        self._add_tk_submenu(menu,label=self.tr("_config"), callback=self._build_config_menu)
        menu.add_separator()

        menu.add_command(label=self.tr("_about"), command=self.show_about)
        menu.add_separator()

        menu.add_command(label=self.tr("_exit"), command=self.quit_app)

        menu.tk_popup(
            self.btn_app_menu.winfo_rootx(),
            self.btn_app_menu.winfo_rooty() + self.btn_app_menu.winfo_height()
        )

    def _show_item_menu(self, event):
        """Show the item menu, updating labels and enabled state."""
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)

        item = self.get_selected_item()
        has_sel = item is not None
        state = "normal" if has_sel else "disabled"

        copy_label = self.tr("_copy")
        if self.hide_after_copy:
            copy_label += " "+self.tr("_and_hide")
        copy_label += " (Enter)"

        pin_label = self.tr("_unpin") if item and item.pinned else self.tr("_pin")
        pin_label += " (F2)"

        self.ctx_menu.entryconfigure(self.ctx_copy_index, label=copy_label)
        self.ctx_menu.entryconfigure(self.ctx_pin_index, label=pin_label)
        self.ctx_menu.entryconfigure(self.ctx_promote_top_index, label=f"{self.tr('_promote_top')} (Ctrl+Home)")
        self.ctx_menu.entryconfigure(self.ctx_edit_index, label=f"{self.tr('_edit')} (Ctrl+E)")
        self.ctx_menu.entryconfigure(self.ctx_delete_index, label=f"{self.tr('_delete')} (Supr)")

        for i in range(self.ctx_menu.index("end") + 1):
            try:
                enabled = state
                if i == self.ctx_promote_top_index and has_sel:
                    enabled = "disabled" if (
                        self.sort_mode == "mfu" or item is self.store.items[0]
                    ) else "normal"
                self.ctx_menu.entryconfigure(i, state=enabled)
            except tk.TclError:
                pass  # separator

        self.ctx_menu.tk_popup(event.x_root, event.y_root)

    # ----- LIST CONTROL -----

    def on_max_enter(self, event):
        """Apply the history limit and return focus to the history list."""
        self.on_change_max()
        self.tree.focus_set()
        return "break"

    def on_change_max(self):
        """Update the maximum number of stored clips.

        The value is clamped to the minimum allowed size, the history is
        trimmed if necessary, and the updated setting is persisted.
        """
        try:
            v = int(self.max_var.get())
            v = max(10, min(v, 500))
            self.max_var.set(v)
            self.store.max_items = v
            self.store._enforce_limit(self.sort_mode)
            self.refresh_list(select_first=False)
            self.save_now()
        except (ValueError, tk.TclError):
            return

    def on_search_changed(self):
        """Update the list and menus after the filter text changes."""
        self.refresh_list()
        self.refresh_tray_menu()

    def on_tree_double_click(self, event):
        """Copy the selected item once per rapid click sequence.

        Ignores consecutive double-click events separated by less than
        500 ms, preventing multiple copies from a single click sequence.
        """
        now = time.monotonic()
        elapsed = now - self._last_double_click
        self._last_double_click = now

        if elapsed >= 0.5:
            self.copy_selected()

        return "break"

    def refresh_list(self, select_first: bool = False, keep_item: Optional[ClipItem] = None):
        """Rebuild the Treeview from the current clipboard history.

        Applies the active text filter and sorts the visible items according
        to the selected mode (MRC or MFU), without modifying the stored order.
        Rebuilds the Treeview rows, highlights the current clipboard item,
        updates the status line and optionally restores the selection.

        Args:
            select_first: Select the first visible item after rebuilding the list.
            keep_item: Keep this item selected if it is still visible.
        """
        def fmt_ts(ts: float) -> str:
            return datetime.fromtimestamp(ts).strftime("%Y/%m/%d-%H:%M")

        sorted_items = self.store.get_sorted_items(self.sort_mode)

        query = self.search_var.get()
        self._has_filter = not is_blank(query)

        if self._has_filter:
            q = query.lower()
            self._filtered_items = [
                it for it in sorted_items if q in it.text.lower()
            ]
        else:
            self._filtered_items = sorted_items

        # Treeview: stable iid + map for the current view
        for row in self.tree.get_children():
            self.tree.delete(row)

        self._view_map = {}  # iid -> ClipItem

        def one_line_preview(s: str, limit: int = 120) -> str:
            s = s.replace("\n", " ⏎ ")
            return s[:limit] + ("…" if len(s) > limit else "")

        for it in self._filtered_items:
            iid = str(id(it))
            self._view_map[iid] = it

            star = "★" if it.pinned else ""
            tags = ()

            if self._last_clipboard and comparison_key(it.text) == self._last_clipboard:
                if "MSX" in it.text.upper():
                    tags = ("msx_clipboard",)
                else:
                    tags = ("current_clipboard",)

            self.tree.insert("", "end", iid=iid, values=(star, it.use_count, fmt_ts(it.ts), one_line_preview(it.text)),tags=tags)

        self.status_default()

        # Selection
        to_select = None
        if keep_item is not None and keep_item in self._filtered_items:
            to_select = str(id(keep_item))
        elif select_first and self._filtered_items:
            to_select = str(id(self._filtered_items[0]))

        if to_select is not None:
            self.tree.selection_set(to_select)
            self.tree.focus(to_select)
            self.tree.see(to_select)

    # ----- CLIPBOARD POLLING -----

    def _prime_clipboard(self):
        """Update the clipboard cache with the current clipboard contents.

        This prevents existing clipboard text from being treated as a new
        clipboard change.
        """
        try:
            text = normalize_line_endings(self.clipboard_get())
            key = comparison_key(text)
            self._last_clipboard = key
        except tk.TclError:
            self._last_clipboard = ""

    def capture_clipboard(self, force: bool = False):
        """Capture clipboard text, optionally ignoring the cached value."""
        try:
            text = normalize_line_endings(self.clipboard_get())
            text_key = comparison_key(text)

            if text_key and (force or text_key != self._last_clipboard):
                added = self.store.add(text, self.sort_mode)
                self._last_clipboard = text_key
                self.refresh_list(select_first=True)

                if added:
                    self.save_now()

        except tk.TclError:
            if self._last_clipboard:
                self._last_clipboard = ""
                self.refresh_list(select_first=False)

    def poll_clipboard(self):
        """Poll the clipboard for changes and schedule the next check."""
        if self.closing:
            return

        try:
            if self.auto_var:
                self.capture_clipboard()
        finally:
            self.after(self.poll_ms, self.poll_clipboard)

    def force_capture(self):
        """Explicitly capture the current clipboard contents."""
        self.capture_clipboard(force=True)

    def sync_clipboard(self, deleted_items):
        """Clear the clipboard only if explicitly deleted items contain
        its current text and no equivalent item remains in the history.
        """
        if not deleted_items:
            return

        try:
            current = comparison_key(self.clipboard_get())
        except tk.TclError:
            return

        if not current:
            return

        deleted_current = any(
            comparison_key(it.text) == current
            for it in deleted_items
        )

        still_stored = any(
            comparison_key(it.text) == current
            for it in self.store.items
        )

        if deleted_current and not still_stored:
            try:
                self.clipboard_clear()
                self._last_clipboard = ""
            except tk.TclError:
                pass

    # ----- ITEM ACTIONS -----

    def get_selected_item(self) -> Optional[ClipItem]:
        """Return the ClipItem associated with the current Treeview selection."""
        sel = self.tree.selection()
        if not sel:
            return None
        return self._view_map.get(sel[0])

    def copy_selected(self):
        """Copy the selected item to the system clipboard.

        On successful copy, increments the item's usage counter and persists
        the updated history. Refreshes the list to highlight the current
        clipboard item, reports the result in the status line and optionally
        hides the window.
        """
        old_last = self._last_clipboard
        item = self.get_selected_item()

        if not item:
            return
        try:
            self.clipboard_clear()
            self._last_clipboard = comparison_key(item.text)
            self.clipboard_append(item.text)
            self.update_idletasks()
            item.use_count += 1
            self.save_now()
            self.refresh_list(select_first=False, keep_item=item)
            self.set_status_builder(lambda: self.tr("_copy_ok"))
        except tk.TclError:
            self._last_clipboard = old_last
            self.set_status_builder(lambda: self.tr("_copy_error"))
        if self.hide_after_copy and self.tray_has_menu:
            self.hide_to_tray()

    def toggle_pin(self):
        """Toggle the pinned state of the selected clipboard item.

        Unpinning an item may cause it to be removed if the history exceeds
        the configured limit. The updated history is then saved.
        """
        item = self.get_selected_item()
        if not item:
            return
        real_idx = self.store.items.index(item)
        self.store.toggle_pin(real_idx)
        self.store._enforce_limit(self.sort_mode)
        self.refresh_list(select_first=False, keep_item=item)
        self.save_now()

    def promote_selected(self):
        """Move the selected item to the top of the clipboard history.

        Only available in MRC mode. The operation preserves the item's
        timestamp and usage counter.
        """
        if self.sort_mode == "mfu":
            return
        item = self.get_selected_item()
        if item is None:
            return

        try:
            self.store.items.remove(item)
        except ValueError:
            return

        self.store.items.insert(0, item)
        self.refresh_list(select_first=False, keep_item=item)
        self.save_now()

    def edit_selected(self):
        """Open a modal editor for the selected clipboard item.

        On save, updates the history using the existing deduplication logic,
        preserving the pinned state and usage counter. If the edited text
        matches another entry, their usage counters are combined and the
        item remains pinned if either entry was pinned.
        """
        if self.modal_window is not None:
            return
        it = self.get_selected_item()
        if not it:
            return

        win = tk.Toplevel(self)
        self.modal_window = win
        win.title(self.tr("_edit"))
        win.transient(self)
        win.grab_set()

        txt = tk.Text(win, wrap="word", width=80, height=20)
        txt.pack(fill="both", expand=True, padx=self._scale(10), pady=self._scale(10))
        txt.insert("1.0", it.text)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=self._scale(10), pady=(0, self._scale(10)))

        def save_edit():
            new_text = txt.get("1.0", "end-1c")

            if new_text.strip():
                edited_item = self.store.edit(it, new_text)
                self.refresh_list(select_first=False, keep_item=edited_item)
                self.save_now()

            self.close_modal()

        ttk.Button(btns, text=self.tr("_save"), command=save_edit).pack(side="right")
        ttk.Button(btns, text=self.tr("_cancel"), command=self.close_modal).pack(side="right", padx=(0, self._scale(8)))

        win.bind("<Escape>", lambda e: (self.close_modal(), "break"))
        win.protocol("WM_DELETE_WINDOW", self.close_modal)
        win.bind("<Control-Return>", lambda e: (save_edit(), "break"))
        win.bind("<Control-KP_Enter>", lambda e: (save_edit(), "break"))

    def delete_selected(self):
        """Delete the selected clipboard item.

        After deletion, the list is refreshed, the first visible item is selected
        when available, and the updated history is saved.
        """
        item = self.get_selected_item()
        if not item:
            return
        real_idx = self.store.items.index(item)
        self.store.delete(real_idx)
        self.sync_clipboard([item])
        self.refresh_list(select_first=True)
        self.save_now()

    # ----- GLOBAL ACTIONS -----

    def import_clips(self):
        """Import clipboard items from an external file.

        The current filter is cleared, the list is refreshed and the updated
        history is persisted.
        """
        filename = filedialog.askopenfilename(
            title=self.tr("_s_file_import"),
            filetypes=FILETYPES
        )

        if filename:
            if self.store.load(filename):
                self.max_var.set(self.store.max_items)
                self.search_var.set("")
                self.refresh_list()
                self.save_now()
            else:
                messagebox.showerror(APP_NAME, self.tr("_import_error"))


    def export_clips(self):
        """Export the current clipboard history to an external file."""
        filename = filedialog.asksaveasfilename(
            title=self.tr("_s_file_export"),
            defaultextension=".json",
            filetypes=FILETYPES
        )
        if filename:
            try:
                self.store.save(filename)
            except Exception as exc:
                messagebox.showerror(APP_NAME, self.tr("_export_error"))

    def _clear(self,message,callback):
        """Execute a clear operation after user confirmation.

        If confirmed, the supplied callback is executed, the list is refreshed
        and the updated history is saved.

        Returns:
            True if the operation was confirmed and executed, False otherwise.
        """
        if not messagebox.askyesno(APP_NAME, self.tr(message)):
            return False

        previous_items = list(self.store.items)
        callback()
        deleted_items = [
            it for it in previous_items
            if it not in self.store.items
        ]
        self.sync_clipboard(deleted_items)
        self.refresh_list(select_first=True)
        self.save_now()
        return True

    def clear_unpinned(self):
        """Delete all unpinned clipboard items."""
        self._clear("_q_clear_unpinned", self.store.clear_unpinned)

    def clear_all(self):
        """Delete all clipboard items and clear the active filter."""
        if self._clear("_q_clear_all", self.store.clear_all):
            self.search_var.set("")

    def clear_not_matching_filter(self):
        """Delete all items that do not match the current text filter.

        The filter is cleared after a successful operation.
        """
        if not self._has_filter:
            return

        if self._clear(
            "_q_clear_not_matching_filter",
            lambda: self.store.clear_not_matching_filter(
                self.search_var.get()
            )
        ):
            self.search_var.set("")

    def toggle_auto(self):
        """Toggle automatic clipboard capture for the current session only.

        Auto-capture is intentionally not persisted because ClipStack is expected
        to start with clipboard monitoring enabled.
        """
        self.auto_var = not self.auto_var

        if self.auto_var:
            self._prime_clipboard()

    def toggle_timestamp(self):
        """Toggle timestamp column visibility."""
        self.show_timestamp = not self.show_timestamp
        self.apply_treeview_columns()
        self.save_now()
        self.refresh_tray_menu()

    def toggle_hide_after_copy(self):
        """Toggle whether copying an item hides the main window."""
        self.hide_after_copy = not self.hide_after_copy
        self.save_now()
        self.refresh_tray_menu()
        self.set_status_builder(
            lambda: f"{self.tr('_hide_when_copy')}: "
                    f"{self.tr('_enabled') if self.hide_after_copy else self.tr('_disabled')}"
        )

    def set_corner(self, corner: str):
        """Set the preferred screen corner for the main window."""
        self.corner = corner
        self.move_to_corner()
        self.save_now()

    def set_ui_scale(self, scale: float):
        """Set the UI scale and restart ClipStack."""
        if scale == self.ui_scale:
            return

        self.ui_scale = scale
        self.restart_app()

    def save_now(self):
        """Save clipboard history and user preferences to disk."""
        try:
            self.store.save(
                self.save_path,
                settings={
                    "language": self.language,
                    "corner": self.corner,
                    "sort_mode": self.sort_mode,
                    "show_timestamp": self.show_timestamp,
                    "hide_after_copy": self.hide_after_copy,
                    "ui_scale": self.ui_scale
                }
            )
        except Exception as exc:
            print(f"Save failed: {exc}")

    # ----- WINDOW CONTROL -----

    def hide_to_tray(self):
        """Hide the window while keeping the application running."""
        self.save_now()
        self.withdraw()

    def move_to_corner(self, corner: Optional[str] = None):
        """Move the window to the selected screen corner.

        If the window has not been fully realized yet, required dimensions are
        used as a fallback because Tk may still report a size of 1x1.
        """
        # Ensure geometry information is up to date before calculating the target
        # corner position.
        self.update_idletasks()

        win_w = self.winfo_width()
        win_h = self.winfo_height()
        if win_w <= 1 or win_h <= 1:
            win_w = self.winfo_reqwidth()
            win_h = self.winfo_reqheight()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        corner = corner or self.corner

        positions = {
            "top-left": (0, 0),
            "top-right": (screen_w - win_w, 0),
            "bottom-left": (0, screen_h - win_h),
            "bottom-right": (screen_w - win_w, screen_h - win_h),
        }
        x, y = positions.get(
            corner,
            (screen_w - win_w, 0)
        )

        self.geometry(f"+{x}+{y}")

    def _fit_preview_column(self):
        """Resize the preview column to fill the available Treeview width.

        Visible fixed-width columns (pin, uses and timestamp) retain their
        widths. The preview column occupies the remaining horizontal space.
        """
        container_w = self.tree.master.winfo_width()
        if container_w <= 1:
            return

        vsb_w = self.vsb.winfo_width() if hasattr(self, "vsb") else 0

        pin_w = int(self.tree.column("pin", "width"))
        uses_w = int(self.tree.column("uses", "width")) if "uses" in self.tree["displaycolumns"] else 0
        ts_visible = "ts" in self.tree["displaycolumns"]
        ts_w = int(self.tree.column("ts", "width")) if ts_visible else 0

        # Small safety margin to avoid clipping and geometry rounding issues.
        margin = self._scale(12)

        new_w = max(self._scale(PREVIEW_COL_MIN_W), container_w - vsb_w - pin_w - uses_w - ts_w - margin)
        self.tree.column("preview", width=new_w)

    def apply_treeview_columns(self):
        """Configure visible Treeview columns and recalculate window layout.

        The usage column is displayed only in MFU mode, while the timestamp
        column depends on the user preference. The preview column always
        remains last and fills the available space.

        Updates the window dimensions and position accordingly.
        """
        columns = ["pin"]
        if self.sort_mode == "mfu": columns.append("uses")
        if self.show_timestamp: columns.append("ts")
        columns.append("preview")

        self.tree["displaycolumns"] = tuple(columns)

        self.after(0, self._fit_preview_column)
        self.after(0, self.resize_to_columns)
        self.after(0, self.move_to_corner)

    def resize_to_columns(self):
        """Resize the window to fit the currently visible Treeview columns.

        Calculates the required width from the visible fixed-width columns,
        the minimum preview width and the surrounding interface elements.
        Users can manually resize the window afterwards.
        """
        fixed_w = self._scale(PIN_COL_W)
        if "uses" in self.tree["displaycolumns"]:
            fixed_w += int(self.tree.column("uses", "width"))
        if self.show_timestamp:
            fixed_w += self._timestamp_column_width()

        # Approximate space for scrollbar, borders and internal padding.
        chrome_w = self._scale(40)

        new_w = fixed_w + self._scale(PREVIEW_MIN_W) + chrome_w
        cur_h = self.winfo_height()

        self.geometry(f"{new_w}x{cur_h}")
        self.minsize(new_w, self.winfo_reqheight())

    def on_tree_click(self, event):
        """Prevent manual resizing of Treeview columns."""
        region = self.tree.identify_region(event.x, event.y)

        # Existing code to prevent column resizing
        if region == "separator":
            return "break"

        # Click on pin column?
        column = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)

        if region == "cell" and column == "#1" and row:
            self.tree.selection_set(row)
            self.toggle_pin()
            return "break"

    def _reposition_after_show(self):
        """Reposition the window after it becomes visible.

        Some window managers apply geometry changes slightly after the window is
        mapped, so the position is applied twice: immediately and again shortly
        afterwards.
        """
        self.update_idletasks()
        self.move_to_corner()
        self.after(50, self.move_to_corner)

    def show_from_tray(self):
        """Restore and focus the main window from the system tray.

        The window position is reapplied after it becomes visible to account for
        delayed geometry updates performed by some window managers.
        """
        self.deiconify()
        self.state("normal")
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass

        self.after_idle(self._reposition_after_show)

    # ----- TRAY ICON -----

    def _tray_call(self, fn, *args, **kwargs):
        """Return a pystray callback that runs `fn` on the Tk thread."""
        def _run():
            if self.modal_window is None:
                fn(*args, **kwargs)

        def _action(icon, item):
            self.after(0, _run)

        return _action

    def _checked_equals(self, getter, value):
        """Return a pystray checked callback comparing `getter()` with `value`."""
        return lambda item: getter() == value

    def setup_tray(self):
        """Create and start the system tray icon in a daemon thread."""
        if self.tray_icon is not None:
            return

        image = ICON_IMAGE
        menu = self._build_tray_menu()
        self.tray_icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)

        def run_icon():
            try:
                self.tray_icon.run()
            except Exception:
                # If the tray fails, keep the Tk app running.
                pass

        self.tray_thread = threading.Thread(target=run_icon, daemon=True)
        self.tray_thread.start()

    def refresh_tray_menu(self):
        """Rebuild and refresh the tray menu.

        This is needed when labels, checked states or enabled states change.
        """
        if self.tray_icon is None:
            return
        try:
            self.tray_icon.menu = self._build_tray_menu()
            self.tray_icon.update_menu()
        except Exception:
            pass

    # ----- ABOUT -----

    def check_for_updates(self, win, update_var, update_button):
        """Check whether a newer ClipStack version is available."""
        update_var.set(self.tr("_update_checking"))
        update_button.config(state="disabled")

        def worker():
            url = "https://api.github.com/repos/SapphiRe-MSX/clipstack/releases/latest"

            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    data = json.load(response)
                latest_version = data["tag_name"].lstrip("v")

                current = tuple(map(int, APP_VERSION.split(".")))
                latest = tuple(map(int, latest_version.split(".")))

                if current < latest:
                    message = self.tr("_update_available").format(version=latest_version)
                elif current > latest:
                    message = self.tr("_update_newer")
                else:
                    message = self.tr("_update_current")

            except Exception:
                message = self.tr("_update_error")

            def show_result():
                if self.modal_window is win:
                    win.update_idletasks()

                    center_x = win.winfo_x() + win.winfo_width() // 2
                    center_y = win.winfo_y() + win.winfo_height() // 2

                    update_var.set(message)
                    update_button.config(state="normal")

                    win.update_idletasks()

                    x = center_x - win.winfo_width() // 2
                    y = center_y - win.winfo_height() // 2

                    win.geometry(f"+{x}+{y}")

            self.after(0, show_result)

        threading.Thread(target=worker, daemon=True).start()

    def show_about(self):
        """Show information about ClipStack."""
        if self.modal_window is not None:
            return
        win = tk.Toplevel(self)
        self.modal_window = win
        win.about_icon = tk.PhotoImage(data=ICON_B64)
        win.title(self.tr("_about"))
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=self._scale(20))
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame)
        header.pack(pady=(0, self._scale(16)))

        ttk.Label(header, image=win.about_icon).pack(side="left", padx=(0, self._scale(16)))

        info = ttk.Frame(header)
        info.pack(side="left")

        ttk.Label(info, text=APP_NAME, font=("TkDefaultFont", self._scale(14), "bold")).pack(anchor="w")
        ttk.Label(info, text=f"{self.tr('_version')} {APP_VERSION}").pack(anchor="w", pady=(self._scale(4), 0))
        ttk.Label(info, text="SapphiRe-MSX").pack(anchor="w", pady=(self._scale(4), 0))

        update_button = ttk.Button(frame, text=self.tr("_check_updates"))
        update_button.configure(command=lambda: self.check_for_updates(win, update_var, update_button))
        update_button.pack(pady=(0, self._scale(8)))

        update_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=update_var).pack(pady=(0, self._scale(8)))

        ttk.Button(frame, text=self.tr("_close"), command=self.close_modal).pack()


        win.bind("<Escape>", lambda e: (self.close_modal(), "break"))
        win.protocol("WM_DELETE_WINDOW", self.close_modal)

    # ----- MODAL WINDOWS -----

    def close_modal(self):
        """Close the current modal window."""
        if self.modal_window is not None:
            self.modal_window.destroy()
            self.modal_window = None

    # ----- RESTART/QUIT THE APP -----

    def prepare_shutdown(self):
        """Save the current state and stop the tray icon before exiting or restarting."""
        self.closing = True
        self.save_now()

        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

        self.update()

    def restart_app(self):
        """Restart ClipStack in the current process, preserving command-line arguments."""
        self.prepare_shutdown()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def quit_app(self):
        """Shut down ClipStack cleanly and destroy the main Tk window."""
        self.prepare_shutdown()
        self.destroy()

def parse_args():
    """Parse and return the application command-line arguments."""
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Disable system tray integration and show the in-window menu.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    app = ClipStackApp(no_tray=args.no_tray)
    app.mainloop()

