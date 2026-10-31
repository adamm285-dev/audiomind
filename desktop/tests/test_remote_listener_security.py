"""
Unit tests for Desktop Remote Dispatch Listener URL validation and execution ACK correlation.
Verifies fixes for:
1. URL hostname parsing (rejecting hostname prefix spoofing like http://localhost.attacker.com).
2. Selection clearing before prompt paste (preventing accidental concatenated auto-submit).
3. Correlated Done-ACKs (preventing unrelated assistant replies from falsely ACKing unsubmitted remote dispatches).
"""
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import time
import pytest
from desktop.app import is_secure_remote_url, AntiTrayApp

def test_is_secure_remote_url_https_permitted():
    assert is_secure_remote_url("https://api.example.com") is True
    assert is_secure_remote_url("https://relay.yourdomain.com:8443") is True
    assert is_secure_remote_url("https://localhost:8000") is True
    assert is_secure_remote_url("https://127.0.0.1:8000") is True

def test_is_secure_remote_url_http_loopback_permitted():
    assert is_secure_remote_url("http://localhost:8000") is True
    assert is_secure_remote_url("http://localhost") is True
    assert is_secure_remote_url("http://127.0.0.1:8000") is True
    assert is_secure_remote_url("http://127.0.0.1") is True

def test_is_secure_remote_url_hostname_spoofing_rejected():
    """Prefix check vulnerability regression test: http://localhost.attacker.com must be blocked."""
    assert is_secure_remote_url("http://localhost.attacker.com") is False
    assert is_secure_remote_url("http://localhost.attacker.com:8000") is False
    assert is_secure_remote_url("http://localhost.evil.org") is False
    assert is_secure_remote_url("http://127.0.0.1.attacker.com") is False
    assert is_secure_remote_url("http://127.0.0.1.attacker.com:8000") is False

def test_is_secure_remote_url_insecure_and_malformed_rejected():
    assert is_secure_remote_url("http://api.remotehost.com") is False
    assert is_secure_remote_url("http://192.168.1.100:8000") is False
    assert is_secure_remote_url("ftp://localhost") is False
    assert is_secure_remote_url("") is False
    assert is_secure_remote_url("   ") is False
    assert is_secure_remote_url("not_a_url") is False

class DummyApp:
    """Mock harness to verify remote dispatch tracking and correlated ACK logic in isolation."""
    def __init__(self):
        self.pending_remote_dispatch = None
        self.sent_acks = []
        self.last_spoken_summary = ""
        self.auto_read = False

    def send_remote_ack(self, dispatch_id: str, status: str = "EXECUTED", summary=None):
        self.sent_acks.append({"id": dispatch_id, "status": status, "summary": summary})

    _on_user_input = AntiTrayApp._on_user_input
    _on_assistant_response = AntiTrayApp._on_assistant_response

def test_unsubmitted_remote_dispatch_does_not_ack_unrelated_response():
    """If user hasn't pressed Enter on a remote command, unrelated agent replies must NOT send Done-ACK."""
    app = DummyApp()
    app.pending_remote_dispatch = {
        "id": "disp_test_1",
        "instruction": "Anti, run unit tests",
        "pasted_at": time.time(),
        "submitted": False,
        "matched_transcript": None,
        "matched_step_index": None
    }

    # An assistant response completes from an unrelated task or past query
    app._on_assistant_response("I have completed the weather query.", filepath="transcript_a.jsonl", step_index=5)

    # Must NOT have sent any ACK because submitted is False!
    assert len(app.sent_acks) == 0
    assert app.pending_remote_dispatch is not None
    assert app.pending_remote_dispatch["submitted"] is False

def test_confirmed_remote_dispatch_acks_only_matching_transcript_response():
    """Once user presses Enter, Done-ACK is sent only when the matching transcript produces a response."""
    app = DummyApp()
    app.pending_remote_dispatch = {
        "id": "disp_test_2",
        "instruction": "Anti, run unit tests",
        "pasted_at": time.time(),
        "submitted": False,
        "matched_transcript": None,
        "matched_step_index": None
    }

    # User presses Enter on the remote instruction in transcript_main.jsonl
    app._on_user_input("Anti, run unit tests", filepath="transcript_main.jsonl", step_index=10)
    assert app.pending_remote_dispatch["submitted"] is True
    assert app.pending_remote_dispatch["matched_transcript"] == "transcript_main.jsonl"
    assert app.pending_remote_dispatch["matched_step_index"] == 10

    # A response completes on a DIFFERENT transcript (e.g. background tab)
    app._on_assistant_response("Tab B finished compilation.", filepath="transcript_tab_b.jsonl", step_index=20)
    assert len(app.sent_acks) == 0  # Ignored!

    # The actual response completes on transcript_main.jsonl
    app._on_assistant_response("All 7 tests passed successfully.", filepath="transcript_main.jsonl", step_index=11)
    assert len(app.sent_acks) == 1
    assert app.sent_acks[0]["id"] == "disp_test_2"
    assert app.sent_acks[0]["status"] == "EXECUTED"
    assert app.sent_acks[0]["summary"] == "All 7 tests passed successfully."
    assert app.pending_remote_dispatch is None

