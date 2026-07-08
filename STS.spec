# -*- mode: python ; coding: utf-8 -*-
import base64
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()
ICON_B64 = ROOT / "src" / "ui" / "assets" / "sts_icon.ico.b64"
GENERATED_DIR = ROOT / "build" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
ICON = GENERATED_DIR / "sts_icon.ico"
ICON.write_bytes(base64.b64decode("".join(ICON_B64.read_text(encoding="ascii").split()), validate=True))

block_cipher = None

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "ui" / "assets"), "src/ui/assets"),
    ],
    hiddenimports=collect_submodules("openpyxl"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="STS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)
