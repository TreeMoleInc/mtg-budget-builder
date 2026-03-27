# -*- mode: python ; coding: utf-8 -*-
# Windows build spec — produces a single .exe
# Run from project root: .venv\Scripts\pyinstaller build_windows.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# customtkinter ships theme JSON and image assets that must be bundled explicitly
ctk_datas   = collect_data_files("customtkinter")
ctk_hidden  = collect_submodules("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("icon.ico", "."),
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
    a.binaries,
    a.datas,
    [],
    name="MTG Budget Builder (v1.0.0)",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)