def test_different_user_input_cancels_pending_remote_dispatch():
    """If user clears the chat box and submits a different prompt, the remote dispatch is marked FAILED."""
    app = DummyApp()
    app.pending_remote_dispatch = {
        "id": "disp_test_3",
        "instruction": "Anti, delete production database",
        "pasted_at": time.time(),
        "submitted": False,
        "matched_transcript": None,
        "matched_step_index": None
    }

    # User types a completely different prompt
    app._on_user_input("Anti, what is the meaning of life?", filepath="transcript_main.jsonl", step_index=1)
    assert len(app.sent_acks) == 1
    assert app.sent_acks[0]["id"] == "disp_test_3"
    assert app.sent_acks[0]["status"] == "FAILED"
    assert "cancelled or overwritten" in app.sent_acks[0]["summary"]
    assert app.pending_remote_dispatch is None


# --- Focus guard: no synthetic keystroke may land outside the Antigravity window ---

import ctypes as _real_ctypes
from types import SimpleNamespace
import desktop.app as app_module

class FakeUser32:
    def __init__(self):
        self.keys = []
        self.clicks = 0
    def keybd_event(self, vk, scan, flags, extra):
        self.keys.append(vk)
    def mouse_event(self, *args):
        self.clicks += 1
    def SetCursorPos(self, x, y):
        return 1
    def GetCursorPos(self, pt):
        return 1

def _patch_win32(monkeypatch, focus_result, foreground_answers):
    user32 = FakeUser32()
    clipboard_calls = []
    monkeypatch.setattr(app_module, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=user32), byref=_real_ctypes.byref))
    monkeypatch.setattr(app_module, "set_clipboard_text", lambda text: clipboard_calls.append(text))
    monkeypatch.setattr(app_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(app_module, "is_current_process_elevated", lambda: False)
    monkeypatch.setattr(app_module, "is_process_elevated", lambda pid: False)
    answers = iter(foreground_answers)
    monkeypatch.setattr(app_module, "is_foreground_window", lambda hwnd: next(answers))
    app = SimpleNamespace(auto_submit=True, _focus_antigravity=lambda: focus_result, _focused_pid=1234)
    app.clipboard_calls = clipboard_calls
    return app, user32

def _rect():
    return app_module.wintypes.RECT(0, 0, 1200, 800)

def test_no_keystrokes_when_antigravity_window_not_found(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (None, None), [])
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    assert user32.keys == []
    assert user32.clicks == 0
    assert app.clipboard_calls == []  # user clipboard untouched if window not found

def test_no_keystrokes_when_antigravity_does_not_take_focus(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [False])
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    assert user32.keys == []
    assert user32.clicks == 0

def test_no_keystrokes_when_focus_moves_away_after_click(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, False])
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    assert user32.keys == []  # no Ctrl+A / Ctrl+V / Enter into whatever stole focus

