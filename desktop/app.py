"""
Anti Desktop System Tray Application & Hands-Free Voice Assistant.
Features:
- Windows Taskbar Active System Tray Icon with real-time status indication.
- Floating translucent Desktop Waveform HUD that animates live voice audio.
- WASAPI Acoustic Echo Cancellation (AEC) dual-stream capture.
- Custom 'Hey Anti' ONNX wake-word detection (calibrated for 'ant-tea').
- AST Command Firewall with 3-Tier security isolation.
- Antigravity CLI execution dispatcher.
"""
import os
import sys
from typing import Optional, List, Dict, Tuple, Callable

# Ensure repository root is in sys.path for standalone launching
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import ctypes

def attach_to_default_desktop():
    """Ensure the calling process and thread are attached to the interactive 'WinSta0\\Default' desktop."""
    try:
        u = ctypes.windll.user32
        WINSTA_ALL = 0x037F
        hwinsta = u.OpenWindowStationW("WinSta0", False, WINSTA_ALL)
        if hwinsta:
            u.SetProcessWindowStation(hwinsta)
        DESKTOP_ALL = 0x01FF
        h_desk = u.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if h_desk:
            u.SetThreadDesktop(h_desk)
    except Exception:
        pass

# Ensure process is attached to interactive desktop before any window/tray initialization
attach_to_default_desktop()

# Real-time file & console logger with automatic self-pruning
LOG_FILE = os.path.join(os.path.dirname(__file__), "anti_tray.log")

class DualLogger:
    def __init__(self, filename, stream, max_bytes=250_000, keep_lines=300):
        self.filename = filename
        self.stream = stream
        self.max_bytes = max_bytes
        self.keep_lines = keep_lines
        self.write_count = 0
        self._prune_if_needed()
        try:
            self.file = open(filename, "a", encoding="utf-8", buffering=1)
        except Exception:
            self.file = None

    def _prune_if_needed(self):
        try:
            if os.path.exists(self.filename) and os.path.getsize(self.filename) > self.max_bytes:
                with open(self.filename, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                if len(lines) > self.keep_lines:
                    with open(self.filename, "w", encoding="utf-8") as f:
                        f.writelines(lines[-self.keep_lines:])
        except Exception:
            pass

    def write(self, data):
        if self.stream:
            try:
                self.stream.write(data)
                self.stream.flush()
            except Exception:
                pass
        if self.file:
            try:
                self.file.write(data)
                self.file.flush()
                self.write_count += 1
                if self.write_count >= 100:
                    self.write_count = 0
                    if os.path.exists(self.filename) and os.path.getsize(self.filename) > self.max_bytes:
                        self.file.close()
                        self._prune_if_needed()
                        self.file = open(self.filename, "a", encoding="utf-8", buffering=1)
            except Exception:
                pass

    def flush(self):
        if self.stream:
            try:
                self.stream.flush()
            except Exception:
                pass
        if self.file:
            try:
                self.file.flush()
            except Exception:
                pass

sys.stdout = DualLogger(LOG_FILE, sys.stdout)
sys.stderr = DualLogger(LOG_FILE, sys.stderr)

import time
import threading
import subprocess
import ctypes
from ctypes import wintypes
from collections import deque
from typing import Tuple, Optional
import traceback
import numpy as np
try:
    import pyperclip
    def set_clipboard_text(text: str):
        pyperclip.copy(text)
except ImportError:
    try:
        import win32clipboard
        def set_clipboard_text(text: str):
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
    except Exception:
        def set_clipboard_text(text: str):
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
from PIL import Image, ImageDraw, ImageFont
try:
    import pystray
    from pystray import MenuItem as item
except ImportError:
    pystray = None
    item = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None

# Core UI & Policy Modules
try:
    from desktop.firewall.policy import CommandFirewall, RiskTier
    from desktop.ui.hud import WaveformHud
except ImportError:
    from firewall.policy import CommandFirewall, RiskTier
    from ui.hud import WaveformHud

# Audio Hardware & Synthesis Modules
try:
    from desktop.audio.wasapi_stream import WasapiAecStream
    from desktop.audio.chime import play_chime, play_submit_chime
    from desktop.audio.tts import (
        speak, stop_speech, pause_speech, resume_speech, 
        toggle_pause, rewind_speech, fast_forward_speech,
        skip_to_next_chapter, repeat_last_chapter, get_chapter_info,
        is_speaking, is_paused, is_speech_active, get_speech_player
    )
    from desktop.audio.read_aloud import TranscriptWatcher
except ImportError:
    try:
        from audio.wasapi_stream import WasapiAecStream
        from audio.chime import play_chime, play_submit_chime
        from audio.tts import (
            speak, stop_speech, pause_speech, resume_speech, 
            toggle_pause, rewind_speech, fast_forward_speech,
            skip_to_next_chapter, repeat_last_chapter, get_chapter_info,
            is_speaking, is_paused, is_speech_active, get_speech_player
        )
        from audio.read_aloud import TranscriptWatcher
    except ImportError:
        WasapiAecStream = None
        play_chime = None
        play_submit_chime = None
        speak = None
        stop_speech = None
        pause_speech = None
        resume_speech = None
        toggle_pause = None
        rewind_speech = None
        fast_forward_speech = None
        skip_to_next_chapter = None
        repeat_last_chapter = None
        get_chapter_info = lambda: (1, 1, "Overview")
        is_speaking = None
        is_paused = None
        is_speech_active = None
        get_speech_player = None
        TranscriptWatcher = None

try:
    import openwakeword
    from openwakeword.model import Model
except ImportError:
    openwakeword = None
    Model = None

def attach_to_default_desktop():
    """Ensure the calling process and thread are attached to the interactive 'WinSta0\\Default' desktop."""
    try:
        u = ctypes.windll.user32
        WINSTA_ALL = 0x037F
        hwinsta = u.OpenWindowStationW("WinSta0", False, WINSTA_ALL)
        if hwinsta:
            u.SetProcessWindowStation(hwinsta)
        DESKTOP_ALL = 0x01FF
        h_desk = u.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if h_desk:
            u.SetThreadDesktop(h_desk)
    except Exception:
        pass

def enable_win32_dark_mode():
    """
    Enables native Windows 10/11 Dark Mode for Win32 menus and windows.
    Configures undocumented uxtheme ordinals (SetPreferredAppMode, AllowDarkModeForWindow, FlushMenuThemes)
    and monkey-patches pystray._win32 so that the system tray context menu renders with
    the modern Windows 10/11 dark theme instead of the legacy white GDI theme.
    """
    try:
        # 0. Set Per-Monitor V2 DPI awareness for crystal-clear vector Segoe UI rendering
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass

        uxtheme = ctypes.windll.uxtheme
        dwmapi = ctypes.windll.dwmapi

        # 1. Ordinal 135: SetPreferredAppMode (2 = ForceDark, 1 = AllowDark)
        try:
            SetPreferredAppMode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))
            SetPreferredAppMode(2)
        except Exception:
            pass

        # 2. Ordinal 133: AllowDarkModeForWindow
        try:
            AllowDarkModeForWindow = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_bool)((133, uxtheme))
        except Exception:
            AllowDarkModeForWindow = None

        # 3. Ordinal 136: FlushMenuThemes
        try:
            FlushMenuThemes = ctypes.WINFUNCTYPE(None)((136, uxtheme))
            FlushMenuThemes()
        except Exception:
            FlushMenuThemes = None

        # 4. SetWindowTheme
        try:
            SetWindowTheme = uxtheme.SetWindowTheme
            SetWindowTheme.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
            SetWindowTheme.restype = ctypes.c_long
        except Exception:
            SetWindowTheme = None

        # 5. DwmSetWindowAttribute (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)
        try:
            DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD]
            DwmSetWindowAttribute.restype = ctypes.c_long
        except Exception:
            DwmSetWindowAttribute = None

        # Monkey-patch pystray._win32 to apply dark mode to tray and menu windows
        import pystray._win32 as pwin32

        orig_create_window = pwin32.Icon._create_window

        def dark_create_window(self, atom):
            hwnd = orig_create_window(self, atom)
            try:
                if AllowDarkModeForWindow:
                    AllowDarkModeForWindow(hwnd, True)
                if SetWindowTheme:
                    SetWindowTheme(hwnd, "DarkMode_Explorer", None)
                if DwmSetWindowAttribute:
                    dark_val = ctypes.c_int(1)
                    DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
                if FlushMenuThemes:
                    FlushMenuThemes()
            except Exception:
                pass
            return hwnd

        pwin32.Icon._create_window = dark_create_window

        orig_on_notify = pwin32.Icon._on_notify

        def dark_on_notify(self, wparam, lparam):
            if lparam == pwin32.win32.WM_RBUTTONUP:
                try:
                    if FlushMenuThemes:
                        FlushMenuThemes()
                    # Recreate menu so dynamic checked states and labels update immediately
                    if self.menu:
                        if self._menu_handle:
                            hmenu, callbacks = self._menu_handle
                            pwin32.win32.DestroyMenu(hmenu)
                        callbacks = []
                        self._menu_handle = (self._create_menu(self.menu, callbacks), callbacks)
                except Exception:
                    pass
            return orig_on_notify(self, wparam, lparam)

        pwin32.Icon._on_notify = dark_on_notify
        print("[*] Win32 Dark Mode enabled for System Tray context menu.")
    except Exception as e:
        print(f"[!] Win32 Dark Mode initialization failed: {e}")

