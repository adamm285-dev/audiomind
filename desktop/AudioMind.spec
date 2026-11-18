# -*- mode: python ; coding: utf-8 -*-
# Desktop-only PyInstaller spec for AudioMind (excludes android/ and relay/)
import os
import sys

block_cipher = None
root_dir = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(root_dir, "desktop", "resources"), os.path.join("desktop", "resources")),
]

a = Analysis(
    [os.path.join(root_dir, "desktop", "app.py")],
    pathex=[root_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pystray",
        "PIL._tkinter_finder",
        "kokoro_onnx",
        "edge_tts",
        "sounddevice",
        "openwakeword",
        "onnxruntime",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["android", "relay"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AudioMind",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(root_dir, "desktop", "resources", "anti_voice_assistant.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AudioMind",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AudioMind.app",
        icon=None,
        bundle_identifier="com.audiomind.desktop",
        info_plist={"LSUIElement": True, "NSMicrophoneUsageDescription": "AudioMind listens for 'Hey Anti' voice commands."},
    )