def test_keystrokes_sent_when_antigravity_keeps_focus(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests", press_enter=False) is True
    assert 0x41 in user32.keys and 0x56 in user32.keys  # Ctrl+A, Ctrl+V
    assert 0x0D not in user32.keys  # no Enter when press_enter=False

def test_ide_uses_ctrl_l_chat_focus_instead_of_click(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    app._focused_is_ide = True
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests", press_enter=False) is True
    assert user32.clicks == 0  # no coordinate guess in the IDE
    keys = user32.keys
    assert 0x4C in keys  # Ctrl+L -> antigravity.toggleChatFocus
    assert keys.index(0x4C) < keys.index(0x41) < keys.index(0x56)  # focus chat, then select-all, then paste

def test_ide_chat_focus_still_aborts_if_focus_lost(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, False])
    app._focused_is_ide = True
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    assert 0x41 not in user32.keys and 0x56 not in user32.keys and 0x0D not in user32.keys

def test_standalone_app_falls_back_to_click(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    app._focused_is_ide = False
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests", press_enter=False) is True
    assert user32.clicks == 2  # mouse down + up
    assert 0x4C not in user32.keys

def test_clipboard_preserved_when_focus_fails(monkeypatch):
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [False])
    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, sensitive content") is False
    assert app.clipboard_calls == []  # user clipboard untouched when focus fails

def test_real_is_foreground_window_handles_types():
    assert app_module.is_foreground_window(None) is False
    assert app_module.is_foreground_window(0) is False

def test_elevation_mismatch_aborts_injection_and_speaks(monkeypatch):
    """When target Antigravity process is elevated and Anti is not, injection must fail closed."""
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    app._focused_pid = 5678

    spoken = []
    monkeypatch.setattr(app_module, "speak", lambda msg: spoken.append(msg))
    monkeypatch.setattr(app_module, "is_current_process_elevated", lambda: False)
    monkeypatch.setattr(app_module, "is_process_elevated", lambda pid: True)

    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    # No keys sent
    assert user32.keys == []
    assert user32.clicks == 0
    # Clipboard completely untouched
    assert app.clipboard_calls == []
    # Reason recorded and spoken aloud
    expected_msg = "Antigravity is running as administrator, so Anti can't type into it."
    assert app.last_injection_error == expected_msg
    assert expected_msg in spoken

def test_elevation_unknown_aborts_injection_and_speaks(monkeypatch):
    """When target Antigravity process elevation cannot be verified (None), injection must fail closed."""
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    app._focused_pid = 5678

    spoken = []
    monkeypatch.setattr(app_module, "speak", lambda msg: spoken.append(msg))
    monkeypatch.setattr(app_module, "is_current_process_elevated", lambda: False)
    monkeypatch.setattr(app_module, "is_process_elevated", lambda pid: None)

    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests") is False
    # No keys sent
    assert user32.keys == []
    assert user32.clicks == 0
    # Clipboard completely untouched
    assert app.clipboard_calls == []
    # Reason recorded and spoken aloud
    expected_msg = "Anti couldn't verify Antigravity's permissions, so nothing was typed."
    assert app.last_injection_error == expected_msg
    assert expected_msg in spoken

def test_no_elevation_mismatch_allows_injection(monkeypatch):
    """When elevation matches, prompt injection proceeds normally."""
    app, user32 = _patch_win32(monkeypatch, (1234, _rect()), [True, True])
    app._focused_pid = 5678

    monkeypatch.setattr(app_module, "is_current_process_elevated", lambda: False)
    monkeypatch.setattr(app_module, "is_process_elevated", lambda pid: False)

    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, run tests", press_enter=False) is True
    assert 0x41 in user32.keys and 0x56 in user32.keys  # Ctrl+A, Ctrl+V
    assert app.clipboard_calls == ["Anti, run tests"]
    assert app.last_injection_error is None

def test_remote_dispatch_fails_with_elevation_mismatch_reason(monkeypatch):
    """When remote dispatch hits elevation mismatch, ACK FAILED contains the exact mismatch reason."""
    acks = []
    class RemoteTestApp:
        def __init__(self):
            self.last_injection_error = "Antigravity is running as administrator, so Anti can't type into it."
            self.pending_remote_dispatch = None

        def submit_to_antigravity_chat(self, instruction, press_enter=False):
            return False

        def send_remote_ack(self, dispatch_id, status="EXECUTED", summary=None):
            acks.append({"id": dispatch_id, "status": status, "summary": summary})

    test_app = RemoteTestApp()
    instruction = "Anti, run test suite"
    dispatch_id = "disp_uipi_123"

    if not test_app.submit_to_antigravity_chat(instruction, press_enter=False):
        reason = getattr(test_app, "last_injection_error", None) or "Antigravity window could not be focused on the desktop. Nothing was typed."
        test_app.send_remote_ack(dispatch_id, status="FAILED", summary=reason)

    assert len(acks) == 1
    assert acks[0]["id"] == "disp_uipi_123"
    assert acks[0]["status"] == "FAILED"
    assert acks[0]["summary"] == "Antigravity is running as administrator, so Anti can't type into it."

def test_real_elevation_helpers():
    """Verify elevation helper functions execute and return expected types."""
    assert app_module.is_process_elevated(0) is None
    mismatch, reason = app_module.check_elevation_mismatch(0)
    assert mismatch is True
    assert "Anti couldn't verify" in reason
    mismatch_self, reason_self = app_module.check_elevation_mismatch(os.getpid())
    assert mismatch_self is False
    assert reason_self is None
    assert isinstance(app_module.is_current_process_elevated(), (bool, type(None)))


def test_focus_antigravity_discovers_standalone_app_and_preserves_window_state(monkeypatch):
    """
    Verify _focus_antigravity discovers standalone Antigravity.exe when Antigravity IDE.exe
    is not running, prefers last_app_hwnd, and only calls ShowWindow(SW_RESTORE) if minimized.
    """
    monkeypatch.delenv("ANTIGRAVITY_TARGET_APP", raising=False)
    monkeypatch.setattr(app_module, "attach_to_default_desktop", lambda: None)
    monkeypatch.setattr(app_module, "is_foreground_window", lambda hwnd: False)

    show_window_calls = []
    set_fg_calls = []

    class FakeFocusUser32:
        def IsWindowVisible(self, hwnd):
            return True
        def IsIconic(self, hwnd):
            return hwnd == 2002  # 2002 is minimized, 1001 is visible/snapped
        def GetWindowThreadProcessId(self, hwnd, pid_ptr):
            if pid_ptr is not None:
                pid_ptr._obj.value = 48220
            return 777
        def GetWindowRect(self, hwnd, rect_ptr):
            r = rect_ptr._obj
            r.left, r.top, r.right, r.bottom = 0, 0, 1920, 2070
            return 1
        def GetWindowTextW(self, hwnd, buf, sz):
            buf.value = "Voice Command Wake-Up Issue"
            return len(buf.value)
        def GetClassNameW(self, hwnd, buf, sz):
            buf.value = "Chrome_WidgetWin_1"
            return len(buf.value)
        def OpenDesktopW(self, *args):
            return 0
        def EnumWindows(self, cb, lparam):
            cb(1001, 0)
            cb(2002, 0)
            return 1
        def keybd_event(self, *args):
            pass
        def GetForegroundWindow(self):
            return 9999
        def AttachThreadInput(self, *args):
            return 1
        def ShowWindow(self, hwnd, cmd):
            show_window_calls.append((hwnd, cmd))
            return 1
        def SetForegroundWindow(self, hwnd):
            set_fg_calls.append(hwnd)
            return 1
        def BringWindowToTop(self, hwnd):
            return 1

    class FakeFocusKernel32:
        def OpenProcess(self, access, inherit, pid):
            return 555
        def QueryFullProcessImageNameW(self, hproc, flags, buf, sz_ptr):
            buf.value = r"C:\Users\dev\AppData\Local\Programs\antigravity\Antigravity.exe"
            return 1
        def CloseHandle(self, h):
            return 1
        def GetCurrentThreadId(self):
            return 111

    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(user32=FakeFocusUser32(), kernel32=FakeFocusKernel32()),
        WINFUNCTYPE=lambda *args: (lambda fn: fn),
        create_unicode_buffer=_real_ctypes.create_unicode_buffer,
        byref=_real_ctypes.byref,
        c_bool=_real_ctypes.c_bool,
    )
    monkeypatch.setattr(app_module, "ctypes", fake_ctypes)

    # 1. Non-minimized window (1001) selected via last_app_hwnd -> must NOT call ShowWindow(SW_RESTORE)
    dummy = SimpleNamespace(last_app_hwnd=1001)
    hwnd, rect = AntiTrayApp._focus_antigravity(dummy)
    assert hwnd == 1001
    assert dummy._focused_is_ide is False
    assert dummy._focused_pid == 48220
    assert set_fg_calls == [1001]
    assert show_window_calls == []

    # 2. Minimized window (2002) selected via last_app_hwnd -> MUST call ShowWindow(2002, 9)
    dummy2 = SimpleNamespace(last_app_hwnd=2002)
    hwnd2, _ = AntiTrayApp._focus_antigravity(dummy2)
    assert hwnd2 == 2002
    assert show_window_calls == [(2002, 9)]

def test_standalone_app_click_scales_with_high_dpi(monkeypatch):
    """Verify standalone Antigravity chat input click scales vertical offset by window DPI."""
    app, user32 = _patch_win32(monkeypatch, (3473746, app_module.wintypes.RECT(0, 0, 1920, 2070)), [True, True])
    app._focused_is_ide = False

    cursor_positions = []
    user32.SetCursorPos = lambda x, y: cursor_positions.append((x, y))
    user32.GetDpiForWindow = lambda hwnd: 216  # 225% scaling (2.25x)

    assert AntiTrayApp.submit_to_antigravity_chat(app, "Anti, test high dpi", press_enter=False) is True
    assert len(cursor_positions) == 2  # first click target, second restore original cursor
    click_x, click_y = cursor_positions[0]
    assert click_x == int(1920 * 0.28)
    assert click_y == 2070 - int(82 * 2.25)
