"""User preferences. Stored as settings.json in the project root
(under %APPDATA%\\ScreenTime for the packaged exe; see paths.py).

Kept outside the data folder; everything under data/ counts as a daily record.
"""

import json
import os

import paths

SETTINGS_FILE = paths.settings_file()

DEFAULTS = {
    "theme": "dark",
    "language": "en",
    "period": "week",
    "idle_enabled": True,
    "idle_timeout": 60,
    "hide_system": True,
}


def load_settings():
    values = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        values[key] = stored[key]
        except Exception:
            pass
    return values


def save_settings(values):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({k: values.get(k, DEFAULTS[k]) for k in DEFAULTS},
                      f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
