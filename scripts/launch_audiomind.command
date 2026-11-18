#!/bin/bash
# macOS double-clickable launcher for AudioMind
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR" || exit 1

if [ -x "$ROOT_DIR/.venv_voice/bin/python3" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv_voice/bin/python3"
elif [ -x "$ROOT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" "$ROOT_DIR/desktop/app.py"
