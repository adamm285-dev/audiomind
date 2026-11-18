"""
Lightweight stdlib-only MCP (Model Context Protocol) stdio server for AudioMind.
Exposes audiomind_status, audiomind_list_voices, and audiomind_speak without
altering the standalone desktop tray app lifecycle.
"""
import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

VOICES = [
    {"id": "af_heart", "label": "Heart (Warm & Natural, Default)"},
    {"id": "af_bella", "label": "Bella (Friendly & Melodic)"},
    {"id": "af_nicole", "label": "Nicole (Relaxed & Casual)"},
    {"id": "af_sky", "label": "Sky (Breezy & Upbeat)"},
    {"id": "af_sarah", "label": "Sarah (Crisp & Professional)"},
    {"id": "am_adam", "label": "Adam (Natural & Conversational)"},
    {"id": "am_michael", "label": "Michael (Deep & Warm)"},
    {"id": "am_echo", "label": "Echo (Smooth & Mellow)"},
    {"id": "am_onyx", "label": "Onyx (Resonant & Baritone)"},
    {"id": "bf_emma", "label": "Emma (British Warm & Expressive)"},
    {"id": "bf_isabella", "label": "Isabella (British Eloquent)"},
    {"id": "bm_george", "label": "George (British Classic BBC)"},
    {"id": "bm_fable", "label": "Fable (British Narrative)"},
]

TOOLS = [
    {
        "name": "audiomind_status",
        "description": "Check whether the AudioMind desktop tray app is running and report the active platform.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "audiomind_list_voices",
        "description": "List available AudioMind Kokoro neural TTS voices.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "audiomind_speak",
        "description": "Speak a short notification aloud using AudioMind's TTS engine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Short natural-language text to speak aloud."},
                "voice": {"type": "string", "description": "Optional voice ID (e.g. af_heart, am_adam)."},
            },
            "required": ["text"],
        },
    },
]


def _is_tray_running() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "AudioMind_TrayApp_Mutex")
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        import fcntl
        with open("/tmp/audiomind_tray.lock", "a+") as fp:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
                return False
            except BlockingIOError:
                return True
    except Exception:
        return False


def handle_tool_call(name: str, args: dict) -> dict:
    if name == "audiomind_status":
        payload = {"platform": sys.platform, "tray_running": _is_tray_running()}
        return {"content": [{"type": "text", "text": json.dumps(payload)}]}
    if name == "audiomind_list_voices":
        return {"content": [{"type": "text", "text": json.dumps(VOICES)}]}
    if name == "audiomind_speak":
        text = str((args or {}).get("text", "")).strip()
        if not text:
            return {"content": [{"type": "text", "text": "No text provided."}], "isError": True}
        voice = (args or {}).get("voice")
        from desktop.audio.tts import speak
        speak(text, voice=voice)
        return {"content": [{"type": "text", "text": f"Spoke {len(text.split())} words."}]}
    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "audiomind", "version": "1.0.0"},
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = handle_tool_call(params.get("name", ""), params.get("arguments") or {})
        else:
            result = {}

        if req_id is not None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
