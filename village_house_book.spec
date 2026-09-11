# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
lo = Path(os.environ.get("HOUSEBOOK_BUNDLED_LO", root / "runtime" / "libreoffice"))
datas = [(str(root / "resources"), "resources")]
datas += collect_data_files("docxcompose", includes=["templates/*.xml"])
lo_tree = Tree(str(lo), prefix="runtime/libreoffice")

a = Analysis(
    [str(root / "run_app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["pillow_heif", "fitz", "PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

def keep_runtime_data(entry):
    destination = entry[0].replace("\\", "/")
    if destination.startswith("PySide6/translations/"):
        return destination.endswith("_zh_CN.qm")
    if destination.startswith("PySide6/plugins/platforms/"):
        return destination.endswith(("qwindows.dll", "qoffscreen.dll"))
    if destination.startswith("PySide6/plugins/imageformats/"):
        return destination.endswith(("qjpeg.dll", "qtiff.dll", "qwebp.dll", "qgif.dll", "qico.dll"))
    if destination.startswith("PySide6/plugins/generic/"):
        return False
    return True

a.datas = [entry for entry in a.datas if keep_runtime_data(entry)]
blocked_runtime_dlls = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    entry
    for entry in a.binaries
    if Path(entry[0]).name.lower() not in blocked_runtime_dlls
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="村务材料管理",
    icon=str(root / "resources" / "icons" / "villagedocs-icon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    lo_tree,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VillageDocs",
)
