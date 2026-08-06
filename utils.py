"""Lightweight persistence helpers for Tri-angle.

This module provides a thin JSON-backed in-memory cache with a
debounced write-to-disk strategy to avoid frequent file I/O.
"""

import json
import os
import threading

DATA_FILE = "triangle_data.json"

# In-memory cache to avoid repeated file reads/writes
_DATA_CACHE = None
_CACHE_LOCK = threading.Lock()
_SAVE_TIMER = None
_SAVE_DELAY = 1.0  # seconds to debounce frequent saves


def _ensure_loaded():
    """Load `DATA_FILE` into the in-memory cache if not already loaded.

    This is intentionally defensive: if the file is missing or invalid
    JSON is encountered, a minimal default structure is populated.
    """
    global _DATA_CACHE
    if _DATA_CACHE is None:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    _DATA_CACHE = json.load(f)
            except Exception:
                _DATA_CACHE = {"study_groups": {}, "tasks": {}, "stats": {}}
        else:
            _DATA_CACHE = {"study_groups": {}, "tasks": {}, "stats": {}}


def load_data():
    """Return the in-memory data cache, loading from disk once if needed."""
    with _CACHE_LOCK:
        _ensure_loaded()
        return _DATA_CACHE


def _write_to_disk():
    """Write the current cache to disk atomically."""
    global _SAVE_TIMER
    with _CACHE_LOCK:
        data = _DATA_CACHE
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    finally:
        _SAVE_TIMER = None


def save_data(data):
    """Update the in-memory cache and schedule a debounced write to disk."""
    global _DATA_CACHE, _SAVE_TIMER
    with _CACHE_LOCK:
        _DATA_CACHE = data
        if _SAVE_TIMER is not None:
            _SAVE_TIMER.cancel()
        _SAVE_TIMER = threading.Timer(_SAVE_DELAY, _write_to_disk)
        _SAVE_TIMER.daemon = True
        _SAVE_TIMER.start()


def flush():
    """Force any pending writes to disk immediately."""
    global _SAVE_TIMER
    if _SAVE_TIMER:
        _SAVE_TIMER.cancel()
        _write_to_disk()
