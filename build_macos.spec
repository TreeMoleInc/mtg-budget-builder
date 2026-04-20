# -*- mode: python ; coding: utf-8 -*-
# macOS build spec — produces a single .app bundle
# Run from project root: .venv/bin/pyinstaller build_macos.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ctk_datas  = collect_data_files("customtkinter")
ctk_hidden = collect_submodules("customtkinter")

_icns = "assets/icon.icns"
_icon_datas = [(_icns, ".")] if os.path.exists(_icns) else []
_icon_file  = _icns if os.path.exists(_icns) else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=_icon_datas + ctk_datas,
    hiddenimports=ctk_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MTG Budget Builder (v1.0.1 macOS)",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MTG Budget Builder (v1.0.1 macOS)",
)

app = BUNDLE(
    coll,
    name="MTG Budget Builder (v1.0.1 macOS).app",
    icon=_icon_file,
    bundle_identifier="com.treemoleinc.mtgbudgetbuilder",
    info_plist={
        "CFBundleShortVersionString": "1.0.1",
        "CFBundleVersion": "1.0.1",
        "NSHighResolutionCapable": True,
    },
)
