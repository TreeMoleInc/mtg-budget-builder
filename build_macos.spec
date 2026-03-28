# -*- mode: python ; coding: utf-8 -*-
# macOS build spec — produces a single .app bundle
# Run from project root: .venv/bin/pyinstaller build_macos.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ctk_datas  = collect_data_files("customtkinter")
ctk_hidden = collect_submodules("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/icon.icns", "."),
    ] + ctk_datas,
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
    name="MTG Budget Builder (v1.0.0 macOS)",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MTG Budget Builder (v1.0.0 macOS)",
)

app = BUNDLE(
    coll,
    name="MTG Budget Builder (v1.0.0 macOS).app",
    icon="assets/icon.icns",
    bundle_identifier="com.treemoleinc.mtgbudgetbuilder",
    info_plist={
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
