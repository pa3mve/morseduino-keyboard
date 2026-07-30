# PyInstaller spec for Serial → Keyboard
# Run:  python build.py
#   or: pyinstaller serial_keyboard.spec --clean

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

# pynput ships platform backends as separate modules; PyInstaller
# won't detect them via static analysis, so list them explicitly.
hidden = [
    "pynput.keyboard._win32",
    "pynput.keyboard._darwin",
    "pynput.keyboard._xorg",
    "pynput.keyboard._uinput",
    "pynput.mouse._win32",
    "pynput.mouse._darwin",
    "pynput.mouse._xorg",
    "pynput.mouse._uinput",
    # pyserial platform backends
    "serial.serialutil",
    "serial.serialposix",
    "serial.serialwin32",
    "serial.tools",
    "serial.tools.list_ports",
    "serial.tools.list_ports_common",
    "serial.tools.list_ports_posix",
    "serial.tools.list_ports_windows",
    "serial.tools.list_ports_osx",
    # evdev (Linux/Wayland)
    "evdev",
    "evdev.ecodes",
    "evdev.uinput",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PIL", "email", "html", "http",
               "unittest", "xmlrpc"],
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
    name="SerialKeyboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compress if UPX is on PATH (optional, shrinks binary)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