# Enable Win32 Dark Mode before any windows or menus are initialized
enable_win32_dark_mode()

import shutil

def resolve_agy_path() -> str:
    env_path = os.getenv("AGY_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    which_path = shutil.which("agy")
    if which_path:
        return which_path
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        default_win_path = os.path.join(local_app_data, "agy", "bin", "agy.exe")
        if os.path.exists(default_win_path):
            return default_win_path
    return "agy"

AGY_PATH = resolve_agy_path()
# Antigravity IDE binds Ctrl+L to antigravity.toggleChatFocus ("Open Chat with Agent"), which places
# the cursor in the agent chat input. It is on the terminal skip-shell list, so it works from the terminal too.
ANTIGRAVITY_IDE_EXE = "antigravity ide.exe"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "resources", "models", "hey_anti.onnx")

def create_tray_icon_image(state: str = "listening", pulse: float = 0.0) -> Image.Image:
    """Generate high-resolution 64x64 dynamic icon for Windows System Tray with animated pulsing."""
    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Normalize pulse oscillation (0.0 to 1.0)
    p = max(0.0, min(1.0, pulse))

    # Theme colors based on state
    if state == "listening":
        ring_color = (0, 229, 255, 255)   # Cyan
        glow_color = (0, 229, 255, 60)
        center_color = (13, 17, 23, 240)
        accent = (0, 230, 118, 255)       # Green dot
        glow_expand = 0
    elif state == "user_speaking":
        ring_color = (124, 77, 255, 255)  # Violet
        glow_alpha = int(70 + 110 * p)
        glow_color = (124, 77, 255, glow_alpha)
        center_color = (22, 27, 34, 255)
        accent = (213, 0, 249, 255)       # Neon Pink
        glow_expand = int(2.5 * p)
    elif state in ("processing", "thinking"):
        ring_color = (255, 214, 0, 255)   # Amber
        glow_alpha = int(60 + 120 * p)
        glow_color = (255, 214, 0, glow_alpha)
        center_color = (22, 27, 34, 255)
        accent = (255, 145, 0, 255)
        glow_expand = int(2.5 * p)
    elif state == "anti_speaking":
        ring_color = (0, 229, 255, 255)   # Cyan
        glow_alpha = int(70 + 120 * p)
        glow_color = (0, 229, 255, glow_alpha)
        center_color = (13, 17, 23, 255)
        # Pulse accent between cyan and bright white-cyan
        accent = (int(100 * p), int(229 + 26 * p), 255, 255)
        glow_expand = int(3.0 * p)
    else:  # muted
        ring_color = (110, 118, 129, 180) # Gray
        glow_color = (0, 0, 0, 0)
        center_color = (22, 27, 34, 200)
        accent = (248, 81, 73, 255)       # Red dot
        glow_expand = 0

    # Outer soft glow (pulses with expand & alpha)
    draw.ellipse([2 - glow_expand, 2 - glow_expand, 61 + glow_expand, 61 + glow_expand], fill=glow_color)
    # Background circle
    draw.ellipse([6, 6, 57, 57], fill=center_color, outline=ring_color, width=3)

    # Stylized "A" symbol with sound bars
    draw.line([(32, 16), (20, 46)], fill=ring_color, width=3)
    draw.line([(32, 16), (44, 46)], fill=ring_color, width=3)
    draw.line([(24, 36), (40, 36)], fill=accent, width=3)

    # Status accent badge on bottom right (pulses size slightly during active speech)
    badge_r = 6.0 + (1.5 * p if state in ("anti_speaking", "user_speaking", "processing", "thinking") else 0.0)
    bx, by = 50.0, 50.0
    draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], fill=accent, outline=(13, 17, 23, 255), width=2)
    return image

def get_desktop_session_token() -> str:
    """Generates an HMAC-SHA256 authenticated session token matching the Cloud Relay specification."""
    try:
        from dotenv import load_dotenv
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(root_dir, ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file, override=False)
    except Exception:
        pass

    import hmac
    import hashlib

    # Prefer RELAY_AUTH_SECRET or AUTH_SECRET_KEY. Never use hardcoded fallback secrets!
    secret = (os.getenv("RELAY_AUTH_SECRET") or os.getenv("AUTH_SECRET_KEY") or "").strip()
    if not secret:
        return ""

    tenant_id = os.getenv("RELAY_TENANT_ID", "default_tenant").strip() or "default_tenant"
    exp = int(time.time() + 86400 * 30)
    payload = f"{tenant_id}.{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{tenant_id}.{exp}.{sig}"

def is_secure_remote_url(url: str) -> bool:
    """
    Validates that the remote dispatch URL is HTTPS, or loopback HTTP (127.0.0.1 / localhost)
    for local development. Rejects hostname prefix spoofing such as http://localhost.attacker.com.
    """
    if not url or not url.strip():
        return False
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url.strip())
        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower()
        if scheme == "https" and hostname:
            return True
        if scheme == "http" and hostname in ("127.0.0.1", "localhost"):
            return True
        return False
    except Exception:
        return False

def is_foreground_window(hwnd) -> bool:
    """True only if hwnd (or a child/owned window) is the current foreground window. Gates every synthetic keystroke."""
    if not hwnd:
        return False
    try:
        hwnd_val = getattr(hwnd, "value", hwnd)
        if not hwnd_val:
            return False
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        fg = user32.GetForegroundWindow()
        fg_val = getattr(fg, "value", fg)
        if not fg_val:
            return False
        if int(fg_val) == int(hwnd_val):
            return True
        # Check root window ancestor (GA_ROOT = 2) in case a child widget/panel holds foreground
        root = user32.GetAncestor(fg_val, 2)
        root_val = getattr(root, "value", root)
        return bool(root_val) and int(root_val) == int(hwnd_val)
    except Exception:
        return False

def match_playback_intent(text: str, speech_active: bool) -> Optional[str]:
    """
    Pure matcher for speech playback voice intents.
    Returns the intent name ('PAUSE', 'RESUME', 'REWIND_5', 'NEXT_CHAPTER', 'REPEAT_CHAPTER', 'STOP')
    or None if no match or speech is not active.
    Note: 'forward' is strictly a tray button/action and excluded from voice commands.
    """
    if not speech_active or not text:
        return None

    clean = text.lower().strip().rstrip(".!?").strip()
    if not clean:
        return None

    PAUSE_COMMANDS = {
        "pause", "hold on", "pause speech", "pause reading", "wait a second", "wait a minute"
    }
    RESUME_COMMANDS = {
        "resume", "continue", "unpause", "keep reading", "play speech", "keep going"
    }
    REWIND_COMMANDS = {
        "rewind", "back up", "go back", "rewind 5", "back up 5", "go back 5",
        "back 5 seconds", "rewind 5 seconds", "rewind 10", "back up 10", "go back 10"
    }
    NEXT_CH_COMMANDS = {
        "next chapter", "skip chapter", "skip to next chapter", "next section", "skip section"
    }
    REPEAT_CH_COMMANDS = {
        "repeat chapter", "replay chapter", "previous chapter", "last chapter",
        "repeat last chapter", "restart chapter", "previous section"
    }
    STOP_COMMANDS = {
        "stop", "cancel", "stop talking", "shut up", "be quiet", "stop speech", "cancel reading"
    }

    if clean in PAUSE_COMMANDS:
        return "PAUSE"
    if clean in RESUME_COMMANDS:
        return "RESUME"
    if clean in REWIND_COMMANDS:
        return "REWIND_5"
    if clean in NEXT_CH_COMMANDS:
        return "NEXT_CHAPTER"
    if clean in REPEAT_CH_COMMANDS:
        return "REPEAT_CHAPTER"
    if clean in STOP_COMMANDS:
        return "STOP"

    return None

