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
import time
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# -------- Configuration --------
APP_NAME = "ClipStack"
MAX_ITEMS_DEFAULT = 50
POLL_MS_DEFAULT = 600
SAVE_FILENAME = ".clipstack_history.json"
FILETYPES = [ ('clip files', '*.json') ]

# -------- UI Columns --------
PIN_COL_W = 26
TS_COL_W = 120
PREVIEW_COL_MIN_W = 120
PREVIEW_MIN_W = 520

# -------- Icon --------
TRAY_ICON_PNG_B64 = """
iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAdnJLH8AAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAAlwSFlzAAAuIwAALiMBeKU/dgAAAAd0SU1FB+oBCg4HLF7RjL4AAARkSURBVHja7ZtdTBxVFMd/d2aXZXaXhYJUbGpqlKJiocTWl/KgSUPSNMUqlRTQtmIsVvqFNSbESDFCbTQmWGkaNamVNn3oQzUtmzSmtInUWK2RSAIYWRI+UmxNLRRw6dLdnfFBTGxTZWZZZHZ2/8k8TO4598785szZczZzIc4lDNimATmA3UTXrwE/AMG5XEQBmoGb0wua7WieywiQgTNAUXFx+R/rni4TTsXlMsOjvz5yjZpd5X+fVgKfRzKPbYbxSqDotT0N/urttYos22SzxP7VK5f/efox8Atw0eg80gzjLwPhzVu2q2a6+Tt0cjoHnAQWRxvA8k2bdwRSUxekmDiRdwFbgCzgy+mcFTUAyZmZWS7Mry+ARmAlcNjIr5uEdfQ2cBooB2rjEYAKvAD0AA1AcbwBAJgAngHGgeNAbrwBAPABFYATOAWkz6YOiAXtnA79OxUCsoFWoNByAFI8acHKl2q0qUAg/d+e8k+dl+jp7lhlyQhwudz2ur1N/2lzsHkfPd0dRB2AvXkf4pN3jTnlriTYcgZNcZoKZGQR8NswPLQMrWi9PvufOxHffAXBW2AJAICWt4Lgjjf1LdJ64i8AJtT/mgPG+n1qx84KSRvqi/rc2cfbuL9wtbkBJHlSpfSKKrTgrajP7czMMn8EKBkLyd/2Rvy+AndT95Fm/L4eQz5yioe8XXUkudyzXn/eS2E1FAwbd1JV0MKWiIC8rXvk+XxwEQMQl9qxv1Wtz3bAZ9qKMiIA2vInjNk/sBSWrUBzJFsDQKi0EkorLdE7W/H/gLmPgCviMiPid2NFkOZgqfaoNQAckj7AK84Z9vs6fAGPlmaNQmgVBVSrr+uybRdtfCparNUMpWsZPKYW6LLtl3wgoH/cp+7uqZCGtOg3Q8eWtFF4n8mbIU9SmlSeWkVQi34zlJkcA81QRnImrzySaIZuU+vAidDgzT5D1+GU3Wr5g1slxeaMfQAd49/aWiY/MuTzuFwolaovWiMC6vMPUM+B2HsFJsUkV8WwLttRMWKtShDgPBc5L6+Jz1J4k1rFGrHekI8DB27NYw0AOVouOVouVlCiG4zE6ezZMXp9xr5NdLkEz1ekY7eL2AfQfiGA91yIsKozzAQIASXPhrHbbbEPAGDdahsN79yry9brvUHdfj/Dw2Nq04ddUiikRf1GNpRkU1Cw2Nw5QAghWSIHRKpFizzU730y0Qzd/np0hwaHJow1Q06bWrYxX1KUpNgH8N3316TTbROGfB5eYhMbSsJBRZn9p/vzDqCx4SmpscF4OiFK+xYShVCkjgODKl7vDV22P3ZMWQuA2y3o6lPp2u/X7bNwgUCWhTUA1Oy+h1e3qYZ8ZFngcsnWAOBwSDgc1kgfcZ8EEwBmGPePjl4PxDOAziOfNdn8/onJeAVwGLAdO3ooFA6HQ/FYCLUAZe+/V1vU29vtX7v2uSnFJBsndRVrUfo2SQEOAgHMuXV2pmN8pqZCr8y4eVqPfgX6Seju+hN5o3yx1M0+FQAAAABJRU5ErkJggg==
""".strip()

