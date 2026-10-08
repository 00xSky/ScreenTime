# PyInstaller build for the Windows exe.
#
#   pyinstaller ScreenTime.spec              -> dist\ScreenTime.exe (one file)
#   pyinstaller ScreenTime.spec -- --onedir  -> dist\ScreenTime\ (folder)
#
# The packaged app keeps settings.json and data\ under %APPDATA%\ScreenTime
# (see paths.py).

import argparse

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo)

parser = argparse.ArgumentParser()
parser.add_argument("--onedir", action="store_true")
options = parser.parse_args()

VERSION = (1, 0, 0, 0)
VERSION_TEXT = ".".join(str(n) for n in VERSION)
ICON = "assets\\ScreenTime.ico"

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION, prodvers=VERSION),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "00xSky"),
            StringStruct("FileDescription", "Screen Time"),
            StringStruct("FileVersion", VERSION_TEXT),
            StringStruct("InternalName", "ScreenTime"),
            StringStruct("LegalCopyright", "Copyright (c) 2026 00xSky"),
            StringStruct("OriginalFilename", "ScreenTime.exe"),
            StringStruct("ProductName", "Screen Time"),
            StringStruct("ProductVersion", VERSION_TEXT),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    ["main.py"],
    datas=[(ICON, "assets")],
    # Pillow imports numpy only if it is installed; the app never uses it
    excludes=["numpy"],
)
pyz = PYZ(a.pure)

exe_options = dict(
    name="ScreenTime",
    icon=ICON,
    version=version_info,
    console=False,
    upx=False,
)

if options.onedir:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, name="ScreenTime", upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, **exe_options)