def is_process_elevated(pid: int) -> Optional[bool]:
    """
    Checks if a target process by PID is elevated using:
    OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) -> OpenProcessToken -> GetTokenInformation(TokenElevation).
    Returns:
      True: target process is elevated.
      False: target process is NOT elevated.
      None: query failed (access denied, invalid PID, or token query failed).
    """
    if not pid:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        TOKEN_QUERY = 0x0008
        TokenElevation = 20

        class TOKEN_ELEVATION(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h_proc:
            return None
        try:
            h_token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(h_proc, TOKEN_QUERY, ctypes.byref(h_token)):
                return None
            try:
                elev = TOKEN_ELEVATION()
                ret_len = wintypes.DWORD()
                if advapi32.GetTokenInformation(h_token, TokenElevation, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret_len)):
                    return bool(elev.TokenIsElevated)
                return None
            finally:
                kernel32.CloseHandle(h_token)
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        return None

def is_current_process_elevated() -> Optional[bool]:
    """Checks if the current calling process is elevated. Returns True, False, or None on error."""
    try:
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        TOKEN_QUERY = 0x0008
        TokenElevation = 20

        class TOKEN_ELEVATION(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        h_token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(h_token)):
            return None
        try:
            elev = TOKEN_ELEVATION()
            ret_len = wintypes.DWORD()
            if advapi32.GetTokenInformation(h_token, TokenElevation, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret_len)):
                return bool(elev.TokenIsElevated)
            return None
        finally:
            kernel32.CloseHandle(h_token)
    except Exception:
        return None

def check_elevation_mismatch(target_pid: int) -> tuple[bool, Optional[str]]:
    """
    Checks if target process elevation prevents synthetic keystrokes under Windows UIPI.
    Returns:
      (True, "Antigravity is running as administrator, so Anti can't type into it.") if target is elevated while current is not.
      (True, "Anti couldn't verify Antigravity's permissions, so nothing was typed.") if target elevation cannot be verified (fails closed).
      (False, None) if current process is elevated, or both processes are confirmed unelevated.
    """
    if not target_pid:
        return (True, "Anti couldn't verify Antigravity's permissions, so nothing was typed.")

    cur_elev = is_current_process_elevated()
    # If current process is elevated, UIPI does not restrict keystrokes
    if cur_elev is True:
        return (False, None)

    target_elev = is_process_elevated(target_pid)
    if target_elev is True:
        return (True, "Antigravity is running as administrator, so Anti can't type into it.")
    elif target_elev is None:
        # Fails closed on unknown/unverifiable permissions
        return (True, "Anti couldn't verify Antigravity's permissions, so nothing was typed.")
    return (False, None)

