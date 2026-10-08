"""Turns process names into readable app names.

Display layer only: keys on disk stay as they are, no data is
converted. So changing the mapping never corrupts past data.
"""

import json
import os
import re

from paths import local_appnames_file

DISPLAY_NAMES = {
    # Browsers
    "edge": "Microsoft Edge",
    "msedge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "firefox": "Mozilla Firefox",
    "brave": "Brave",
    "opera": "Opera",
    # Windows shell
    "explorer": "File Explorer",
    "windows gezgini": "File Explorer",
    "shellexperiencehost": "Windows Shell",
    "startmenuexperiencehost": "Start Menu",
    "searchapp": "Windows Search",
    "searchhost": "Windows Search",
    "applicationframehost": "Windows App",
    "textinputhost": "Text Input",
    "lockapp": "Lock Screen",
    "logonui": "Lock Screen",
    "taskmgr": "Task Manager",
    "systemsettings": "Settings",
    "systemsettingsadminflows": "Settings",
    "credentialuibroker": "Windows Security",
    "dwm": "Desktop Window Manager",
    # Development
    "code": "VS Code",
    "devenv": "Visual Studio",
    "pycharm64": "PyCharm",
    "idea64": "IntelliJ IDEA",
    "unrealeditor": "Unreal Engine",
    "unity": "Unity",
    "blender": "Blender",
    "python": "Python",
    "pythonw": "Python",
    "cmd": "Command Prompt",
    "powershell": "PowerShell",
    "windowsterminal": "Windows Terminal",
    "wt": "Windows Terminal",
    "notepad": "Notepad",
    "notepad++": "Notepad++",
    "livecodingconsole": "Live Coding Console",
    "crashreportclienteditor": "Crash Reporter",
    # Game launchers
    "steam": "Steam",
    "steamwebhelper": "Steam",
    "epicgameslauncher": "Epic Games Launcher",
    "epicgamesupdater": "Epic Games Updater",
    "battle.net": "Battle.net",
    # Tools
    "winrar": "WinRAR",
    "7zfm": "7-Zip",
    "mspaint": "Paint",
    "telegram": "Telegram",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "spotify": "Spotify",
    "vlc": "VLC",
    "obs64": "OBS Studio",
    "nvidia app": "NVIDIA App",
    "nvcontainer": "NVIDIA Container",
    "setup": "Installer",
    "setup.tmp": "Installer",
    "photos": "Photos",
    "javaw": "Java",
    "msdt": "Windows Troubleshooter",
}

# Recorded, but hidden from the list by default
SYSTEM_PROCESSES = {
    "shellexperiencehost", "startmenuexperiencehost", "searchapp", "searchhost",
    "applicationframehost", "textinputhost", "lockapp", "logonui",
    "credentialuibroker", "dwm", "systemsettingsadminflows", "sihost",
    "runtimebroker", "widgets", "widgetboard", "gamebar", "gamebarftserver",
}

# Abbreviations that should be written in upper case
_ACRONYMS = {"gta", "ac", "re", "ui", "id", "vlc", "obs", "pc", "hd", "3d", "2d",
             "cpu", "gpu", "api", "sdk", "ide", "vpn", "usb", "pdf"}

# Engine suffixes that recur in game binaries
_NOISE = re.compile(
    r"[-_\s]*(win64|win32|x64|x86)?[-_\s]*(shipping|debug|release|test|final)$",
    re.IGNORECASE,
)


def _prettify(raw):
    """Produces a reasonable display form for names not in the mapping."""
    name = _NOISE.sub("", raw.strip())
    name = re.sub(r"[_]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    if not name:
        return raw

    words = []
    for word in name.split(" "):
        stripped = word.strip("-")
        if stripped.lower() in _ACRONYMS:
            words.append(stripped.upper())
        elif stripped.isupper() and len(stripped) <= 4:
            words.append(stripped)
        else:
            words.append(stripped[:1].upper() + stripped[1:])
    return " ".join(w for w in words if w)


# Categories: read time as what you were doing, not app by app
_CATEGORY_MEMBERS = {
    "browser": {"edge", "msedge", "chrome", "firefox", "brave", "opera"},
    "dev": {"code", "devenv", "pycharm64", "idea64", "unrealeditor", "unity",
            "blender", "python", "pythonw", "cmd", "powershell",
            "windowsterminal", "wt", "notepad", "notepad++",
            "livecodingconsole", "crashreportclienteditor", "javaw", "setup",
            "setup.tmp"},
    "game": {"steam", "steamwebhelper", "epicgameslauncher",
             "epicgamesupdater", "battle.net"},
    "media": {"spotify", "vlc", "obs64", "photos", "mspaint", "telegram",
              "discord", "whatsapp"},
    "tool": {"explorer", "windows gezgini", "winrar", "7zfm", "taskmgr",
             "msdt", "nvidia app", "nvcontainer", "systemsettings"},
}


def _load_local():
    """Merges the user's own names from appnames_local.json, if present.

    The file is git-ignored, so personal apps stay out of the repository.
    Format: {"names": {key: name}, "categories": {category: [key, ...]}};
    both sections are optional and local entries win over built-in ones.
    """
    path = local_appnames_file()
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        names = data.get("names") or {}
        categories = data.get("categories") or {}
        if not isinstance(names, dict) or not isinstance(categories, dict):
            raise ValueError("unexpected structure")
    except (OSError, ValueError, AttributeError) as e:
        print(f"appnames_local.json ignored: {e}")
        return

    for key, name in names.items():
        if isinstance(key, str) and isinstance(name, str):
            DISPLAY_NAMES[key.strip().lower()] = name
    for category, keys in categories.items():
        if category not in _CATEGORY_MEMBERS or not isinstance(keys, list):
            continue
        for key in keys:
            if not isinstance(key, str):
                continue
            key = key.strip().lower()
            for members in _CATEGORY_MEMBERS.values():
                members.discard(key)
            _CATEGORY_MEMBERS[category].add(key)


_load_local()

_CATEGORY_OF = {}
for _name, _members in _CATEGORY_MEMBERS.items():
    for _member in _members:
        _CATEGORY_OF[_member] = _name

# Display order; colors match theme.PALETTES["series"]
CATEGORY_ORDER = ["browser", "dev", "game", "media", "tool", "system", "other"]


def category_of(raw):
    key = (raw or "").strip().lower()
    if key in SYSTEM_PROCESSES:
        return "system"
    return _CATEGORY_OF.get(key, "other")


def display_name(raw):
    if not raw:
        return ""
    return DISPLAY_NAMES.get(raw.strip().lower(), _prettify(raw))


def is_system(raw):
    return (raw or "").strip().lower() in SYSTEM_PROCESSES
