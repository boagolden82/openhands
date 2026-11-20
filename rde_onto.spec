# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 Windows 可执行程序。

用法：
    pyinstaller --noconfirm --clean rde_onto.spec
产物：
    dist/RDE-Onto.exe
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()

datas = [
    (str(ROOT / "ontology" / "ontology.json"), "ontology"),
    (str(ROOT / "app" / "web"), "app/web"),
]
if (ROOT / "docs").exists():
    datas.append((str(ROOT / "docs"), "docs"))
if (ROOT / "README.md").exists():
    datas.append((str(ROOT / "README.md"), "."))

hiddenimports = collect_submodules("app")

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RDE-Onto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