class AntiTrayApp:
    def __init__(self):
        attach_to_default_desktop()
        self.running = False
        self.muted = False
        self.hud_enabled = True
        self.auto_submit = True
        self.auto_read = True
        self.last_spoken_summary = ""
        self.last_injection_error = None
        self.wakeword_threshold = 0.35
        self.current_state = "listening"
        self._pulse_thread = None
        self._focused_pid = None
        self.last_app_hwnd = None

        # Remote Android / Assistant Dispatch Listener (disabled by default)
        configured_url = os.getenv("REMOTE_DISPATCH_API_URL", "").strip().rstrip("/")
        self.remote_api_url = configured_url if is_secure_remote_url(configured_url) else ""
        self.pending_remote_dispatch: Optional[dict] = None
        # Only enable if explicitly configured with a secure URL and an authentication secret
        token = get_desktop_session_token()
        self.remote_poll_enabled = bool(self.remote_api_url and token)
        self._speak_lock = threading.Lock()

        # Initialize HUD in background thread
        self.hud = WaveformHud()
        self.hud.on_click = self.toggle_speech_pause
        self.hud.start()

        # Security & STT
        self.firewall = CommandFirewall(workspace_root=os.path.abspath("."))
        self.recognizer = sr.Recognizer()

        # Wake-word model
        if os.path.exists(MODEL_PATH):
            self.model = Model(wakeword_models=[MODEL_PATH], inference_framework="onnx")
            self.model_name = "hey_anti"
        else:
            self.model = Model(wakeword_models=["hey_jarvis_v0.1.onnx"], inference_framework="onnx")
            self.model_name = "hey_jarvis_v0.1"

        # Transcript Watcher for auto read-aloud and remote dispatch correlation
        self.transcript_watcher = TranscriptWatcher(
            on_new_response=self._on_assistant_response,
            on_user_input=self._on_user_input
        )

        # Wire speech player state changes to tray and HUD
        def _on_player_state(st: str):
            if st == "paused":
                self.set_tray_state("paused", "AudioMind: Speech Paused (Click to Resume)")
                if self.hud_enabled:
                    self.hud.set_status("AudioMind • Paused", state="paused")
            elif st == "playing":
                self.set_tray_state("anti_speaking", "AudioMind: Speaking...")
                if self.hud_enabled:
                    self.hud.show(state="speaking", status="AudioMind • Speaking")
            elif st == "rewound":
                if self.hud_enabled:
                    self.hud.set_status("AudioMind • Rewound 5s", state="speaking" if is_speaking() else "paused")
            elif st == "forwarded":
                if self.hud_enabled:
                    self.hud.set_status("AudioMind • Forward 5s", state="speaking" if is_speaking() else "paused")
            elif st in ("chapter_skipped", "chapter_repeated"):
                cur_ch, tot_ch, title = get_chapter_info()
                if self.hud_enabled:
                    self.hud.set_status(f"AudioMind • Ch {cur_ch}/{tot_ch}: {title[:20]}", state="speaking" if is_speaking() else "paused")
            elif st in ("stopped", "finished"):
                if self.hud_enabled:
                    self.hud.hide()
                if not self.muted:
                    self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                else:
                    self.set_tray_state("muted", "AudioMind: Microphone Muted")

        get_speech_player().on_state_change = _on_player_state

        # System Tray setup
        self.tray_icon = None
        self._setup_tray()

    def _setup_tray(self):
        menu = pystray.Menu(
            item(lambda it: f"🎙️  AudioMind • {'Muted' if self.muted else 'Active'}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("💬  Auto-Submit Voice to Chat", self.toggle_auto_submit, checked=lambda item: self.auto_submit),
            item("🔊  Auto-Read Assistant Responses", self.toggle_auto_read, checked=lambda item: self.auto_read),
            pystray.Menu.SEPARATOR,
            item(lambda it: "▶️  Resume Speech (Paused)" if is_paused() else "⏸️  Pause Speech", self.toggle_speech_pause, enabled=lambda it: is_speech_active()),
            item("⏩  Forward 5 Seconds", self.forward_speech_5, enabled=lambda it: is_speech_active()),
            item("⏪  Rewind 5 Seconds", self.rewind_speech_5, enabled=lambda it: is_speech_active()),
            item("⏭️  Skip to Next Chapter", self.skip_next_chapter, enabled=lambda it: is_speech_active()),
            item("⏮️  Repeat Last Chapter", self.repeat_chapter, enabled=lambda it: is_speech_active() or bool(self.last_spoken_summary)),
            item("⏹️  Stop Speaking / Interrupt", self.interrupt_speech, enabled=lambda it: is_speech_active()),
            item("🔁  Replay Last Response", self.replay_last_response),
            item("📖  Read Highlighted Text  (Ctrl+Alt+R)", self.read_highlighted_text),
            pystray.Menu.SEPARATOR,
            item("🔇  Mute Microphone", self.toggle_mute, checked=lambda item: self.muted),
            item("🌊  Desktop Waveform HUD", self.toggle_hud, checked=lambda item: self.hud_enabled, default=True),
            item("📌  Dock Waveform to Bottom-Right", self.toggle_hud_dock, checked=lambda item: self.hud.position == "bottom_right"),
            item("📱  Remote Assistant Dispatch Listener", self.toggle_remote_listener, checked=lambda item: self.remote_poll_enabled),
            pystray.Menu.SEPARATOR,
            item("👋  Test Voice Greeting", self.test_greeting),
            item("🛡️  Open Firewall State", self.open_firewall_audit),
            pystray.Menu.SEPARATOR,
            item("❌  Exit AudioMind", self.exit_app)
        )
        self.tray_icon = pystray.Icon(
            "AudioMind",
            create_tray_icon_image("listening"),
            title="AudioMind: Active & Listening",
            menu=menu
        )

    def set_tray_state(self, state: str, title: str):
        """Update system tray icon and tooltip."""
        self.current_state = state
        if self.tray_icon:
            self.tray_icon.title = title
            self.tray_icon.icon = create_tray_icon_image(state, pulse=0.0)

    def _pulse_worker(self):
        """Smoothly pulse system tray icon glow and badge while Anti is active."""
        phase = 0.0
        user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        while self.running:
            try:
                # Track last active application window for universal highlighted text capture
                if user32:
                    fg = user32.GetForegroundWindow()
                    if fg:
                        buf = ctypes.create_unicode_buffer(128)
                        user32.GetClassNameW(fg, buf, 128)
                        cls_name = buf.value
                        if cls_name not in ("Shell_TrayWnd", "NotifyIconOverflowWindow", "TkTopLevel"):
                            self.last_app_hwnd = fg

                state = self.current_state
                if state in ("anti_speaking", "processing", "user_speaking", "thinking"):
                    phase += 0.35
                    pulse = 0.5 * (1.0 + math.sin(phase))
                    if self.tray_icon:
                        self.tray_icon.icon = create_tray_icon_image(state, pulse=pulse)
                    time.sleep(0.12)
                else:
                    time.sleep(0.20)
            except Exception:
                time.sleep(0.5)

    def toggle_auto_submit(self, icon=None, item=None):
        self.auto_submit = not self.auto_submit
        print(f"[*] Auto-Submit Voice to Chat: {self.auto_submit}")

    def toggle_auto_read(self, icon=None, item=None):
        self.auto_read = not self.auto_read
        if not self.auto_read:
            stop_speech()
        print(f"[*] Auto-Read Assistant Responses: {self.auto_read}")

    def toggle_remote_listener(self, icon=None, item=None):
        self.remote_poll_enabled = not self.remote_poll_enabled
        print(f"[*] Remote Phone Command Listener: {self.remote_poll_enabled}")

    def toggle_speech_pause(self, icon=None, item=None):
        paused = toggle_pause()
        print(f"[*] Speech Pause Toggled: now {'PAUSED' if paused else 'PLAYING'}")
        if self.hud_enabled:
            if paused:
                self.hud.set_status("AudioMind • Paused", state="paused")
            else:
                self.hud.set_status("AudioMind • Speaking", state="speaking")
        if paused:
            self.set_tray_state("paused", "AudioMind: Speech Paused (Click to Resume)")
        else:
            self.set_tray_state("anti_speaking", "AudioMind: Speaking...")

    def forward_speech_5(self, icon=None, item=None):
        new_pos = fast_forward_speech(5.0)
        if self.hud_enabled:
            self.hud.set_status("AudioMind • Forward 5s", state="speaking" if is_speaking() else "paused")
        print(f"[*] Speech Forwarded 5s -> position: {new_pos:.1f}s")

    def rewind_speech_5(self, icon=None, item=None):
        new_pos = rewind_speech(5.0)
        if self.hud_enabled:
            self.hud.set_status("AudioMind • Rewound 5s", state="speaking" if is_speaking() else "paused")
        print(f"[*] Speech Rewound 5s -> position: {new_pos:.1f}s")

    def rewind_speech_10(self, icon=None, item=None):
        new_pos = rewind_speech(10.0)
        if self.hud_enabled:
            self.hud.set_status("AudioMind • Rewound 10s", state="speaking" if is_speaking() else "paused")
        print(f"[*] Speech Rewound 10s -> position: {new_pos:.1f}s")

    def skip_next_chapter(self, icon=None, item=None):
        new_ch = skip_to_next_chapter()
        cur_ch, tot_ch, title = get_chapter_info()
        if self.hud_enabled:
            self.hud.set_status(f"AudioMind • Ch {cur_ch}/{tot_ch}: {title[:20]}", state="speaking" if is_speaking() else "paused")
        print(f"[*] Skipped to Next Chapter -> Chapter {cur_ch}/{tot_ch} ({title})")

    def repeat_chapter(self, icon=None, item=None):
        if is_speech_active():
            new_ch = repeat_last_chapter()
            cur_ch, tot_ch, title = get_chapter_info()
            if self.hud_enabled:
                self.hud.set_status(f"AudioMind • Ch {cur_ch}/{tot_ch}: {title[:20]}", state="speaking" if is_speaking() else "paused")
            print(f"[*] Repeated Chapter -> Chapter {cur_ch}/{tot_ch} ({title})")
        elif self.last_spoken_summary:
            self.replay_last_response()

    def interrupt_speech(self, icon=None, item=None):
        stop_speech()
        if self.hud_enabled:
            self.hud.hide()
        if not self.muted:
            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
        else:
            self.set_tray_state("muted", "AudioMind: Microphone Muted")

    def replay_last_response(self, icon=None, item=None):
        if self.last_spoken_summary:
            self._on_assistant_response(self.last_spoken_summary)
        else:
            speak("There is no recent assistant response to replay.")

    def read_highlighted_text(self, icon=None, item=None):
        """
        Captures highlighted/selected text from the active application window
        and reads it aloud using the Ava neural speech engine (or offline SAPI fallback).
        """
        try:
            from desktop.audio.read_aloud import capture_highlighted_text
        except ImportError:
            try:
                from audio.read_aloud import capture_highlighted_text
            except ImportError:
                capture_highlighted_text = lambda target_hwnd: None

        target_hwnd = getattr(self, "last_app_hwnd", None)
        text = capture_highlighted_text(target_hwnd)
        if text and text.strip():
            print(f"\n[📖 READ HIGHLIGHTED TEXT]: Captured {len(text.split())} words: \"{text[:60]}...\"")
            if self.hud_enabled:
                self.hud.show(state="speaking", status="AudioMind • Reading Selection")
            self.set_tray_state("anti_speaking", "AudioMind: Reading Selection...")

            def _on_start():
                if self.hud_enabled:
                    self.hud.show(state="speaking", status="AudioMind • Reading Selection")
                self.set_tray_state("anti_speaking", "AudioMind: Reading Selection...")

            def _on_lvl(lvl: float):
                if self.hud_enabled and is_speaking():
                    self.hud.update_audio_level(lvl)

            def _read_worker():
                try:
                    speak(text, on_start=_on_start, on_level=_on_lvl)
                except Exception as e:
                    print(f"[!] Read highlighted text error: {e}")
                finally:
                    if is_speaking():
                        pass
                    elif is_paused():
                        if self.hud_enabled:
                            self.hud.set_status("AudioMind • Paused", state="paused")
                        self.set_tray_state("paused", "AudioMind: Speech Paused")
                    else:
                        if self.hud_enabled:
                            self.hud.hide()
                        if not self.muted:
                            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                        else:
                            self.set_tray_state("muted", "AudioMind: Microphone Muted")

            threading.Thread(target=_read_worker, daemon=True).start()
        else:
            print("[ℹ️ READ HIGHLIGHTED TEXT]: No text was highlighted on screen.")
            if self.hud_enabled:
                self.hud.show(state="idle", status="AudioMind • No Selection")
            speak("No text was highlighted. Highlight some text on screen and try again.")
            if self.hud_enabled:
                time.sleep(1.0)
                self.hud.hide()
            if not self.muted:
                self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
            else:
                self.set_tray_state("muted", "AudioMind: Microphone Muted")

    def send_remote_ack(self, dispatch_id: str, status: str = "EXECUTED", summary: Optional[str] = None):
        """Sends execution or rejection ACK back to Cloud Relay without X-Admin-Key."""
        if not self.remote_api_url:
            return
        token = get_desktop_session_token()
        if not token:
            return
        def _send():
            try:
                import json
                import urllib.request
                ack_url = f"{self.remote_api_url}/api/agent/ack"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "AntiVoice-Desktop/1.0",
                    "Content-Type": "application/json"
                }
                summary_clean = summary[:600] if summary else "Execution completed."
                payload = json.dumps({
                    "dispatch_id": dispatch_id,
                    "status": status,
                    "execution_summary": summary_clean
                }).encode("utf-8")
                req = urllib.request.Request(ack_url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
                print(f"[📱 REMOTE DISPATCH ACK]: id={dispatch_id} -> {status}")
            except Exception as ack_err:
                print(f"[!] Remote dispatch ack error: {ack_err}")
        threading.Thread(target=_send, daemon=True).start()

    def _on_user_input(self, text: str, filepath: str, step_index: int):
        """Callback from TranscriptWatcher when a user prompt is submitted into Antigravity."""
        if not getattr(self, "pending_remote_dispatch", None):
            return

        now = time.time()
        pasted_at = self.pending_remote_dispatch.get("pasted_at", 0)
        # Timeout after 5 minutes TTL
        if now - pasted_at > 300:
            old_id = self.pending_remote_dispatch.get("id")
            self.send_remote_ack(old_id, status="FAILED", summary="Timed out waiting for manual user confirmation.")
            self.pending_remote_dispatch = None
            return

        if not self.pending_remote_dispatch.get("submitted"):
            expected = self.pending_remote_dispatch.get("instruction", "").strip().lower()
            submitted_text = text.strip().lower()
            expected_norm = " ".join(expected.split())
            submitted_norm = " ".join(submitted_text.split())

            # Check if this submitted prompt matches or contains the remote instruction
            if expected_norm in submitted_norm or submitted_norm in expected_norm:
                print(f"[✓ REMOTE DISPATCH CONFIRMED BY USER]: id={self.pending_remote_dispatch['id']} submitted at step {step_index}")
                self.pending_remote_dispatch["submitted"] = True
                self.pending_remote_dispatch["matched_transcript"] = filepath
                self.pending_remote_dispatch["matched_step_index"] = step_index
            else:
                # User submitted a different prompt while a remote command was waiting in chat
                old_id = self.pending_remote_dispatch.get("id")
                print(f"[!] User submitted a different command in IDE. Cancelling remote dispatch {old_id}.")
                self.send_remote_ack(old_id, status="FAILED", summary="Remote dispatch cancelled or overwritten by different local command.")
                self.pending_remote_dispatch = None

    def _on_assistant_response(self, text: str, filepath: Optional[str] = None, step_index: Optional[int] = None):
        """Callback from TranscriptWatcher when a new assistant response completes."""
        self.last_spoken_summary = text

        # If a remote dispatch was confirmed by the user and executed in this transcript, send execution ACK
        if getattr(self, "pending_remote_dispatch", None) and self.pending_remote_dispatch.get("submitted"):
            dispatch = self.pending_remote_dispatch
            matched_file = dispatch.get("matched_transcript")
            matched_step = dispatch.get("matched_step_index", 0)

            # Ensure response belongs to the same conversation file and follows the user's confirmation
            file_matches = (filepath is None or matched_file is None or filepath == matched_file)
            step_matches = (step_index is None or step_index > matched_step)

            if file_matches and step_matches:
                dispatch_id = dispatch["id"]
                self.pending_remote_dispatch = None
                print(f"[✓ REMOTE DISPATCH EXECUTED]: id={dispatch_id} sending ACK with response summary")
                self.send_remote_ack(dispatch_id, status="EXECUTED", summary=text)

        if not self.auto_read or not text:
            return

        def _speak_worker():
            with self._speak_lock:
                stop_speech()
                try:
                    print(f"\n[🔊 ASSISTANT RESPONSE COMPLETED]: Preparing audio via Ava @ 48kHz...")
                    self.set_tray_state("anti_speaking", "AudioMind: Preparing audio...")
                    if self.hud_enabled:
                        self.hud.show(state="thinking", status="AudioMind • Preparing...")

                    def _on_playback_start():
                        print("[🔊 PLAYBACK COMMENCED]: Audio streaming through headset.")
                        self.set_tray_state("anti_speaking", "AudioMind: Speaking...")
                        if self.hud_enabled:
                            self.hud.show(state="speaking", status="AudioMind • Speaking")

                    def _on_level(level: float):
                        if self.hud_enabled and is_speaking():
                            self.hud.update_audio_level(level)

                    speak(text, on_start=_on_playback_start, on_level=_on_level)

                except Exception as e:
                    print(f"[!] Read-aloud error: {e}")
                finally:
                    if is_speaking():
                        pass
                    elif is_paused():
                        if self.hud_enabled:
                            self.hud.set_status("AudioMind • Paused", state="paused")
                        self.set_tray_state("paused", "AudioMind: Speech Paused")
                    else:
                        if self.hud_enabled:
                            self.hud.hide()
                        if not self.muted:
                            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                        else:
                            self.set_tray_state("muted", "AudioMind: Microphone Muted")

        threading.Thread(target=_speak_worker, daemon=True).start()

    def toggle_mute(self, icon, item):
        self.muted = not self.muted
        if self.muted:
            self.set_tray_state("muted", "AudioMind: Microphone Muted (Paused)")
            if self.hud_enabled:
                self.hud.show(state="idle", status="AudioMind • Muted")
                time.sleep(1.0)
                self.hud.hide()
        else:
            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
            if self.hud_enabled:
                self.hud.show(state="listening", status="AudioMind • Listening")
                time.sleep(1.0)
                self.hud.hide()

    def toggle_hud(self, icon, item):
        self.hud_enabled = not self.hud_enabled
        if not self.hud_enabled:
            self.hud.hide()

    def toggle_hud_dock(self, icon=None, item=None):
        new_pos = "bottom_center" if self.hud.position == "bottom_right" else "bottom_right"
        self.hud.set_position(new_pos)
        print(f"[*] HUD Position set to: {new_pos}")

    def test_greeting(self, icon=None, item=None):
        def _greet():
            self.set_tray_state("anti_speaking", "AudioMind: Speaking...")
            if self.hud_enabled:
                self.hud.show(state="speaking", status="AudioMind • Speaking")
                self.hud.update_audio_level(0.75)
            speak("Hey! AudioMind is online and guarding your terminal.")
            if self.hud_enabled:
                self.hud.hide()
            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
        threading.Thread(target=_greet, daemon=True).start()

    def open_firewall_audit(self, icon=None, item=None):
        log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "state.md"))
        if os.path.exists(log_path):
            try:
                os.startfile(log_path)
            except Exception:
                subprocess.run(["notepad", log_path])

    def exit_app(self, icon=None, item=None):
        self.running = False
        if hasattr(self, "transcript_watcher") and self.transcript_watcher:
            self.transcript_watcher.stop()
        if self.hud:
            self.hud.destroy()
        if self.tray_icon:
            self.tray_icon.stop()
        sys.exit(0)

    def capture_command_audio(
        self, 
        aec_stream: WasapiAecStream, 
        max_duration_sec: float = 20.0, 
        initial_timeout_sec: float = 4.5, 
        trailing_silence_sec: float = 1.4,
        speech_threshold_rms: float = 45.0
    ) -> Tuple[np.ndarray, str]:
        """
        Captures user speech using a resilient dynamic-noise-floor Voice Activity Detection (VAD) loop.
        Measures initial ambient room noise and dynamically adjusts the silence threshold
        so commands cleanly finish within 1.4s of the user pausing speech.
        """
        collected_frames = []
        pre_roll = deque(maxlen=4)  # ~320ms rolling buffer to prevent clipped word onsets
        has_spoken = False
        speech_start_time = None
        silence_start = None
        start_time = time.time()
        
        # Adaptive noise floor calibration during initial pre-speech listening
        ambient_samples = []
        silence_threshold = speech_threshold_rms

        print(f"[{time.strftime('%X')}] [🎙️ LISTENING]: Awaiting speech (up to {initial_timeout_sec}s to start, {max_duration_sec}s max)...")

        while True:
            chunk = aec_stream.read_chunk()
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32)**2)))

            # Feed live audio volume to HUD waveform
            if self.hud_enabled:
                normalized_level = min(1.0, max(0.0, (rms - 8.0) / 1200.0))
                self.hud.update_audio_level(normalized_level)

            now = time.time()

            if not has_spoken:
                pre_roll.append(chunk)
                if len(ambient_samples) < 12:
                    ambient_samples.append(rms)
                    if len(ambient_samples) == 12:
                        avg_ambient = float(np.mean(ambient_samples))
                        # Set silence threshold dynamically above ambient floor
                        silence_threshold = max(speech_threshold_rms, avg_ambient + 14.0)

                trigger_threshold = max(speech_threshold_rms, silence_threshold)
                if rms >= trigger_threshold:
                    has_spoken = True
                    speech_start_time = now
                    silence_start = None
                    collected_frames.extend(list(pre_roll))
                    print(f"[{time.strftime('%X')}] [🗣️ SPEECH DETECTED]: Recording utterance (RMS: {rms:.1f}, silence threshold: {silence_threshold:.1f})...")
                    if self.hud_enabled:
                        self.hud.set_status("AudioMind • Listening", state="listening")
                else:
                    if now - start_time >= initial_timeout_sec:
                        print(f"[{time.strftime('%X')}] [ℹ️ INITIAL TIMEOUT]: No speech detected within {initial_timeout_sec}s.")
                        return np.array([], dtype=np.int16), "initial_timeout"
            else:
                collected_frames.append(chunk)
                if rms < silence_threshold:
                    if silence_start is None:
                        silence_start = now
                    elif now - silence_start >= trailing_silence_sec:
                        duration = now - speech_start_time
                        print(f"[{time.strftime('%X')}] [⏱️ CAPTURE FINISHED]: {duration:.1f}s speech recorded ({trailing_silence_sec}s pause detected).")
                        break
                else:
                    silence_start = None

                if now - speech_start_time >= max_duration_sec:
                    print(f"[{time.strftime('%X')}] [⏱️ MAX DURATION]: Hit {max_duration_sec}s ceiling.")
                    break

            time.sleep(0.005)

        if collected_frames:
            return np.concatenate(collected_frames), "speech_captured"
        return np.array([], dtype=np.int16), "no_audio"

    def transcribe(self, pcm_16k: np.ndarray) -> str:
        if len(pcm_16k) < 4000:
            return ""
        audio_bytes = pcm_16k.tobytes()
        audio_data = sr.AudioData(audio_bytes, sample_rate=16000, sample_width=2)
        try:
            return self.recognizer.recognize_google(audio_data).strip()
        except sr.UnknownValueError:
            print("[⚠️ STT]: Speech was unclear / not recognized by Google Speech Recognition.")
            return ""
        except sr.RequestError as e:
            print(f"[!] STT API network error: {e}")
            return ""
        except Exception as e:
            print(f"[!] STT unexpected error: {e}")
            return ""

    def _focus_antigravity(self):
        """
        Ensures the primary Antigravity IDE/App window is focused before keystroke injection,
        even if another application (Chrome, Android Studio, Word) currently owns foreground focus.
        Uses Win32 Alt-key foreground lock bypass and AttachThreadInput.
        Returns:
            (best_hwnd, best_rect)
        """
        try:
            attach_to_default_desktop()
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            candidates = []

            def enum_cb(hwnd, extra):
                if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
                if h_proc:
                    buf = ctypes.create_unicode_buffer(260)
                    sz = wintypes.DWORD(260)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(sz)):
                        exe_name = os.path.basename(buf.value).lower()
                        if "antigravity" in exe_name:
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            w = rect.right - rect.left
                            h = rect.bottom - rect.top
                            title = ctypes.create_unicode_buffer(260)
                            user32.GetWindowTextW(hwnd, title, 260)
                            cls = ctypes.create_unicode_buffer(260)
                            user32.GetClassNameW(hwnd, cls, 260)
                            # Only target substantive UI windows (skip zero-size, DDE, utility windows)
                            if w > 300 and h > 300:
                                candidates.append((hwnd, pid.value, w, h, rect, title.value, exe_name))
                    kernel32.CloseHandle(h_proc)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            h_desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if h_desk:
                user32.EnumDesktopWindows(h_desk, WNDENUMPROC(enum_cb), 0)
            else:
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            if not candidates:
                return None, None

            # Target application selection:
            # Default to Antigravity IDE when installed on the workstation so that closing
            # the IDE safely fails closed rather than inadvertently typing into the standalone Antigravity app.
            ide_installed = os.path.exists(
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe")
            )
            target_mode = os.getenv("ANTIGRAVITY_TARGET_APP", "ide" if ide_installed else "auto").lower()

            ide_candidates = [c for c in candidates if c[6] == ANTIGRAVITY_IDE_EXE]
            if target_mode == "ide":
                chosen_candidates = ide_candidates
            elif target_mode == "standalone":
                chosen_candidates = [c for c in candidates if c[6] != ANTIGRAVITY_IDE_EXE]
            else:  # auto
                chosen_candidates = ide_candidates or candidates

            if not chosen_candidates:
                return None, None

            best_hwnd, best_pid, _, _, best_rect, _, best_exe = max(chosen_candidates, key=lambda c: c[2] * c[3])
            self._focused_is_ide = (best_exe == ANTIGRAVITY_IDE_EXE)
            self._focused_pid = best_pid

            # Windows 10/11 Foreground Lock Bypass:
            # 1. Simulate an Alt key down/up to grant foreground change permission
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # 2. Attach thread inputs between current thread, current foreground window, and target window
            cur_tid = kernel32.GetCurrentThreadId()
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            target_tid = user32.GetWindowThreadProcessId(best_hwnd, None)

            if fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
            if target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, True)

            # 3. Restore (if minimized), bring to top, and set foreground
            user32.ShowWindow(best_hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(best_hwnd)
            user32.BringWindowToTop(best_hwnd)

            # 4. Detach thread inputs
            if target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, False)
            if fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, False)

            user32.GetWindowRect(best_hwnd, ctypes.byref(best_rect))
            return best_hwnd, best_rect
        except Exception as e:
            print(f"[!] Window focus error: {e}")
            return None, None

    def is_elevation_mismatch(self, target_pid: int) -> tuple[bool, Optional[str]]:
        """Checks if target process elevation blocks synthetic keystrokes."""
        return check_elevation_mismatch(target_pid)

    def submit_to_antigravity_chat(self, prompt_text: str, press_enter: Optional[bool] = None):
        """
        Injects the prompt directly into the active Antigravity IDE chat window
        via system clipboard (Ctrl+V) and submits with Enter only if press_enter is True
        (or if press_enter is None and self.auto_submit is enabled).
        Remote dispatches MUST pass press_enter=False (never auto-submits remote input).
        """
        try:
            user32 = ctypes.windll.user32

            # 1. Focus Antigravity window
            best_hwnd, rect = self._focus_antigravity()
            if not best_hwnd or not rect:
                print("[!] Antigravity window not found. Aborting prompt injection (no keystrokes sent).")
                self.last_injection_error = "Antigravity window not found. Nothing was typed."
                return False

            # Check for elevation mismatch (UIPI blocks keystrokes if target is elevated and we are not)
            target_pid = getattr(self, "_focused_pid", None)
            if target_pid is None:
                try:
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(best_hwnd, ctypes.byref(pid))
                    target_pid = pid.value
                except Exception:
                    target_pid = 0

            check_mismatch = getattr(self, "is_elevation_mismatch", check_elevation_mismatch)
            res = check_mismatch(target_pid) if callable(check_mismatch) else (False, None)
            if isinstance(res, tuple):
                has_mismatch, mismatch_msg = res
            elif res is True:
                has_mismatch, mismatch_msg = True, "Antigravity is running as administrator, so Anti can't type into it."
            elif res is None:
                has_mismatch, mismatch_msg = True, "Anti couldn't verify Antigravity's permissions, so nothing was typed."
            else:
                has_mismatch, mismatch_msg = False, None

            if has_mismatch:
                msg = mismatch_msg or "Antigravity is running as administrator, so Anti can't type into it."
                print(f"[!] {msg}")
                if speak:
                    speak(msg)
                self.last_injection_error = msg
                return False

            # Give Windows OS and Electron time to finish WM_ACTIVATE
            time.sleep(0.18)
            if not is_foreground_window(best_hwnd):
                print("[!] Antigravity did not take foreground focus. Aborting prompt injection (no keystrokes sent).")
                self.last_injection_error = "Antigravity did not take foreground focus. Nothing was typed."
                return False

            # 2. Focus chat input box specifically!
            if getattr(self, "_focused_is_ide", False):
                # Ctrl+L -> antigravity.toggleChatFocus: deterministic, independent of window layout.
                # (Its keybinding is inactive while chat already has focus, in which case the cursor is already there.)
                VK_CONTROL = 0x11
                VK_L = 0x4C
                KEYEVENTF_KEYUP = 0x0002
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_L, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.12)  # Let Electron finish triggerFocus()
            else:
                # Standalone Antigravity app: no verified shortcut, so fall back to clicking the chat input.
                # Save original mouse cursor position so the user's mouse never visibly wanders
                orig_pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(orig_pt))

                w = rect.right - rect.left
                h = rect.bottom - rect.top
                # Target the chat input textarea (horizontally ~40% across, 48px from the bottom)
                click_x = rect.left + int(w * 0.40)
                click_y = rect.bottom - 48

                user32.SetCursorPos(click_x, click_y)
                time.sleep(0.02)
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.02)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.03)

                # Instantly restore the user's original cursor position
                user32.SetCursorPos(orig_pt.x, orig_pt.y)

            # Re-check right before typing: the click or the user may have moved focus elsewhere.
            # Ctrl+A / Ctrl+V / Enter must never land in another application (editor, terminal, email).
            if not is_foreground_window(best_hwnd):
                print("[!] Focus left Antigravity before typing. Aborting prompt injection (no keystrokes sent).")
                self.last_injection_error = "Focus left Antigravity before typing. Nothing was typed."
                return False

            # 3. Copy prompt to clipboard only after focus is secured (preserves user clipboard on focus failure)
            set_clipboard_text(prompt_text)
            time.sleep(0.05)

            # 4. Select all existing text (Ctrl+A) so new input replaces any leftover/unsubmitted text
            # rather than concatenating and accidentally executing pending unconfirmed input
            VK_CONTROL = 0x11
            VK_A = 0x41
            VK_V = 0x56
            VK_RETURN = 0x0D
            KEYEVENTF_KEYUP = 0x0002

            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_A, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(VK_A, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)

            # 5. Paste via Ctrl+V
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

            # 6. Auto-submit with Enter if enabled and requested
            should_press_enter = self.auto_submit if press_enter is None else press_enter
            if should_press_enter:
                time.sleep(0.15)
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
                print(f"[⌨️ SUBMITTED TO CHAT]: \"{prompt_text}\" (Enter pressed)")
            else:
                print(f"[📋 PASTED TO CHAT]: \"{prompt_text}\" (Awaiting manual Enter confirmation)")
            self.last_injection_error = None
            return True

        except Exception as e:
            print(f"[!] Chat injection error: {e}")
            traceback.print_exc()
            return False

    def voice_loop(self):
        """Continuous background audio listening loop with WASAPI AEC."""
        wake_cooldown_until = 0.0
        while self.running:
            try:
                with WasapiAecStream() as aec_stream:
                    print(f"[{time.strftime('%X')}] WASAPI AEC Stream initialized. Listening for 'Hey Anti'...")
                    while self.running:
                        if self.muted:
                            time.sleep(0.1)
                            continue

                        if time.time() < wake_cooldown_until:
                            time.sleep(0.01)
                            continue

                        chunk = aec_stream.read_chunk()
                        predictions = self.model.predict(chunk)
                        score = predictions.get(self.model_name, 0.0)

                        if score >= self.wakeword_threshold:
                            self.model.reset()  # Reset rolling spectrogram buffer immediately upon trigger
                            
                            # Preserve speech state for potential pause/resume/rewind commands
                            was_speaking = is_speech_active()
                            if is_speaking():
                                pause_speech()

                            print(f"\n[⚡ TRIGGER] 'Hey Anti' recognized! Score: {score:.3f}")
                            # Update Tray & HUD
                            self.set_tray_state("user_speaking", "AudioMind: Listening for your command...")
                            if self.hud_enabled:
                                self.hud.show(state="listening", status="AudioMind • Listening")

                            # Play wake acknowledgment chime
                            play_chime(rising=True)

                            # Capture user command audio with dual-phase VAD
                            audio_buf, status_reason = self.capture_command_audio(aec_stream)
                            if status_reason == "initial_timeout" or len(audio_buf) == 0:
                                self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • No Speech", state="idle")
                                    time.sleep(1.2)
                                    self.hud.hide()
                                if was_speaking and is_paused():
                                    resume_speech()
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            # Transcribe
                            if self.hud_enabled:
                                self.hud.set_status("AudioMind • Thinking", state="processing")
                            self.set_tray_state("processing", "AudioMind: Processing command...")

                            prompt_text = self.transcribe(audio_buf)
                            if not prompt_text:
                                print(f"[{time.strftime('%X')}] [⚠️ STT]: No recognizable words in {len(audio_buf)/16000:.1f}s audio.")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Didn't Catch That", state="idle")
                                    time.sleep(1.2)
                                    self.hud.hide()
                                if was_speaking and is_paused():
                                    resume_speech()
                                self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            print(f"[🗣️ USER SPOKE]: \"{prompt_text}\"")

                            # --- Built-in Assistant Voice Controls (Pause, Resume, Rewind, Stop, Chapter Navigation) ---
                            # Note: Matched via match_playback_intent only while speech is active; 'forward' is tray button only.
                            intent = match_playback_intent(prompt_text, is_speech_active())

                            if intent == "PAUSE":
                                pause_speech()
                                play_chime(rising=False)
                                self.set_tray_state("paused", "AudioMind: Speech Paused (Click to Resume)")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Paused", state="paused")
                                print(f"[⏸️ VOICE COMMAND]: Speech paused by user request.")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            elif intent == "RESUME":
                                resume_speech()
                                play_chime(rising=True)
                                self.set_tray_state("anti_speaking", "AudioMind: Speaking...")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Speaking", state="speaking")
                                print(f"[▶️ VOICE COMMAND]: Speech resumed by user request.")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            elif intent == "NEXT_CHAPTER":
                                new_ch = skip_to_next_chapter()
                                cur_ch, tot_ch, title = get_chapter_info()
                                if not is_speaking():
                                    resume_speech()
                                play_chime(rising=True)
                                if self.hud_enabled:
                                    self.hud.set_status(f"AudioMind • Ch {cur_ch}/{tot_ch}: {title[:20]}", state="speaking")
                                print(f"[⏭️ VOICE COMMAND]: Skipped to Chapter {cur_ch}/{tot_ch} ({title}).")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            elif intent == "REPEAT_CHAPTER":
                                if is_speech_active():
                                    new_ch = repeat_last_chapter()
                                    cur_ch, tot_ch, title = get_chapter_info()
                                    if not is_speaking():
                                        resume_speech()
                                    play_chime(rising=True)
                                    if self.hud_enabled:
                                        self.hud.set_status(f"AudioMind • Ch {cur_ch}/{tot_ch}: {title[:20]}", state="speaking")
                                    print(f"[⏮️ VOICE COMMAND]: Repeated Chapter {cur_ch}/{tot_ch} ({title}).")
                                elif self.last_spoken_summary:
                                    self.replay_last_response()
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            elif intent == "REWIND_5":
                                new_pos = rewind_speech(5.0)
                                if not is_speaking():
                                    resume_speech()
                                play_chime(rising=True)
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Rewound 5s", state="speaking")
                                print(f"[⏪ VOICE COMMAND]: Rewound 5 seconds to {new_pos:.1f}s.")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            elif intent == "STOP":
                                stop_speech()
                                play_chime(rising=False)
                                if self.hud_enabled:
                                    self.hud.hide()
                                self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                                print(f"[⏹️ VOICE COMMAND]: Speech stopped by user request.")
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.5
                                continue

                            # Check for "read highlighted / selected text" voice command
                            clean_prompt = prompt_text.lower().strip().rstrip(".!?").strip()
                            READ_HIGHLIGHT_PHRASES = {
                                "read this", "read highlighted text", "read selected text", "read selection",
                                "read highlighted", "read the highlighted text", "read the selected text",
                                "read what is highlighted", "read what's highlighted"
                            }
                            if clean_prompt in READ_HIGHLIGHT_PHRASES:
                                play_chime(rising=True)
                                self.read_highlighted_text()
                                aec_stream.drain()
                                self.model.reset()
                                wake_cooldown_until = time.time() + 0.8
                                continue

                            # User spoke a genuine command/prompt -> Stop any lingering speech and process via Firewall
                            stop_speech()

                            if self.hud_enabled:
                                self.hud.set_status("AudioMind • Thinking", state="processing")
                            self.set_tray_state("processing", "AudioMind: Evaluating security firewall...")

                            # Firewall Verification
                            evaluation = self.firewall.evaluate(prompt_text)

                            if evaluation.tier == RiskTier.RED:
                                play_chime(rising=False)
                                self.set_tray_state("muted", "AudioMind: Command Blocked by Firewall")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Blocked", state="processing")
                                speak("AudioMind cannot execute that command. It was blocked by the security firewall.")
                            
                            # If an unconfirmed remote dispatch was waiting in chat, cancel it
                            if getattr(self, "pending_remote_dispatch", None):
                                old_id = self.pending_remote_dispatch.get("id")
                                print(f"[!] Local voice command arrived while remote dispatch {old_id} was waiting. Cancelling remote dispatch.")
                                self.send_remote_ack(old_id, status="FAILED", summary="Superseded by local voice command before user confirmation.")
                                self.pending_remote_dispatch = None

                            if evaluation.tier == RiskTier.YELLOW:
                                play_chime(rising=True)
                                self.set_tray_state("anti_speaking", "AudioMind: Caution verified. Dispatching...")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Speaking", state="speaking")
                                speak("Caution verified. AudioMind is sending to chat.")
                                if not self.submit_to_antigravity_chat(prompt_text):
                                    if getattr(self, "last_injection_error", None) != "Antigravity is running as administrator, so Anti can't type into it.":
                                        speak("I couldn't focus Antigravity, so nothing was typed.")

                            elif evaluation.tier == RiskTier.GREEN:
                                # Instant non-blocking submit chime & zero-delay prompt injection
                                play_submit_chime()
                                self.set_tray_state("processing", "AudioMind: Working in IDE...")
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • Sent", state="processing")
                                if not self.submit_to_antigravity_chat(prompt_text):
                                    if getattr(self, "last_injection_error", None) != "Antigravity is running as administrator, so Anti can't type into it.":
                                        speak("I couldn't focus Antigravity, so nothing was typed.")

                            # Return to passive listening state
                            time.sleep(1.2)
                            if self.hud_enabled:
                                self.hud.hide()
                            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")

                            # Drain buffered mic frames and enforce refractory cooldown to eliminate trailing double-triggers
                            aec_stream.drain()
                            self.model.reset()
                            wake_cooldown_until = time.time() + 0.8
            except Exception as e:
                print(f"[!] Error in voice loop: {e}")
                traceback.print_exc()
                time.sleep(1.0)

    def _remote_dispatch_worker(self):
        """
        Polls the cloud backend (GET /api/agent/pending) for remote voice instructions
        dispatched from the user's Android companion app / Google Assistant / Gemini.
        When a pending instruction is received, brings Antigravity IDE to focus,
        displays the Desktop HUD, and injects the prompt directly into chat.
        """
        last_poll_error_logged = 0.0
        import json
        import urllib.request
        from urllib.error import HTTPError, URLError

        print(f"[*] Remote Dispatch Listener active -> polling {self.remote_api_url}/api/agent/pending")

        while self.running:
            if not self.remote_poll_enabled or not self.remote_api_url:
                time.sleep(2.0)
                continue

            try:
                token = get_desktop_session_token()
                if not token:
                    time.sleep(2.0)
                    continue

                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "AntiVoice-Desktop/1.0"
                }

                poll_url = f"{self.remote_api_url}/api/agent/pending"
                req = urllib.request.Request(poll_url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("has_pending") and data.get("dispatch"):
                            dispatch = data["dispatch"]
                            dispatch_id = dispatch.get("id")
                            raw_instruction = dispatch.get("instruction", "")
                            source = dispatch.get("source", "phone")

                            # 1. Cap instruction length (2000 chars) and strip non-printable control characters
                            instruction = raw_instruction[:2000]
                            instruction = "".join(
                                ch for ch in instruction
                                if ch in ('\n', '\r', '\t') or (ord(ch) >= 32 and ord(ch) != 127)
                            ).strip()

                            if not instruction:
                                print(f"[!] Dropping empty remote dispatch {dispatch_id}")
                                self.send_remote_ack(dispatch_id, status="FAILED", summary="Empty or invalid instruction after sanitization.")
                                continue

                            print(f"\n[📱 REMOTE DISPATCH RECEIVED]: id={dispatch_id} from {source}: \"{instruction[:80]}...\"")

                            # 2. Gate through AST Command Firewall (defense-in-depth)
                            verdict = self.firewall.evaluate(instruction)
                            if verdict.tier == RiskTier.RED or not verdict.allowed:
                                print(f"\n[🚫 REMOTE DISPATCH BLOCKED BY FIREWALL]: id={dispatch_id}: {verdict.reason}")
                                if self.hud_enabled:
                                    self.hud.show(state="muted", status="AudioMind • Command Blocked")
                                    time.sleep(1.5)
                                    self.hud.hide()
                                self.send_remote_ack(dispatch_id, status="FAILED", summary=f"Blocked by Command Firewall (RED Tier): {verdict.reason}")
                                continue

                            # 3. Track pending remote dispatch for user confirmation and correlated execution acknowledgment
                            self.pending_remote_dispatch = {
                                "id": dispatch_id,
                                "instruction": instruction,
                                "pasted_at": time.time(),
                                "submitted": False,
                                "matched_transcript": None,
                                "matched_step_index": None
                            }

                            # Visual feedback on Desktop HUD and Tray
                            self.set_tray_state("processing", f"AudioMind: Remote Command ({instruction[:25]}...)")
                            if self.hud_enabled:
                                self.hud.show(state="thinking", status="AudioMind • Remote Command")

                            # Play submit chime
                            play_submit_chime()

                            # 4. Paste into Antigravity IDE chat — NEVER auto-submit remote input!
                            # The user must physically review and press Enter themselves.
                            if not self.submit_to_antigravity_chat(instruction, press_enter=False):
                                self.pending_remote_dispatch = None
                                reason = getattr(self, "last_injection_error", None) or "Antigravity window could not be focused on the desktop. Nothing was typed."
                                self.send_remote_ack(dispatch_id, status="FAILED", summary=reason)
                                if self.hud_enabled:
                                    self.hud.set_status("AudioMind • IDE Not Focused", state="idle")
                                    time.sleep(1.5)
                                    self.hud.hide()
                                self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
                                continue

                            if self.hud_enabled:
                                self.hud.set_status("AudioMind • Pasted (Enter to Run)", state="processing")
                                time.sleep(1.5)
                                self.hud.hide()

                            self.set_tray_state("listening", "AudioMind: Listening for 'Hey Anti'")
            except HTTPError as e:
                now = time.time()
                if e.code in (401, 403):
                    if now - last_poll_error_logged > 60.0:
                        print(f"[!] Remote dispatch polling authentication rejected: HTTP {e.code}")
                        last_poll_error_logged = now
                elif now - last_poll_error_logged > 30.0:
                    print(f"[!] Remote dispatch poll HTTP {e.code}")
                    last_poll_error_logged = now
            except Exception as e:
                now = time.time()
                if now - last_poll_error_logged > 60.0:
                    print(f"[!] Remote dispatch polling error: {e}")
                    last_poll_error_logged = now

            time.sleep(1.5)

    def _start_hotkey_listener(self):
        """Registers Ctrl+Alt+R global hotkey in a dedicated Win32 message pump thread."""
        def _listener():
            if sys.platform != "win32":
                return
            user32 = ctypes.windll.user32
            HOTKEY_ID = 2026
            MOD_ALT = 0x0001
            MOD_CONTROL = 0x0002
            VK_R = 0x52  # 'R' key

            registered = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_R)
            if not registered:
                print("[!] Global hotkey Ctrl+Alt+R could not be registered (already in use).")
                return
            print("[*] Global hotkey registered: Ctrl+Alt+R -> Read Highlighted Text")
            try:
                msg = wintypes.MSG()
                while self.running:
                    res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                    if res <= 0:
                        break
                    if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:  # WM_HOTKEY
                        print("[⌨️ GLOBAL HOTKEY]: Ctrl+Alt+R triggered -> Reading highlighted text.")
                        self.read_highlighted_text()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                print(f"[!] Hotkey listener error: {e}")
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)

        threading.Thread(target=_listener, daemon=True).start()

    def run(self):
        attach_to_default_desktop()
        self.running = True
        # Start transcript watcher for assistant read-aloud
        self.transcript_watcher.start()
        print(f"[*] Transcript Watcher active across {len(self.transcript_watcher.tracked_files)} conversations")

        # Launch pulse worker for active tray animation
        self._pulse_thread = threading.Thread(target=self._pulse_worker, daemon=True)
        self._pulse_thread.start()

        # Launch remote dispatch listener in dedicated daemon thread
        dispatch_thread = threading.Thread(target=self._remote_dispatch_worker, daemon=True)
        dispatch_thread.start()

        # Launch global hotkey listener (Ctrl+Alt+R) for reading highlighted text anywhere
        self._start_hotkey_listener()

        # Launch voice loop in dedicated daemon thread
        voice_thread = threading.Thread(target=self.voice_loop, daemon=True)
        voice_thread.start()

        # Run pystray event loop on main thread (required by Windows)
        print("[*] Anti System Tray Active. Check your Windows taskbar tray area.")
        attach_to_default_desktop()
        self.tray_icon.run()

if __name__ == "__main__":
    attach_to_default_desktop()

    # Ensure single instance to prevent duplicate tray icons or audio stream conflicts
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "AudioMind_TrayApp_Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("[!] Another instance of AudioMind is already running.")
        sys.exit(0)

    app = AntiTrayApp()
    app.run()
