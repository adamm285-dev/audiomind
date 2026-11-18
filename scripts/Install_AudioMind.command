#!/bin/bash
# 1-Click macOS Desktop Installer for AudioMind (Desktop only)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR" || exit 1

echo "=========================================="
echo "    AudioMind Desktop Installer (macOS)   "
echo "=========================================="

if [ ! -x "$ROOT_DIR/.venv_voice/bin/python3" ]; then
    echo "[*] Creating Python virtual environment..."
    python3 -m venv "$ROOT_DIR/.venv_voice" || { echo "[!] python3 not found."; exit 1; }
fi

echo "[*] Installing desktop dependencies..."
"$ROOT_DIR/.venv_voice/bin/python3" -m pip install --upgrade pip >/dev/null
"$ROOT_DIR/.venv_voice/bin/python3" -m pip install -r "$ROOT_DIR/desktop/requirements.txt" || exit 1

echo "[*] Creating Desktop launcher..."
APP_DIR="$HOME/Desktop/AudioMind.app"
mkdir -p "$APP_DIR/Contents/MacOS"
cat > "$APP_DIR/Contents/MacOS/AudioMind" <<EOF
#!/bin/bash
cd "$ROOT_DIR" || exit 1
exec "$ROOT_DIR/.venv_voice/bin/python3" "$ROOT_DIR/desktop/app.py"
EOF
chmod +x "$APP_DIR/Contents/MacOS/AudioMind"

cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>AudioMind</string>
  <key>CFBundleExecutable</key><string>AudioMind</string>
  <key>CFBundleIdentifier</key><string>com.audiomind.desktop</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF

echo "[+] AudioMind.app created on your Desktop! Launching AudioMind..."
open "$APP_DIR"
