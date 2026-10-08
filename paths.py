"""Where the app keeps its files.

From source: settings.json (and the optional appnames_local.json) next to
the code and data/ relative to the working directory (start_screentime.bat
switches to the project folder).

As a packaged exe (PyInstaller): all under %APPDATA%\\ScreenTime, since the
exe may sit in a read-only folder or, for the one-file build, unpack into a
temporary one on every start.
"""

import os
import sys

FROZEN = getattr(sys, "frozen", False)

_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """Folder holding settings.json; created if missing."""
    if not FROZEN:
        return _SOURCE_DIR
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "ScreenTime")
    os.makedirs(path, exist_ok=True)
    return path


def settings_file():
    return os.path.join(app_dir(), "settings.json")


def local_appnames_file():
    """Optional, git-ignored file with the user's own app names (see appnames.py)."""
    return os.path.join(app_dir(), "appnames_local.json")


def data_dir():
    """Folder of the daily records; the tracker creates it if missing."""
    if not FROZEN:
        return "data"
    return os.path.join(app_dir(), "data")


def resource(relative):
    """Path of a file shipped with the app, such as the window icon."""
    base = getattr(sys, "_MEIPASS", _SOURCE_DIR) if FROZEN else _SOURCE_DIR
    return os.path.join(base, relative)