# -------- Utilities --------

def get_save_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, SAVE_FILENAME)

def comparison_key(text: str) -> str:
    """Return a normalized key for comparisons and searches."""
    return normalize_line_endings(text).strip()

def is_blank(text: str) -> str:
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
        ts: Unix timestamp (float) of last capture/promote (used for display/aging).
        pinned: If True, item is protected from bulk cleanup and (optionally) limits.
    """

    __slots__ = ("text", "ts", "pinned")

    def __init__(self, text: str, ts: Optional[float] = None, pinned: bool = False):
        """Create a new clipboard item.

        Args:
            text: Clipboard text.
            ts: Optional timestamp. If None, current time is used.
            pinned: Whether the item is pinned.
        """
        self.text = text
        self.ts = ts if ts is not None else time.time()
        self.pinned = pinned

    def to_dict(self):
        """Serialize the item to a JSON-compatible dictionary."""
        return {"text": self.text, "ts": self.ts, "pinned": self.pinned}

    @staticmethod
    def from_dict(d):
        """Create a ClipItem from a dictionary (loaded from JSON)."""
        return ClipItem(d.get("text", ""), d.get("ts", time.time()), bool(d.get("pinned", False)))

######################
# HistoryStore Class #
######################

class HistoryStore:
    """In-memory clipboard history + JSON persistence.

    Responsibilities:
        - Maintain items as MRU (most-recent-first).
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

    def add(self, text: str) -> bool:
        """Add text to history using MRU + de-duplication.

        If the normalized text already exists, the existing item is promoted to the
        top of the list and its timestamp is updated. Otherwise, a new ClipItem is
        inserted at the top. Empty/whitespace-only text is ignored.

        Args:
            text: Clipboard text to add.

        Returns:
            True if a new item was inserted or an existing item was promoted.
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
        self._enforce_limit()
        return True

    def toggle_pin(self, idx: int):
        """Toggle the pinned flag for the item at index `idx` (if valid)."""
        if 0 <= idx < len(self.items):
            self.items[idx].pinned = not self.items[idx].pinned

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

    def _enforce_limit(self):
        """Enforce `max_items` while preserving pinned items (if any).

        Policy:
            - If there are pinned items, keep all pinned items and fill remaining
              slots with most recent unpinned items.
            - If no pinned items exist, truncate to `max_items`.
        """
        if len(self.items) <= self.max_items:
            return
        # Respect pinned items: first try trimming from the end removing unpinned.
        if any(it.pinned for it in self.items):
            kept = []
            pinned = [it for it in self.items if it.pinned]
            unpinned = [it for it in self.items if not it.pinned]

            kept = pinned[:]
            room = max(self.max_items - len(kept), 0)
            kept += unpinned[:room]
            # Rebuild preserving the original MRU order in self.items.
            kept_set = set(id(x) for x in kept)
            self.items = [it for it in self.items if id(it) in kept_set]
        else:
            self.items = self.items[: self.max_items]

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

    def load(self, path: str):
        """Load history (and settings) from a JSON file.

        If the file does not exist or is invalid/corrupted, the store is reset to
        an empty state (no exception is raised).
        """
        if not os.path.exists(path):
            self.settings = {}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.max_items = data.get("max_items", self.max_items)
            self.items = [ClipItem.from_dict(x) for x in data.get("items", [])]
            self.settings = data.get("settings", {})
        except Exception:
            # If the file is corrupt, don't break the app; start empty.
            self.items = []

######################
# ClipStackApp Class #
######################

class ClipStackApp(tk.Tk):
    """Tkinter application: UI + tray integration + clipboard polling.

    Responsibilities:
        - Render the Treeview list and item menu actions (copy/pin/edit/delete).
        - Poll the system clipboard (optional) and push changes into HistoryStore.
        - Run a system tray icon (pystray) and forward tray actions to the Tk thread.

    Threading model:
        - Tk must be accessed from the Tk main thread.
        - Tray callbacks must use `after(0, ...)` to run on the Tk thread.
    """

    def __init__(self, no_tray: bool = False):
        """Initialize the application, load settings, build UI and start services."""

        super().__init__()

        # Hide immediately to avoid startup flicker when launching to tray.
        self.withdraw()

        self.title(APP_NAME)

        # Window icon. Keep a reference to avoid Tk garbage-collecting it.
        self._window_icon = tk.PhotoImage(data=TRAY_ICON_PNG_B64)
        self.iconphoto(True, self._window_icon)

        # Load persisted history and settings.
        self.store = HistoryStore()
        self.save_path = get_save_path()
        self.store.load(self.save_path)

        self.language = self.store.settings.get("language", "es")
        self.corner = self.store.settings.get("corner", "top-right")
        self.show_timestamp = self.store.settings.get("show_timestamp", True)
        self.hide_after_copy = self.store.settings.get("hide_after_copy", True)
        self.auto_var = tk.BooleanVar(value=self.store.settings.get("auto_capture", True))


        # Runtime state.
        self.poll_ms = POLL_MS_DEFAULT
        self._last_clipboard = None
        self._has_filter = False
        self._filtered_items = []
        self._status_builder = None

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

        self._build_ui()
        self._bind_shortcuts()

        # Do not capture the pre-existing clipboard content at startup.
        self._prime_clipboard()
        self.after(400, self.poll_clipboard)


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
        self.tree.heading("ts", text=self.tr("_time"))
        self.tree.heading("preview", text=self.tr("_content"))

        self.refresh_status()

    # ----- STATUS LINE -----

    def status_default(self):
        """Set the status line to the default history/filter counter."""
        def builder() -> str:
            status = f"{self.tr('_history')}: {len(self.store.items)}"

            if not is_blank(self.search_var.get()):
                status += f" ({self.tr('_showing')} {len(self._filtered_items)})"

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

    def _build_ui(self):
        """Create and layout the main application widgets.

        The UI consists of:
            - A filter bar.
            - Clipboard history Treeview.
            - Status line.

        Widget callbacks and keyboard shortcuts are configured separately.
        """
        # Top bar
        top = ttk.Frame(self, padding=(10, 10, 10, 6))
        top.pack(fill="x")

        if not self.tray_has_menu:
            self.btn_app_menu = ttk.Button(
                top,
                text="☰",
                width=2,
                command=self._build_window_menu
            )
            self.btn_app_menu.pack(side="left", padx=(0, 8))

        self.lbl_filter = ttk.Label(top, text=self.tr("_filter"))
        self.lbl_filter.pack(side="left")

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        self.search_entry.pack(side="left", padx=(6, 10))
        self.search_var.trace_add("write", lambda *_: self.on_search_changed())

        self.lbl_max_items = ttk.Label(top, text=self.tr("_maxitms"))
        self.lbl_max_items.pack(side="left")

        self.max_var = tk.IntVar(value=self.store.max_items)
        self.max_spin = ttk.Spinbox(top, from_=10, to=500, textvariable=self.max_var, width=6, command=self.on_change_max)
        self.max_spin.pack(side="left", padx=(6, 12))

        # Main area: list
        main = ttk.Frame(self, padding=(10, 0, 10, 10))
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        cols = ("pin", "ts", "preview")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")

        bold_font = tkfont.nametofont("TkDefaultFont").copy()
        bold_font.configure(weight="bold")
        self.tree.tag_configure("current_clipboard", foreground="green", font=bold_font)

        self.tree.heading("pin", text="★")
        self.tree.heading("ts", text=self.tr("_time"))
        self.tree.heading("preview", text=self.tr("_content"))

        self.tree.column("pin", width=PIN_COL_W, anchor="center", stretch=False)
        self.tree.column("ts", width=TS_COL_W, anchor="center", stretch=False)
        self.tree.column("preview", width=PREVIEW_MIN_W, anchor="w", stretch=True)

        self.apply_treeview_columns()

        self.vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)


        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-1>", self._disable_treeview_resize, add="+")
        self.tree.bind("<Configure>", lambda e: self._fit_preview_column(), add="+")

        # Item menu

        self.ctx_copy_index = 0
        self.ctx_pin_index = 1
        self.ctx_edit_index = 2
        self.ctx_delete_index = 4
        self.ctx_menu = tk.Menu(self, tearoff=0)
        self.ctx_menu.add_command(label="", command=self.copy_selected)
        self.ctx_menu.add_command(label="", command=self.toggle_pin)
        self.ctx_menu.add_command(label=self.tr("_edit"), command=self.edit_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label=self.tr("_delete"), command=self.delete_selected)

        self.tree.bind("<Button-3>", self._show_item_menu)          # Linux/Windows
        self.tree.bind("<Control-Button-1>", self._show_item_menu)  # macOS

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, padding=(10, 0, 10, 8)).pack(fill="x")
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
        self.bind("<Control-E>", _shortcut(self.edit_selected))
        self.bind("<Control-e>", _shortcut(self.edit_selected))
        self.bind("<Control-F>", _ctrl_f)
        self.bind("<Control-f>", _ctrl_f)
        self.bind("<Control-L>", _shortcut(self.import_clips))
        self.bind("<Control-l>", _shortcut(self.import_clips))
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
        self.bind("<F2>", _shortcut(self.toggle_pin))

        if self.tray_has_menu:
            self.bind("<Escape>", _shortcut(self.hide_to_tray))
            self.bind("<F6>", _shortcut(self.toggle_hide_after_copy))

        self.bind("<Map>", lambda e: self.move_to_corner())

    # -------- MENUS --------

    def menu_state(self, enabled: bool) -> str:
        return "normal" if enabled else "disabled"

    def menu_checked(self, checked: bool) -> str:
        return "■ " if checked else "□ "

    def _add_tk_submenu(self,parent_menu,label,callback):
        """Create and attach a Tk submenu populated by a menu builder."""
        submenu = tk.Menu(parent_menu, tearoff=0)
        callback(submenu, tray=False)
        parent_menu.add_cascade(label=label, menu=submenu)

    def _build_file_menu(self,menu = None, tray: bool = True):
        """Build the File submenu for tray or window menu."""
        import_label = f"{self.tr('_import')} (Ctrl+L)"
        export_label = f"{self.tr('_export')} (Ctrl+S)"

        if tray:
            return pystray.Menu(
                pystray.MenuItem(import_label,self._tray_call(self.import_clips)),
                pystray.MenuItem(export_label,self._tray_call(self.export_clips))
            )

        if menu is None:
            raise ValueError("menu is required when tray=False")

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
            position_menu = self._build_position_menu()
            language_menu = self._build_language_menu()

            return pystray.Menu(
                pystray.MenuItem(self.tr("_autocapture"), self._tray_call(self.toggle_auto), checked=lambda item: self.auto_var),
                pystray.MenuItem(f"{self.tr('_show_timestamp')} (Ctrl+T)", self._tray_call(self.toggle_timestamp), checked=lambda item: self.show_timestamp),
                pystray.MenuItem(f"{self.tr('_hide_when_copy')} (F6)", self._tray_call(self.toggle_hide_after_copy), checked=lambda item: self.hide_after_copy),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self.tr("_window_pos"), position_menu),
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
        self._add_tk_submenu(menu,self.tr("_window_pos"),self._build_position_menu)

        menu.add_separator()
        self._add_tk_submenu(menu,self.tr("_language"),self._build_language_menu)

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
            pystray.MenuItem(self.tr("_exit"), self._tray_call(self.quit_app)),
        )

    def _build_window_menu(self):
        """Build and show the in-window fallback menu."""

        menu = tk.Menu(self, tearoff=0)

        self._add_tk_submenu(menu,self.tr("_file"), self._build_file_menu)
        menu.add_separator()

        self._add_tk_submenu(menu,self.tr("_clear"), self._build_clear_menu)
        menu.add_separator()

        self._add_tk_submenu(menu,label=self.tr("_config"), callback=self._build_config_menu)
        menu.add_separator()

        menu.add_command(label=self.tr("_exit"), command=self.quit_app)

        menu.tk_popup(
            self.btn_app_menu.winfo_rootx(),
            self.btn_app_menu.winfo_rooty() + self.btn_app_menu.winfo_height()
        )

    def _show_item_menu(self, event):
        """Show the item item menu, updating labels and enabled state."""

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
        self.ctx_menu.entryconfigure(self.ctx_edit_index, label=f"{self.tr('_edit')} (Ctrl+E)")
        self.ctx_menu.entryconfigure(self.ctx_delete_index, label=f"{self.tr('_delete')} (Supr)")

        for i in range(self.ctx_menu.index("end") + 1):
            try:
                self.ctx_menu.entryconfigure(i, state=state)
            except tk.TclError:
                pass  # separator

        self.ctx_menu.tk_popup(event.x_root, event.y_root)

    # ----- LIST CONTROL -----

    def on_change_max(self):
        """Update the maximum number of stored clips.

        The value is clamped to the minimum allowed size, the history is
        trimmed if necessary, and the updated setting is persisted.
        """
        try:
            v = int(self.max_var.get())
            if v < 10:
                v = 10
            self.store.max_items = v
            self.store._enforce_limit()
            self.refresh_list(select_first=False)
            self.save_now()
        except (ValueError, tk.TclError):
            return

    def on_search_changed(self):
        """Update the list and menus after the filter text changes."""
        self.refresh_list()
        self.refresh_tray_menu()

    def on_tree_double_click(self, event):
        """Copy the selected item when a Treeview row is double-clicked."""
        self.copy_selected()
        return "break"

    def refresh_list(self, select_first: bool = False, keep_item: Optional[ClipItem] = None):
        """Rebuild the Treeview from the current clipboard history.

        Applies the active text filter, rebuilds the visible item cache, updates
        the Treeview rows, highlights the item currently present in the system
        clipboard, refreshes the status line and optionally restores selection.

        Args:
            select_first: Select the first visible item after rebuilding the list.
            keep_item: Keep this item selected if it is still visible after refresh.
        """
        def fmt_ts(ts: float) -> str:
            return datetime.fromtimestamp(ts).strftime("%Y/%m/%d-%H:%M")

        self.sync_clipboard()

        query = self.search_var.get()
        self._has_filter = not is_blank(query)
        if not is_blank(query):
            q = query.lower()
            self._filtered_items = [it for it in self.store.items if q in it.text.lower()]
        else:
            self._filtered_items = list(self.store.items)

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
                tags = ("current_clipboard",)

            self.tree.insert("", "end", iid=iid, values=(star, fmt_ts(it.ts), one_line_preview(it.text)),tags=tags)

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
        """Initialize the clipboard cache with the current clipboard contents.

        This prevents existing clipboard text from being added to the history
        when ClipStack starts.
        """
        try:
            self._last_clipboard = comparison_key(self.clipboard_get())
        except tk.TclError:
            self._last_clipboard = ""

    def poll_clipboard(self):
        """Poll the system clipboard for changes.

        New textual clipboard contents are normalized and added to the history.
        Non-textual clipboard contents and clipboard access errors are ignored.

        The polling loop reschedules itself continuously using Tk's event queue.
        """
        try:
            if self.auto_var:
                text = normalize_line_endings(self.clipboard_get())
                text_key = comparison_key(text)
                if text_key and text_key != self._last_clipboard:
                    added = self.store.add(text)
                    self._last_clipboard = text_key
                    self.refresh_list(select_first=True)
                    if added:
                        self.save_now()
        except tk.TclError:
            # Clipboard unavailable, empty or contains non-textual data.
            if self._last_clipboard:
                self._last_clipboard = ""
                self.refresh_list(select_first=False)
        finally:
            self.after(self.poll_ms, self.poll_clipboard)

    def sync_clipboard(self):
        """Clear the system clipboard if the current clip is no longer stored."""

        if self._last_clipboard and not any(
            comparison_key(it.text) == self._last_clipboard
            for it in self.store.items
        ):
            try:
                self.clipboard_clear()
            except tk.TclError:
                pass

            self._last_clipboard = ""

    # ----- ITEM ACTIONS -----

    def get_selected_item(self) -> Optional[ClipItem]:
        """Return the ClipItem associated with the current Treeview selection."""
        sel = self.tree.selection()
        if not sel:
            return None
        return self._view_map.get(sel[0])

    def copy_selected(self):
        """Copy the selected clipboard item to the system clipboard.

        Updates the cached clipboard value, refreshes the list so the current
        clipboard item is highlighted, reports the result in the status line and
        optionally hides the window after copying.
        """
        item = self.get_selected_item()
        if not item:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(item.text)
            self._last_clipboard = comparison_key(item.text)
            self.refresh_list(select_first=False, keep_item=item)
            self.set_status_builder(lambda: self.tr("_copy_ok"))
        except tk.TclError:
            self.set_status_builder(lambda: self.tr("_copy_error"))
        if self.hide_after_copy and self.tray_has_menu:
            self.hide_to_tray()

    def toggle_pin(self):
        """Toggle the pinned state of the selected clipboard item.

        The current selection is preserved and the updated history is saved.
        """
        item = self.get_selected_item()
        if not item:
            return
        real_idx = self.store.items.index(item)
        self.store.toggle_pin(real_idx)
        self.refresh_list(select_first=False, keep_item=item)
        self.save_now()

    def edit_selected(self):
        """Open a modal editor for the selected clipboard item."""
        it = self.get_selected_item()
        if not it:
            return

        win = tk.Toplevel(self)
        win.title(self.tr("_edit"))
        win.transient(self)
        win.grab_set()

        txt = tk.Text(win, wrap="word", width=80, height=20)
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", it.text)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=(0, 10))

        def save_edit():
            new_text = txt.get("1.0", "end-1c")

            if not new_text.strip():
                win.destroy()
                return

            it.text = new_text
            it.ts = time.time()
            # Remove the old item, then add the edited text through the store so
            # MRU promotion and de-duplication stay consistent.
            real_idx = self.store.items.index(it)
            self.store.delete(real_idx)
            self.store.add(new_text)

            edited_item = self.store.items[0]
            self.refresh_list(select_first=False, keep_item=edited_item)
            self.save_now()
            win.destroy()

        ttk.Button(btns, text=self.tr("_save"), command=save_edit).pack(side="right")
        ttk.Button(btns, text=self.tr("_cancel"), command=win.destroy).pack(side="right", padx=(0, 8))

        win.bind("<Escape>", lambda e: (win.destroy(), "break"))
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
            self.store.load(filename)
            self.search_var.set("")
            self.refresh_list()
            self.save_now()

    def export_clips(self):
        """Export the current clipboard history to an external file."""
        filename = filedialog.asksaveasfilename(
            title=self.tr("_s_file_import"),
            defaultextension=".json",
            filetypes=FILETYPES
        )
        if filename:
            self.store.save(filename)

    def _clear(self,message,callback):
        """Execute a clear operation after user confirmation.

        If confirmed, the supplied callback is executed, the list is refreshed
        and the updated history is saved.

        Returns:
            True if the operation was confirmed and executed, False otherwise.
        """
        if not messagebox.askyesno(APP_NAME, self.tr(message)):
            return False
        callback()
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

    def save_now(self):
        """Save clipboard history and user preferences to disk."""
        try:
            self.store.save(
                self.save_path,
                settings={
                    "language": self.language,
                    "corner": self.corner,
                    "show_timestamp": self.show_timestamp,
                    "hide_after_copy": self.hide_after_copy
                }
            )
        except Exception as exc:
            print(f"Save failed: {exc}")

    # ----- WINDOW CONTROL -----

    def hide_to_tray(self):
        """Oculta la ventana y deja la app viva en bandeja."""
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

        The pin and timestamp columns keep a fixed width. The preview column
        expands or shrinks to occupy the remaining horizontal space.
        """
        self.update_idletasks()

        container_w = self.tree.master.winfo_width()
        if container_w <= 1:
            return

        vsb_w = self.vsb.winfo_width() if hasattr(self, "vsb") else 0

        pin_w = int(self.tree.column("pin", "width"))
        ts_visible = "ts" in self.tree["displaycolumns"]
        ts_w = int(self.tree.column("ts", "width")) if ts_visible else 0

        # Small safety margin to avoid clipping and geometry rounding issues.
        margin = 12

        new_w = max(PREVIEW_COL_MIN_W, container_w - vsb_w - pin_w - ts_w - margin)
        self.tree.column("preview", width=new_w)

    def apply_treeview_columns(self):
        """Apply visible Treeview columns and recalculate window layout.

        Toggling the timestamp column resets the window width to the minimum
        required by the current column layout. Users can resize manually afterwards.
        """
        if self.show_timestamp:
            self.tree["displaycolumns"] = ("pin", "ts", "preview")
        else:
            self.tree["displaycolumns"] = ("pin", "preview")
        self.after(0, self._fit_preview_column)
        self.after(0, self.resize_to_columns)
        self.after(0, self.move_to_corner)

    def resize_to_columns(self):
        """Resize the window to the minimum width required by visible columns.

        Toggling the timestamp column gives ClipStack control of the window width.
        Users can manually resize the window again afterwards.
        """
        self.update_idletasks()

        fixed_w = PIN_COL_W
        if self.show_timestamp:
            fixed_w += TS_COL_W

        # Approximate space for scrollbar, borders and internal padding.
        chrome_w = 40

        new_w = fixed_w + PREVIEW_MIN_W + chrome_w
        cur_h = self.winfo_height()

        self.geometry(f"{new_w}x{cur_h}")
        self.minsize(new_w, self.winfo_reqheight())

    def _disable_treeview_resize(self, event):
        """Prevent manual resizing of Treeview columns."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "separator":
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
        def _action(icon, item):
            self.after(0, lambda: fn(*args, **kwargs))
        return _action

    def _checked_equals(self, getter, value):
        """Return a pystray checked callback comparing `getter()` with `value`."""
        return lambda item: getter() == value

    def _checked_bool(self, getter):
        """Return a pystray checked callback for a boolean getter."""
        return lambda item: bool(getter())

    def _load_tray_icon_from_b64(self, b64: str, size: int = 64) -> Image.Image:
        """Load a tray icon image from a base64-encoded PNG."""
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        if size:
            img = img.resize((size, size), Image.LANCZOS)
        return img

    def setup_tray(self):
        """Create and start the system tray icon in a daemon thread."""
        if self.tray_icon is not None:
            return

        image = self._load_tray_icon_from_b64(TRAY_ICON_PNG_B64, size=64)
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

    # ----- QUIT THE APP -----

    def quit_app(self):
        """Perform a clean application shutdown.

        The current state is saved, the tray icon is stopped if present and the
        main Tk window is destroyed.
        """
        self.save_now()

        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
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

