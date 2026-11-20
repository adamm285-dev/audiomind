"""
AudioMind Desktop Waveform HUD (Heads-Up Display).
A minimalist, ultra-compact floating micro-capsule pill widget that animates live 
audio waveforms when listening, thinking, speaking, or paused.
Positioned discreetly above the Windows taskbar and system tray clock.
"""
import math
import os
import sys
import time
import threading
import tkinter as tk
import ctypes
from ctypes import wintypes

def attach_to_default_desktop():
    """Ensure the calling thread is attached to the user's interactive 'Default' desktop on Windows."""
    if sys.platform != "win32":
        return
    try:
        u = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        h_desk = u.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if h_desk:
            u.SetThreadDesktop(h_desk)
    except Exception:
        pass

def get_primary_work_area():
    """Returns (left, top, right, bottom) of the primary display work area excluding taskbar/dock."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            rect = wintypes.RECT()
            if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
        return (0, 0, 1920, 1040)
    try:
        tmp = tk._default_root
        if tmp:
            return (0, 25, tmp.winfo_screenwidth(), tmp.winfo_screenheight() - 60)
    except Exception:
        pass
    return (0, 25, 1440, 840)

THEME_PALETTES = {
    "cyberpunk": {
        "listening": {"glow": "#00e5ff", "bar1": "#00e5ff", "bar2": "#7c4dff", "dot": "#00e676"},
        "speaking":  {"glow": "#7c4dff", "bar1": "#7c4dff", "bar2": "#00e5ff", "dot": "#00e5ff"},
    },
    "matrix": {
        "listening": {"glow": "#00ff66", "bar1": "#00ff66", "bar2": "#00cc44", "dot": "#00ffcc"},
        "speaking":  {"glow": "#39ff14", "bar1": "#39ff14", "bar2": "#76ff03", "dot": "#00ff66"},
    },
    "sunset": {
        "listening": {"glow": "#ff9100", "bar1": "#ffb300", "bar2": "#ff9100", "dot": "#ffd600"},
        "speaking":  {"glow": "#ff3d00", "bar1": "#ff3d00", "bar2": "#ff9100", "dot": "#ffab00"},
    },
    "violet": {
        "listening": {"glow": "#b388ff", "bar1": "#7c4dff", "bar2": "#b388ff", "dot": "#e040fb"},
        "speaking":  {"glow": "#e040fb", "bar1": "#e040fb", "bar2": "#00e5ff", "dot": "#00e5ff"},
    },
    "ice": {
        "listening": {"glow": "#38bdf8", "bar1": "#7dd3fc", "bar2": "#ffffff", "dot": "#38bdf8"},
        "speaking":  {"glow": "#38bdf8", "bar1": "#ffffff", "bar2": "#38bdf8", "dot": "#38bdf8"},
    },
    "seiko": {
        "listening": {"glow": "#f59e0b", "bar1": "#fde68a", "bar2": "#f59e0b", "dot": "#fbbf24"},
        "speaking":  {"glow": "#fbbf24", "bar1": "#fef3c7", "bar2": "#d97706", "dot": "#f59e0b"},
    },
}

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"

def _interpolate_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex color codes."""
    try:
        r1, g1, b1 = _hex_to_rgb(c1)
        r2, g2, b2 = _hex_to_rgb(c2)
        t = max(0.0, min(1.0, t))
        r = r1 + (r2 - r1) * t
        g = g1 + (g2 - g1) * t
        b = b1 + (b2 - b1) * t
        return _rgb_to_hex(r, g, b)
    except Exception:
        return c1 if t < 0.5 else c2

class WaveformHud:
    def __init__(self, position="bottom_right", theme="seiko", width=480):
        self.root = None
        self.canvas = None
        self.is_running = False
        self.visible = False
        self.state = "idle"  # "idle", "listening", "processing", "speaking", "paused"
        self.status_text = "AudioMind"
        self.subtitle_text = ""
        self.audio_level = 0.0
        self.phase = 0.0
        self.position = position  # "bottom_right" or "bottom_center"
        self.theme = theme if theme in THEME_PALETTES else "cyberpunk"
        self.num_bars = 10
        self.bars = [3.5] * 10
        self._was_visible = False
        self.on_click = None
        self.on_right_click = None
        self.on_double_click = None
        self.on_prev_chapter = None
        self.on_rewind_5 = None
        self.on_play_pause = None
        self.on_forward_5 = None
        self.on_next_chapter = None
        self.on_skip_output = None
        self.is_hovered = False
        self.hovered_button = None
        self._hover_hint = None
        self.width = 480
        self.height = 38
        self._thread = None
        self._lock = threading.Lock()

        # Free draggability & custom position caching
        self.custom_x = None
        self.custom_y = None
        self._current_x = 0
        self._current_y = 0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0
        self._drag_has_moved = False
        self._drag_press_event = None

        # Collapse, Locate & Expand callbacks
        self.on_collapse = None
        self.on_locate = None
        self.on_expand_toggle = None
        self.on_speed_cycle = None
        self.playback_progress = 0.0

        # Expanded Winamp-style Reader Deck & Scale state
        self.expanded = False
        self.ui_scale = 1.0
        self.skin_finish = "titanium"  # "dark", "stainless", "titanium"
        self.compact_width = width
        self.expanded_width = 800
        self.expanded_height = 360
        self._skin_cache = {}
        self._skin_cache_dirty = False
        self.live_phrase = ""
        self.live_context_before = ""
        self.live_context_after = ""
        self.chapter_label = ""
        self.time_elapsed_sec = 0.0
        self.time_total_sec = 0.0
        self.queue_count = 0
        self.speed_label = "1.0x"

        # Tactile button pressing & high-priority action flash feedback
        self.pressed_button = None
        self._action_toast = None
        self._action_toast_until = 0.0

    def set_progress(self, progress: float):
        """Updates normalized playback progress (0.0 to 1.0) for the HUD progress bar."""
        with self._lock:
            self.playback_progress = max(0.0, min(1.0, float(progress)))

    def set_live_text(self, phrase: str = "", context_before: str = "", context_after: str = "", chapter_label: str = ""):
        """Update the live spoken phrase and surrounding context for the expanded Winamp reader."""
        with self._lock:
            self.live_phrase = phrase or ""
            self.live_context_before = context_before or ""
            self.live_context_after = context_after or ""
            if chapter_label:
                self.chapter_label = chapter_label

    def set_playback_meta(self, elapsed_sec: float = 0.0, total_sec: float = 0.0, queue_count: int = 0, speed_label: str = "1.0x"):
        """Update digital time counter, queue depth, and speed badge for the expanded Winamp deck."""
        with self._lock:
            self.time_elapsed_sec = max(0.0, float(elapsed_sec or 0.0))
            self.time_total_sec = max(0.0, float(total_sec or 0.0))
            self.queue_count = max(0, int(queue_count or 0))
            self.speed_label = speed_label or "1.0x"

    def set_expanded(self, expanded: bool):
        """Switch between the compact HUD and the expanded Winamp-style reader deck."""
        with self._lock:
            self.expanded = bool(expanded)
        if self.root:
            self.root.after(0, self._check_expansion)
        else:
            self._check_expansion()

    def set_scale(self, scale: float):
        """Set uniform HUD scale factor (e.g. 0.75, 1.0, 1.25, 1.5) for both compact and expanded modes."""
        with self._lock:
            self.ui_scale = max(0.6, min(2.0, float(scale)))
            self._skin_cache_dirty = True
        if self.root:
            try:
                self.root.after(0, self._check_expansion)
            except Exception:
                pass
        else:
            self._check_expansion()

    def set_skin_finish(self, finish: str):
        """Set the car-deck faceplate finish ('dark', 'stainless', 'titanium')."""
        if finish not in ("dark", "stainless", "titanium"):
            return
        with self._lock:
            self.skin_finish = finish
            self._skin_cache_dirty = True

    def _skin_filename(self, kind: str) -> str:
        """Resolve skin PNG filename for 'expanded', 'mini', or 'pill' and active skin_finish."""
        finish = getattr(self, "skin_finish", "dark")
        if kind == "expanded":
            return "winamp_car_deck_dark.png" if finish == "dark" else f"winamp_car_deck_{finish}.png"
        if kind == "mini":
            return "winamp_car_deck_mini.png" if finish == "dark" else f"winamp_car_deck_mini_{finish}.png"
        return "winamp_car_deck_pill.png" if finish == "dark" else f"winamp_car_deck_pill_{finish}.png"

    def _active_mode(self) -> str:
        """Return 'expanded', 'dock', or 'pill' independent of ui_scale."""
        if self.expanded:
            return "expanded"
        s = self.ui_scale or 1.0
        if self.is_hovered or self.state in ("speaking", "paused") or self.height >= int(round(60 * s)):
            return "dock"
        return "pill"

    def toggle_expand(self):
        """Toggle between compact HUD mode and expanded Winamp-style reader mode."""
        self.set_expanded(not self.expanded)
        if self.on_expand_toggle:
            try:
                self.on_expand_toggle(self.expanded)
            except Exception:
                pass

    def flash_action(self, toast_text: str, duration_sec: float = 1.4):
        """Display an immediate high-priority action confirmation toast on the LCD, superseding hover hints."""
        with self._lock:
            self._action_toast = toast_text
            self._action_toast_until = time.time() + duration_sec

    def set_theme(self, theme: str):
        """Set active color theme for the HUD ('cyberpunk', 'matrix', 'sunset', 'violet', 'ice')."""
        with self._lock:
            if theme in THEME_PALETTES:
                self.theme = theme

    def start(self):
        """Start the Tkinter UI event loop in a dedicated background thread."""
        self._thread = threading.Thread(target=self._run_ui, daemon=True)
        self._thread.start()

    def _run_ui(self):
        attach_to_default_desktop()
        self.root = tk.Tk()
        self.root.title("AudioMind Voice HUD")
        self.root.overrideredirect(True)  # Frameless
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)  # Start hidden

        # Configure transparent-capable canvas
        try:
            self.root.wm_attributes("-transparentcolor", "#010409")
            self.root.configure(bg="#010409")
        except Exception:
            self.root.configure(bg="#0c0e14")

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg="#010409", highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)

        # Mouse press, drag motion, and release for fluid draggability without click collision
        self.canvas.bind("<ButtonPress-1>", self._on_button_press)
        self.root.bind("<ButtonPress-1>", self._on_button_press)
        self.canvas.bind("<B1-Motion>", self._on_b1_motion)
        self.root.bind("<B1-Motion>", self._on_b1_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_release)
        self.root.bind("<ButtonRelease-1>", self._on_button_release)

        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.root.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.root.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<Enter>", self._on_mouse_enter)
        self.root.bind("<Enter>", self._on_mouse_enter)
        self.canvas.bind("<Leave>", self._on_mouse_leave)
        self.root.bind("<Leave>", self._on_mouse_leave)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.root.bind("<Motion>", self._on_mouse_move)

        self._update_geometry()

        self.is_running = True
        self._animate()
        self.root.mainloop()

    def _get_button_defs(self, w=None):
        """Returns unscaled base button definitions [(id, icon, bx1, bx2), ...] for dock or expanded deck."""
        mode = self._active_mode()
        if mode == "expanded":
            # Exact pixel-aligned coordinates for the 6 sculpted hardware buttons in winamp_car_deck_dark.png (800x360)
            return [
                ("prev", "⏮", 58, 117),
                ("rewind", "⏪ 5s", 129, 188),
                ("play_pause", "▶" if self.state == "paused" else "⏸", 200, 259),
                ("forward", "⏩ 5s", 271, 330),
                ("next", "⏭", 342, 401),
                ("skip", "⏹", 413, 472),
            ]
        # Exact pixel-aligned coordinates for the 6 wide sculpted hardware buttons in winamp_car_deck_mini.png (480x84)
        return [
            ("prev", "⏮", 23, 66),
            ("rewind", "⏪5s", 77, 119),
            ("play_pause", "▶" if self.state == "paused" else "⏸", 129, 171),
            ("forward", "⏩5s", 182, 224),
            ("next", "⏭", 235, 277),
            ("skip", "⏹", 289, 332),
        ]

    def _top_btn_y_bounds(self):
        """Return unscaled (y1, y2) hit-test bounds for top-right utility buttons."""
        mode = self._active_mode()
        if mode == "expanded":
            return 12, 38
        if mode == "dock":
            return 15, 35
        return 9, 29

    def _top_btn_x_bounds(self):
        """Return unscaled ((exp_x1, exp_x2), (loc_x1, loc_x2), (col_x1, col_x2)) for top-right buttons."""
        mode = self._active_mode()
        if mode == "expanded":
            w = self.expanded_width
            return (w - 162, w - 134), (w - 130, w - 102), (w - 98, w - 70)
        w = self.compact_width
        return (w - 82, w - 62), (w - 58, w - 38), (w - 34, w - 14)

    def _hit_test_collapse(self, x, y):
        """Hit-test (x, y) coordinates against the top-right collapse button."""
        s = self.ui_scale or 1.0
        ux, uy = x / s, y / s
        y1, y2 = self._top_btn_y_bounds()
        _, _, (cx1, cx2) = self._top_btn_x_bounds()
        return (cx1 - 2 <= ux <= cx2 + 2) and (y1 - 2 <= uy <= y2 + 2)

    def _hit_test_locate(self, x, y):
        """Hit-test (x, y) coordinates against the top-right Locate-in-Chat target button."""
        s = self.ui_scale or 1.0
        ux, uy = x / s, y / s
        y1, y2 = self._top_btn_y_bounds()
        _, (lx1, lx2), _ = self._top_btn_x_bounds()
        return (lx1 - 2 <= ux <= lx2 + 2) and (y1 - 2 <= uy <= y2 + 2)

    def _hit_test_expand(self, x, y):
        """Hit-test (x, y) coordinates against the top-right Expand/Minimize button or dock pill."""
        s = self.ui_scale or 1.0
        ux, uy = x / s, y / s
        if self._active_mode() == "dock" and (359 <= ux <= 445) and (50 <= uy <= 76):
            return True
        y1, y2 = self._top_btn_y_bounds()
        (ex1, ex2), _, _ = self._top_btn_x_bounds()
        return (ex1 - 2 <= ux <= ex2 + 2) and (y1 - 2 <= uy <= y2 + 2)

    def _hit_test_speed(self, x, y):
        """Hit-test (x, y) coordinates against the expanded deck speed pill button."""
        if self._active_mode() != "expanded":
            return False
        s = self.ui_scale or 1.0
        ux, uy = x / s, y / s
        return (572 <= ux <= 742) and (292 <= uy <= 330)

    def _hit_test_button(self, x, y):
        """Hit-test (x, y) coordinates against CD-player transport buttons."""
        mode = self._active_mode()
        if mode == "pill":
            return None
        s = self.ui_scale or 1.0
        ux, uy = x / s, y / s
        y1, y2 = (292, 330) if mode == "expanded" else (50, 76)
        if not (y1 <= uy <= y2):
            return None
        for btn_id, _, bx1, bx2 in self._get_button_defs():
            if bx1 <= ux <= bx2:
                return btn_id
        return None

    def _on_button_press(self, event=None):
        if event:
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            self._drag_has_moved = False
            self._drag_press_event = event
            self._drag_start_win_x = self.custom_x if self.custom_x is not None else self._current_x
            self._drag_start_win_y = self.custom_y if self.custom_y is not None else self._current_y
            if self._hit_test_collapse(event.x, event.y):
                self.pressed_button = "collapse"
            elif self._hit_test_locate(event.x, event.y):
                self.pressed_button = "locate"
            elif self._hit_test_expand(event.x, event.y):
                self.pressed_button = "expand"
            elif self._hit_test_speed(event.x, event.y):
                self.pressed_button = "speed"
            elif self._active_mode() != "pill":
                self.pressed_button = self._hit_test_button(event.x, event.y)
            else:
                self.pressed_button = None

    def _on_b1_motion(self, event=None):
        if not event or not self.root:
            return
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_has_moved = True
            self.pressed_button = None
            left, top, right, bottom = get_primary_work_area()
            target_x = self._drag_start_win_x + dx
            target_y = self._drag_start_win_y + dy
            # Clamp within work area bounds so HUD stays fully visible
            target_x = max(left, min(right - self.width, target_x))
            target_y = max(top, min(bottom - self.height, target_y))
            self.custom_x = target_x
            self.custom_y = target_y
            self._current_x = target_x
            self._current_y = target_y
            try:
                self.root.geometry(f"{self.width}x{self.height}+{target_x}+{target_y}")
                if sys.platform == "win32":
                    hwnd = int(self.root.wm_frame(), 16)
                    user32 = ctypes.windll.user32
                    SWP_NOACTIVATE = 0x0010
                    SWP_SHOWWINDOW = 0x0040
                    HWND_TOPMOST = -1
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, target_x, target_y, self.width, self.height, SWP_NOACTIVATE | SWP_SHOWWINDOW)
            except Exception:
                pass

    def _on_button_release(self, event=None):
        self.pressed_button = None
        if self._drag_has_moved:
            self._drag_has_moved = False
            return "break"
        evt = self._drag_press_event or event
        return self._on_canvas_click(evt)

    def _on_canvas_click(self, event=None):
        """Invoke button transport callback, collapse callback, or general on_click (play/pause toggle)."""
        if event:
            if self._hit_test_collapse(event.x, event.y):
                if self.on_collapse:
                    try:
                        self.on_collapse()
                    except Exception:
                        pass
                else:
                    self.hide()
                return "break"

            if self._hit_test_locate(event.x, event.y):
                if self.on_locate:
                    try:
                        self.on_locate()
                    except Exception:
                        pass
                return "break"

            if self._hit_test_expand(event.x, event.y):
                self.toggle_expand()
                return "break"

            if self._hit_test_speed(event.x, event.y):
                if self.on_speed_cycle:
                    try:
                        self.on_speed_cycle()
                    except Exception:
                        pass
                return "break"

            if self._active_mode() != "pill":
                btn = self._hit_test_button(event.x, event.y)
                if btn == "prev":
                    if self.on_prev_chapter:
                        try:
                            self.on_prev_chapter()
                        except Exception:
                            pass
                    elif self.on_click:
                        try:
                            self.on_click()
                        except Exception:
                            pass
                    return "break"
                elif btn == "rewind":
                    if self.on_rewind_5:
                        try:
                            self.on_rewind_5()
                        except Exception:
                            pass
                    return "break"
                elif btn == "play_pause":
                    if self.on_play_pause:
                        try:
                            self.on_play_pause()
                        except Exception:
                            pass
                    elif self.on_click:
                        try:
                            self.on_click()
                        except Exception:
                            pass
                    return "break"
                elif btn == "forward":
                    if self.on_forward_5:
                        try:
                            self.on_forward_5()
                        except Exception:
                            pass
                    return "break"
                elif btn == "next":
                    if self.on_next_chapter:
                        try:
                            self.on_next_chapter()
                        except Exception:
                            pass
                    return "break"
                elif btn == "skip":
                    if self.on_skip_output:
                        try:
                            self.on_skip_output()
                        except Exception:
                            pass
                    elif self.on_double_click:
                        try:
                            self.on_double_click()
                        except Exception:
                            pass
                    return "break"

        # General click on top row / background or compact mode
        if self.on_click:
            try:
                self.on_click()
            except Exception:
                pass
        return "break"

    def _on_canvas_right_click(self, event=None):
        """Invoke on_right_click callback (e.g. skip output) when user right-clicks floating HUD."""
        if self.on_right_click:
            try:
                self.on_right_click()
            except Exception:
                pass
        return "break"

    def _on_canvas_double_click(self, event=None):
        """Invoke on_double_click callback (e.g. skip output) when user double-clicks floating HUD."""
        if self.on_double_click:
            try:
                self.on_double_click()
            except Exception:
                pass
        elif self.on_right_click:
            try:
                self.on_right_click()
            except Exception:
                pass
        return "break"

    def _on_mouse_enter(self, event=None):
        self.is_hovered = True
        self._check_expansion()

    def _on_mouse_leave(self, event=None):
        self.is_hovered = False
        self.hovered_button = None
        self._hover_hint = None
        self._check_expansion()

    def _on_mouse_move(self, event=None):
        if not event:
            return
        if self._hit_test_collapse(event.x, event.y):
            if self.hovered_button != "collapse":
                self.hovered_button = "collapse"
                self._hover_hint = "▼  COLLAPSE TO TRAY"
            return

        if self._hit_test_locate(event.x, event.y):
            if self.hovered_button != "locate":
                self.hovered_button = "locate"
                mod = "Cmd+Opt" if sys.platform == "darwin" else "Ctrl+Alt"
                self._hover_hint = f"🎯  FIND PHRASE IN CHAT ({mod}+F)"
            return

        if self._hit_test_expand(event.x, event.y):
            if self.hovered_button != "expand":
                self.hovered_button = "expand"
                self._hover_hint = "🗕  MINIMIZE TO COMPACT HUD" if self.expanded else "⤢  EXPAND WINAMP READER"
            return

        if self._hit_test_speed(event.x, event.y):
            if self.hovered_button != "speed":
                self.hovered_button = "speed"
                self._hover_hint = "⚡  CYCLE SPEECH SPEED"
            return

        if self._active_mode() == "pill":
            if self.hovered_button:
                self.hovered_button = None
                self._hover_hint = None
            return

        btn = self._hit_test_button(event.x, event.y)
        if btn != self.hovered_button:
            self.hovered_button = btn
            if btn:
                hints = {
                    "prev": "⏮  REPEAT / PREV CHAPTER",
                    "rewind": "⏪  REWIND 5 SECONDS",
                    "play_pause": "▶  RESUME SPEECH" if self.state == "paused" else "⏸  PAUSE SPEECH",
                    "forward": "⏩  FORWARD 5 SECONDS",
                    "next": "⏭  NEXT CHAPTER",
                    "skip": "⏹  SKIP CURRENT OUTPUT",
                }
                self._hover_hint = hints.get(btn)
            else:
                self._hover_hint = None

    def _check_expansion(self):
        """Resize HUD between compact pill (38px), compact dock (84px), and expanded Winamp deck (360px), scaled by ui_scale."""
        s = self.ui_scale or 1.0
        if self.expanded:
            base_w, base_h = self.expanded_width, self.expanded_height
        elif self.is_hovered or (self.state in ("speaking", "paused")):
            base_w, base_h = self.compact_width, 84
        else:
            base_w, base_h = self.compact_width, 38
        target_w = int(round(base_w * s))
        target_h = int(round(base_h * s))
        if self.width != target_w or self.height != target_h:
            self.width = target_w
            self.height = target_h
            if self.canvas:
                try:
                    self.canvas.config(width=self.width, height=self.height)
                except Exception:
                    pass
            self._update_geometry()

    def _update_geometry(self):
        if not self.root:
            return

        left, top, right, bottom = get_primary_work_area()

        if self.custom_x is not None and self.custom_y is not None:
            x = self.custom_x
            y = self.custom_y
            x = max(left, min(right - self.width, x))
            y = max(top, min(bottom - self.height, y))
        elif self.position == "bottom_center":
            x = left + ((right - left) - self.width) // 2
            y = bottom - self.height - 12
        else:  # "bottom_right" (above system tray clock)
            x = right - self.width - 20
            y = bottom - self.height - 12

        self._current_x = x
        self._current_y = y
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Position precisely via Win32 without stealing focus
        if sys.platform == "win32":
            try:
                hwnd = int(self.root.wm_frame(), 16)
                user32 = ctypes.windll.user32
                # WS_EX_TOOLWINDOW = 0x0080, WS_EX_NOACTIVATE = 0x08000000
                ex_style = user32.GetWindowLongW(hwnd, -20)
                user32.SetWindowLongW(hwnd, -20, ex_style | 0x0080 | 0x08000000)
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                HWND_TOPMOST = -1
                user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, self.width, self.height, SWP_NOACTIVATE | SWP_SHOWWINDOW)
            except Exception:
                pass

    def reset_position(self):
        """Reset custom drag position and snap back to default screen corner."""
        with self._lock:
            self.custom_x = None
            self.custom_y = None
        if self.root:
            self.root.after(0, self._update_geometry)

    def collapse(self):
        """Collapse and hide HUD directly to tray."""
        if self.on_collapse:
            try:
                self.on_collapse()
            except Exception:
                pass
        else:
            self.hide()

    def format_lcd_label(self, label: str, default_status: str = "Ready") -> str:
        """
        Formats LCD display text to cleanly present [Chat Tag] • Status or App name.
        Avoids stripping status text while preventing horizontal overflow.
        """
        if not label:
            return default_status

        for prefix in ("AudioMind • ", "AudioMind: ", "Anti • ", "Anti: "):
            if label.startswith(prefix):
                label = label[len(prefix):].strip()

        if label in ("AudioMind", "AudioMind is online", "Anti", "Anti is online", ""):
            return default_status

        if label.startswith("[") and "]" in label:
            end_b = label.find("]")
            tag_part = label[:end_b + 1].strip()
            rest = label[end_b + 1:].strip()
            if rest:
                if rest.startswith("• "):
                    rest = rest[2:].strip()
                label = f"{tag_part} • {rest}"
            else:
                label = f"{tag_part} • {default_status}"

        if len(label) > 42:
            label = label[:41] + "…"
        return label

    def set_position(self, pos: str):
        """Toggle position between 'bottom_right' and 'bottom_center'."""
        with self._lock:
            self.position = pos
        if self.root:
            self.root.after(0, self._update_geometry)

    def _bring_to_front(self):
        """Physically lift the borderless HUD to the topmost Z-order over full-screen apps."""
        try:
            if self.root:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                if sys.platform == "win32":
                    hwnd = int(self.root.wm_frame(), 16)
                    user32 = ctypes.windll.user32
                    SWP_NOACTIVATE = 0x0010
                    SWP_SHOWWINDOW = 0x0040
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    HWND_TOPMOST = -1
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def show(self, state="listening", status="Listening...", subtitle=""):
        """Show the HUD with smooth alpha transition and ensure topmost visibility."""
        with self._lock:
            self.state = state
            self.status_text = status
            self.subtitle_text = subtitle
            self.visible = True
        if self.root:
            self.root.after(0, self._bring_to_front)

    def hide(self):
        """Fade out and hide the HUD."""
        with self._lock:
            self.visible = False

    def update_audio_level(self, level: float):
        """Update live audio volume level (0.0 to 1.0) for wave animation."""
        with self._lock:
            self.audio_level = max(0.0, min(1.0, level))

    def set_status(self, status: str, subtitle: str = "", state: str = None):
        """Update HUD display text and state, automatically revealing when active."""
        should_bring_front = False
        with self._lock:
            self.status_text = status
            self.subtitle_text = subtitle
            if state:
                self.state = state
                if state in ("speaking", "listening", "processing", "thinking"):
                    if not self.visible:
                        self.visible = True
                        should_bring_front = True
        if should_bring_front and self.root:
            self.root.after(0, self._bring_to_front)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, fill, outline, width=1):
        """Draw a smooth rounded rectangle with corner radius r."""
        self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline=outline, width=width)
        self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline=outline, width=width)
        self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=fill, outline=outline, width=width)
        self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=fill, outline=outline, width=width)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
        if outline:
            self.canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width)
            self.canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width)
            self.canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width)
            self.canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width)

    def _animate(self):
        if not self.is_running or not self.root:
            return

        self._check_expansion()

        # Smooth alpha fade transition
        curr_alpha = float(self.root.attributes("-alpha"))
        target_alpha = 0.95 if self.visible else 0.0
        if abs(curr_alpha - target_alpha) > 0.02:
            step = 0.20 if target_alpha > curr_alpha else -0.20
            new_alpha = max(0.0, min(0.95, curr_alpha + step))
            self.root.attributes("-alpha", new_alpha)

        # Ensure topmost stays active when entering visible state
        if self.visible:
            if not self._was_visible:
                self._was_visible = True
                self._bring_to_front()
        else:
            self._was_visible = False

        # Only draw if visible or in fade transition
        if curr_alpha > 0.01 or self.visible:
            self._draw_frame()

        self.phase += 0.16
        self.root.after(28, self._animate)

    def _draw_outlined_text(self, x: float, y: float, text: str, fill: str, outline_fill: str, font, anchor: str = "w"):
        """Draw crisp text with a 1px dark outline for high contrast over metallic faceplates."""
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.canvas.create_text(x + dx, y + dy, text=text, fill=outline_fill, font=font, anchor=anchor)
        return self.canvas.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor)

    def _draw_top_right_buttons(self, w: int, y1: int, y2: int, glow_color: str):
        """Draws Expand/Minimize [⤢/🗕], Locate-in-Chat [⌖], and Collapse-to-Tray [▼] buttons (scaled by ui_scale)."""
        s = self.ui_scale or 1.0
        (ex1, ex2), (lx1, lx2), (cx1, cx2) = self._top_btn_x_bounds()
        exp_x1, exp_x2 = ex1 * s, ex2 * s
        loc_x1, loc_x2 = lx1 * s, lx2 * s
        col_x1, col_x2 = cx1 * s, cx2 * s
        sy1, sy2 = y1 * s, y2 * s
        is_exp_mode = (self._active_mode() == "expanded")
        is_light_metal = getattr(self, "skin_finish", "dark") in ("stainless", "titanium")
        f_sz = -max(9, int(round((14 if is_exp_mode else 10) * s)))
        loc_sz = -max(10, int(round((15 if is_exp_mode else 11) * s)))

        if is_exp_mode:
            # Expanded skin has sculpted 3D hardware pads baked into the titlebar; draw crisp icon + hover/press rim only
            base_ink = "#0f172a" if is_light_metal else "#f1f5f9"
            hover_ink = "#1d4ed8" if is_light_metal else glow_color
            btn_specs = [
                ("expand", exp_x1, exp_x2, "🗕" if self.expanded else "⤢", f_sz),
                ("locate", loc_x1, loc_x2, "⌖", loc_sz),
                ("collapse", col_x1, col_x2, "▼", f_sz),
            ]
            for bid, bx1, bx2, glyph, g_sz in btn_specs:
                is_hov = (self.hovered_button == bid)
                is_prs = (self.pressed_button == bid)
                cy_b = (sy1 + sy2) / 2 + (1 if is_prs else 0)
                if is_prs:
                    self._draw_rounded_rect(bx1, sy1, bx2, sy2, 4, fill="", outline="#ffffff", width=1)
                    ink = "#ffffff" if not is_light_metal else "#fef3c7"
                elif is_hov:
                    self._draw_rounded_rect(bx1, sy1, bx2, sy2, 4, fill="", outline=hover_ink, width=1)
                    ink = hover_ink
                else:
                    ink = "#fef3c7" if getattr(self, "skin_finish", "dark") == "titanium" else ("#f8fafc" if is_light_metal else base_ink)
                if is_light_metal:
                    self._draw_outlined_text((bx1 + bx2) / 2, cy_b, glyph, fill=ink, outline_fill="#090d14", font=("Segoe UI Symbol", g_sz, "bold"), anchor="center")
                else:
                    self.canvas.create_text((bx1 + bx2) / 2, cy_b, text=glyph, fill=ink, font=("Segoe UI Symbol", g_sz, "bold"))
            return

        # Expand / Minimize button [⤢] or [🗕]
        exp_hover = (self.hovered_button == "expand")
        exp_pressed = (self.pressed_button == "expand")
        if exp_pressed:
            exp_bg, exp_border, exp_txt, exp_cy = "#2f415c", "#ffffff", "#ffffff", (sy1 + sy2) / 2 + 1
        elif exp_hover:
            exp_bg, exp_border, exp_txt, exp_cy = "#222d3d", glow_color, glow_color, (sy1 + sy2) / 2
        elif self.expanded:
            exp_bg, exp_border, exp_txt, exp_cy = "#101824", glow_color, glow_color, (sy1 + sy2) / 2
        else:
            exp_bg, exp_border, exp_txt, exp_cy = "#0d131d", "#212b3d", "#8b949e", (sy1 + sy2) / 2
        self._draw_rounded_rect(exp_x1, sy1, exp_x2, sy2, 4, fill=exp_bg, outline=exp_border, width=1)
        exp_glyph = "🗕" if self.expanded else "⤢"
        self.canvas.create_text((exp_x1 + exp_x2) / 2, exp_cy, text=exp_glyph, fill=exp_txt, font=("Segoe UI Symbol", f_sz, "bold"))

        # Locate in Chat button [⌖]
        loc_hover = (self.hovered_button == "locate")
        loc_pressed = (self.pressed_button == "locate")
        if loc_pressed:
            loc_bg, loc_border, loc_txt, loc_cy = "#2f415c", "#ffffff", "#ffffff", (sy1 + sy2) / 2 + 1
        elif loc_hover:
            loc_bg, loc_border, loc_txt, loc_cy = "#222d3d", glow_color, glow_color, (sy1 + sy2) / 2
        elif self.state in ("speaking", "paused"):
            loc_bg, loc_border, loc_txt, loc_cy = "#101824", glow_color, glow_color, (sy1 + sy2) / 2
        else:
            loc_bg, loc_border, loc_txt, loc_cy = "#0d131d", "#212b3d", "#8b949e", (sy1 + sy2) / 2
        self._draw_rounded_rect(loc_x1, sy1, loc_x2, sy2, 4, fill=loc_bg, outline=loc_border, width=1)
        self.canvas.create_text((loc_x1 + loc_x2) / 2, loc_cy, text="⌖", fill=loc_txt, font=("Segoe UI Symbol", loc_sz, "bold"))

        # Collapse to Tray button [▼]
        col_hover = (self.hovered_button == "collapse")
        col_pressed = (self.pressed_button == "collapse")
        if col_pressed:
            col_bg, col_border, col_txt, col_cy = "#2f415c", "#ffffff", "#ffffff", (sy1 + sy2) / 2 + 1
        elif col_hover:
            col_bg, col_border, col_txt, col_cy = "#222d3d", glow_color, glow_color, (sy1 + sy2) / 2
        else:
            col_bg, col_border, col_txt, col_cy = "#0d131d", "#212b3d", "#8b949e", (sy1 + sy2) / 2
        self._draw_rounded_rect(col_x1, sy1, col_x2, sy2, 4, fill=col_bg, outline=col_border, width=1)
        self.canvas.create_text((col_x1 + col_x2) / 2, col_cy, text="▼", fill=col_txt, font=("Segoe UI Symbol", f_sz, "bold"))

    @staticmethod
    def _format_mmss(seconds: float) -> str:
        """Format seconds as M:SS for Winamp-style digital time counter."""
        total = max(0, int(seconds))
        mins, secs = divmod(total, 60)
        return f"{mins}:{secs:02d}"

    def _draw_seven_segment_text(self, x: float, cy: float, text: str, digit_h: float, on_color: str, off_color: str) -> float:
        """Draw '90s Seiko digital-watch 7-segment LCD characters ('0'-'9', ':', '/') and return ending x."""
        seg_map = {
            "0": (1, 1, 1, 1, 1, 1, 0),
            "1": (0, 1, 1, 0, 0, 0, 0),
            "2": (1, 1, 0, 1, 1, 0, 1),
            "3": (1, 1, 1, 1, 0, 0, 1),
            "4": (0, 1, 1, 0, 0, 1, 1),
            "5": (1, 0, 1, 1, 0, 1, 1),
            "6": (1, 0, 1, 1, 1, 1, 1),
            "7": (1, 1, 1, 0, 0, 0, 0),
            "8": (1, 1, 1, 1, 1, 1, 1),
            "9": (1, 1, 1, 1, 0, 1, 1),
        }
        dw = digit_h * 0.54
        half_h = digit_h / 2.0
        y_top = cy - half_h
        y_mid = cy
        y_bot = cy + half_h
        lw = max(1.8, digit_h * 0.13)
        pad = lw * 0.55
        cur_x = x

        for ch in text:
            if ch in seg_map:
                a, b, c, d, e, f, g = seg_map[ch]
                xL, xR = cur_x + pad, cur_x + dw - pad
                segs = [
                    (a, xL + pad * 0.4, y_top, xR - pad * 0.4, y_top),
                    (b, xR, y_top + pad * 0.4, xR, y_mid - pad * 0.4),
                    (c, xR, y_mid + pad * 0.4, xR, y_bot - pad * 0.4),
                    (d, xL + pad * 0.4, y_bot, xR - pad * 0.4, y_bot),
                    (e, xL, y_mid + pad * 0.4, xL, y_bot - pad * 0.4),
                    (f, xL, y_top + pad * 0.4, xL, y_mid - pad * 0.4),
                    (g, xL + pad * 0.4, y_mid, xR - pad * 0.4, y_mid),
                ]
                for on, x1, y1, x2, y2 in segs:
                    self.canvas.create_line(x1, y1, x2, y2, fill=(on_color if on else off_color), width=lw, capstyle="round")
                cur_x += dw + lw * 1.4
            elif ch == ":":
                dot_r = max(1.3, lw * 0.65)
                cx_dot = cur_x + dot_r + 1
                self.canvas.create_oval(cx_dot - dot_r, cy - half_h * 0.42 - dot_r, cx_dot + dot_r, cy - half_h * 0.42 + dot_r, fill=on_color, outline="")
                self.canvas.create_oval(cx_dot - dot_r, cy + half_h * 0.42 - dot_r, cx_dot + dot_r, cy + half_h * 0.42 + dot_r, fill=on_color, outline="")
                cur_x += dot_r * 2 + lw * 1.6
            elif ch == "/":
                self.canvas.create_line(cur_x + dw * 0.45, y_top + 1, cur_x + 2, y_bot - 1, fill=on_color, width=max(1.5, lw * 0.85), capstyle="round")
                cur_x += dw * 0.55 + lw
            elif ch == " ":
                cur_x += dw * 0.35
        return cur_x

    @staticmethod
    def _wrap_reader_segments(before: str, active: str, after: str, max_chars: int = 68, max_lines: int = 3) -> list[list[tuple[str, bool]]]:
        """
        Wrap (before, active, after) text into up to `max_lines` lines of `(token_str, is_active)` pairs
        so the active spoken phrase can be highlighted inline on the canvas.
        """
        tagged_words: list[tuple[str, bool]] = []
        for w in (before or "").split():
            tagged_words.append((w, False))
        for w in (active or "").split():
            tagged_words.append((w, True))
        for w in (after or "").split():
            tagged_words.append((w, False))

        if not tagged_words:
            return []

        lines: list[list[tuple[str, bool]]] = []
        cur_line: list[tuple[str, bool]] = []
        cur_len = 0

        for word, is_act in tagged_words:
            add_len = len(word) + (1 if cur_line else 0)
            if cur_line and cur_len + add_len > max_chars:
                lines.append(cur_line)
                if len(lines) >= max_lines:
                    # Append ellipsis to the last word of the final line if truncated
                    last_w, last_act = lines[-1][-1]
                    if not last_w.endswith("…"):
                        lines[-1][-1] = (last_w + "…", last_act)
                    return lines
                cur_line = [(word, is_act)]
                cur_len = len(word)
            else:
                cur_line.append((word, is_act))
                cur_len += add_len

        if cur_line and len(lines) < max_lines:
            lines.append(cur_line)
        return lines

    def _get_scaled_skin(self, filename: str, target_w: int, target_h: int):
        """Load and cache a car-deck skin PNG scaled to (target_w, target_h) on the Tkinter thread."""
        key = (filename, int(target_w), int(target_h))
        if key in self._skin_cache:
            return self._skin_cache[key]
        photo = None
        try:
            skin_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "resources", "skins", filename)
            )
            if os.path.exists(skin_path):
                from PIL import Image, ImageTk
                img = Image.open(skin_path).convert("RGBA")
                if img.size != (target_w, target_h):
                    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img, master=self.root)
        except Exception:
            try:
                if os.path.exists(skin_path) and self.root:
                    photo = tk.PhotoImage(file=skin_path, master=self.root)
            except Exception as exc:
                print(f"[!] Failed to load skin {filename}: {exc}")
                photo = None
        self._skin_cache[key] = photo
        return photo

    def _draw_expanded_deck(self, w: int, h: int, glow_color: str, bar_color1: str, bar_color2: str, dot_color: str, default_status: str):
        """Render the '90s dark gunmetal car-deck / Winamp faceplate skin (base 800x360) scaled by ui_scale."""
        s = self.ui_scale or 1.0
        sf = lambda px: -max(8, int(round(px * s)))
        now = time.time()
        with self._lock:
            toast_active = bool(self._action_toast and now < self._action_toast_until)
            toast_msg = self._action_toast if toast_active else None
            prog = self.playback_progress
            target_level = self.audio_level
            phrase = self.live_phrase
            ctx_before = self.live_context_before
            ctx_after = self.live_context_after
            ch_label = self.chapter_label
            elapsed_s = self.time_elapsed_sec
            total_s = self.time_total_sec
            q_cnt = self.queue_count
            spd_lbl = self.speed_label

        skin = self._get_scaled_skin(self._skin_filename("expanded"), w, h)
        is_light_metal = getattr(self, "skin_finish", "dark") in ("stainless", "titanium")
        if skin is not None:
            self.canvas.create_image(0, 0, anchor="nw", image=skin)
        else:
            self._draw_rounded_rect(1, 1, w - 1, h - 1, 12, fill="#1f2736", outline="#475569", width=1)
            self._draw_rounded_rect(94 * s, 60 * s, 706 * s, 155 * s, 8, fill="#0d2247", outline="#071124", width=2)
            self._draw_rounded_rect(64 * s, 180 * s, 736 * s, 245 * s, 8, fill="#070c14", outline="#334155", width=1)

        # 1. Recessed Titlebar Strip - larger outlined champagne/silver text + [Session] • Chapter + bbox() clipping
        self.canvas.create_oval(72 * s, 20 * s, 81 * s, 29 * s, fill=dot_color, outline="#090d14" if is_light_metal else "")
        finish = getattr(self, "skin_finish", "dark")
        brand_fg = "#fef3c7" if finish == "titanium" else ("#f8fafc" if finish == "stainless" else "#f1f5f9")
        if is_light_metal:
            brand_id = self._draw_outlined_text(90 * s, 25 * s, "AUDIOMIND", fill=brand_fg, outline_fill="#090d14", font=("Segoe UI", sf(16), "bold"), anchor="w")
        else:
            brand_id = self.canvas.create_text(90 * s, 25 * s, text="AUDIOMIND", fill=brand_fg, font=("Segoe UI", sf(16), "bold"), anchor="w")
        brand_bbox = self.canvas.bbox(brand_id)
        next_x = (brand_bbox[2] + 10 * s) if brand_bbox else 200 * s

        header_status = self.format_lcd_label(self.status_text, default_status)
        session_tag = ""
        if header_status.startswith("[") and "]" in header_status:
            end_b = header_status.find("]")
            session_tag = header_status[:end_b + 1].strip()
        if toast_msg:
            header_status = toast_msg
            hdr_color = "#fde68a" if is_light_metal else glow_color
        elif self._hover_hint:
            header_status = self._hover_hint
            hdr_color = "#fde68a" if is_light_metal else glow_color
        else:
            if session_tag and ch_label:
                header_status = f"{session_tag} • {ch_label}"
            elif ch_label:
                header_status = ch_label
            hdr_color = "#fef3c7" if finish == "titanium" else ("#f1f5f9" if finish == "stainless" else "#93c5fd")

        max_hdr_x = w - 172 * s
        hdr_font = ("Segoe UI", sf(15), "bold")
        # Measure & trim status cleanly before drawing final outlined text
        hdr_id = self.canvas.create_text(next_x, 25 * s, text=f"|  {header_status}", fill=hdr_color, font=hdr_font, anchor="w")
        hdr_bbox = self.canvas.bbox(hdr_id)
        while hdr_bbox and hdr_bbox[2] > max_hdr_x and len(header_status) > 8:
            header_status = header_status[:-4] + "…"
            self.canvas.itemconfig(hdr_id, text=f"|  {header_status}")
            hdr_bbox = self.canvas.bbox(hdr_id)
        if is_light_metal:
            self.canvas.delete(hdr_id)
            self._draw_outlined_text(next_x, 25 * s, f"|  {header_status}", fill=hdr_color, outline_fill="#090d14", font=hdr_font, anchor="w")
        self._draw_top_right_buttons(w, 15, 35, glow_color)

        # 2. Cobalt-Sapphire Glass LCD Bay
        play_glyph = "⏸" if self.state == "paused" else ("▶" if self.state == "speaking" else "●")
        glyph_color = "#fde047" if self.state == "paused" else ("#ffffff" if self.state == "speaking" else dot_color)
        self.canvas.create_text(112 * s, 90 * s, text=play_glyph, fill=glyph_color, font=("Segoe UI Symbol", sf(18), "bold"), anchor="w")

        time_str = f"{self._format_mmss(elapsed_s)} / {self._format_mmss(total_s)}" if total_s > 0 else self._format_mmss(elapsed_s)
        seg_on = "#fde68a" if self.theme == "seiko" else "#e0f7ff"
        time_end_x = self._draw_seven_segment_text(
            138 * s, 90 * s, time_str, digit_h=22 * s,
            on_color=seg_on, off_color="#0e2a5c",
        )
        badge_x = time_end_x + 14 * s

        # Only show PAUSED or Queue badge in LCD (avoid redundant SPEAKING badge next to timer)
        if self.state == "paused":
            badge_w = 68 * s
            if badge_x + badge_w < 495 * s:
                self._draw_rounded_rect(badge_x, 78 * s, badge_x + badge_w, 102 * s, 4, fill="#3b2c0a", outline="#facc15", width=1)
                self.canvas.create_text(badge_x + badge_w / 2, 90 * s, text="PAUSED", fill="#fde047", font=("Consolas", sf(13), "bold"))
                badge_x += badge_w + 8 * s

        if q_cnt > 0 and badge_x + 52 * s < 495 * s:
            self._draw_rounded_rect(badge_x, 78 * s, badge_x + 50 * s, 102 * s, 4, fill="#08142b", outline="#38bdf8", width=1)
            self.canvas.create_text(badge_x + 25 * s, 90 * s, text=f"Q:{q_cnt}", fill="#7dd3fc", font=("Consolas", sf(13), "bold"))

        # 14-Band Winamp Spectrum Analyzer
        num_bars = 14
        bar_w = 5.5 * s
        spacing = 7.0 * s
        total_bars_w = num_bars * bar_w + (num_bars - 1) * spacing
        spec_x0 = 685 * s - total_bars_w
        spec_y1, spec_y2 = 68 * s, 115 * s
        for gy in range(int(spec_y1 + 10 * s), int(spec_y2), max(4, int(10 * s))):
            self.canvas.create_line(spec_x0 - 4 * s, gy, 690 * s, gy, fill="#102954", width=1)
        for i in range(num_bars):
            t = i / max(1, num_bars - 1)
            dist = abs(i - (num_bars - 1) / 2) / ((num_bars - 1) / 2)
            bell = math.exp(-1.1 * (dist ** 2))
            if self.state == "speaking":
                freq_wave = math.sin(self.phase * (1.7 + 0.14 * i) + i * 0.6) * 0.38 + 0.62
                target_h = max(4.0, (max(0.35, target_level) * 38.0 + 4.0) * bell * freq_wave) * s
            elif self.state == "listening":
                ripple = math.sin(self.phase * 2.0 + i * 0.6) * 0.35 + 0.65
                target_h = max(4.0, (max(0.15, target_level) * 25.0 + 4.0) * bell * ripple) * s
            elif self.state == "paused":
                target_h = 5.5 * s
            else:
                target_h = 4.0 * s
            bx = spec_x0 + i * (bar_w + spacing)
            bh = min(43.0 * s, max(4.0 * s, target_h))
            eq_base = "#fef3c7" if self.theme == "seiko" else "#e0f2fe"
            bar_color = _interpolate_color(eq_base, glow_color, t)
            self.canvas.create_line(bx, spec_y2 - 2 * s - bh, bx, spec_y2 - 2 * s, fill=bar_color, width=bar_w)

        # Marquee Track Line
        track_line = ch_label if ch_label else header_status
        if len(track_line) > 58:
            track_line = track_line[:57] + "…"
        self.canvas.create_text(112 * s, 135 * s, text=track_line, fill="#e6f1ff", font=("Consolas", sf(15), "bold"), anchor="w")

        # 3. Smoked-Obsidian Live Reader Bay (pulled cleanly inside dark glass: y=197..232)
        reader_hdr = "NOW READING" if self.state == "speaking" else ("PAUSED AT" if self.state == "paused" else "LIVE READER")
        self.canvas.create_text(82 * s, 198 * s, text=reader_hdr, fill=glow_color, font=("Consolas", sf(10), "bold"), anchor="w")
        self.canvas.create_text(718 * s, 198 * s, text="⌖ LOCATE IN CHAT", fill="#64748b", font=("Consolas", sf(10), "bold"), anchor="e")

        wrapped = self._wrap_reader_segments(ctx_before, phrase, ctx_after, max_chars=70, max_lines=2)
        if not wrapped:
            empty_msg = "WAITING FOR ASSISTANT RESPONSE..."
            self.canvas.create_text(82 * s, 219 * s, text=empty_msg, fill="#64748b", font=("Consolas", sf(13)), anchor="w")
        else:
            hl_bg = "#2a1f08" if self.theme == "seiko" else "#0f1e36"
            hl_fg = "#fef3c7" if self.theme == "seiko" else "#ffffff"
            line_y = 213 * s
            for line_tokens in wrapped:
                cur_x = 82 * s
                for tok, is_act in line_tokens:
                    tok_font = ("Consolas", sf(13), "bold") if is_act else ("Consolas", sf(13))
                    tok_color = hl_fg if is_act else "#cbd5e1"
                    item_id = self.canvas.create_text(cur_x, line_y, text=tok, fill=tok_color, font=tok_font, anchor="w")
                    bbox = self.canvas.bbox(item_id)
                    if bbox and bbox[2] > 718 * s:
                        self.canvas.delete(item_id)
                        break
                    if is_act and bbox:
                        hl_rect = self.canvas.create_rectangle(
                            bbox[0] - 2 * s, bbox[1], bbox[2] + 2 * s, bbox[3],
                            fill=hl_bg, outline=glow_color, width=1,
                        )
                        self.canvas.tag_lower(hl_rect, item_id)
                    cur_x = (bbox[2] + 6 * s) if bbox else (cur_x + (len(tok) * 8 + 6) * s)
                line_y += 17 * s

        # 4. Seek Groove Progress & Slider Knob
        track_x1, track_x2 = 65 * s, 735 * s
        if prog > 0.005:
            knob_x = track_x1 + (track_x2 - track_x1) * prog
            self.canvas.create_line(track_x1, 271 * s, knob_x, 271 * s, fill=glow_color, width=max(2, int(4 * s)), capstyle="round")
            self._draw_rounded_rect(knob_x - 6 * s, 266 * s, knob_x + 6 * s, 276 * s, 3, fill="#e2e8f0", outline="#1e293b", width=1)

        # 5. Sculpted Hardware Button Overlays
        btn_defs = self._get_button_defs(w)
        btn_y1, btn_y2 = 294 * s, 328 * s
        cy = (btn_y1 + btn_y2) / 2
        for btn_id, icon, ubx1, ubx2 in btn_defs:
            bx1, bx2 = ubx1 * s, ubx2 * s
            is_btn_hover = (self.hovered_button == btn_id)
            is_btn_pressed = (self.pressed_button == btn_id)
            if is_btn_pressed:
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 6, fill="", outline="#ffffff", width=1)
                txt_fill, draw_cy = "#ffffff", cy + 1
            elif is_btn_hover:
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 6, fill="", outline="#60a5fa", width=1)
                txt_fill, draw_cy = "#93c5fd", cy
            elif btn_id == "play_pause":
                rim = "#facc15" if self.state == "paused" else ("#0284c7" if is_light_metal else "#38bdf8")
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 6, fill="", outline=rim, width=1)
                txt_fill, draw_cy = ("#b45309" if (self.state == "paused" and is_light_metal) else ("#fde047" if self.state == "paused" else ("#0f172a" if is_light_metal else "#e0f2fe"))), cy
            else:
                txt_fill, draw_cy = ("#0f172a" if is_light_metal else "#f1f5f9"), cy
            font_spec = ("Segoe UI Symbol", sf(14), "bold") if "5s" in icon else ("Segoe UI Symbol", sf(16))
            self.canvas.create_text((bx1 + bx2) / 2, draw_cy, text=icon, fill=txt_fill, font=font_spec)

        # Right Pill Button: Speed Cycle
        sp_x1, sp_x2 = 572 * s, 742 * s
        sp_hover = (self.hovered_button == "speed")
        sp_pressed = (self.pressed_button == "speed")
        if sp_pressed:
            self._draw_rounded_rect(sp_x1, btn_y1, sp_x2, btn_y2, 14, fill="", outline="#ffffff", width=1)
            sp_txt, sp_cy = ("#0f172a" if is_light_metal else "#ffffff"), cy + 1
        elif sp_hover:
            self._draw_rounded_rect(sp_x1, btn_y1, sp_x2, btn_y2, 14, fill="", outline="#60a5fa", width=1)
            sp_txt, sp_cy = ("#1d4ed8" if is_light_metal else "#93c5fd"), cy
        else:
            sp_txt, sp_cy = ("#0f172a" if is_light_metal else "#e2e8f0"), cy
        self.canvas.create_text((sp_x1 + sp_x2) / 2, sp_cy, text=f"⚡ SPEED  {spd_lbl}", fill=sp_txt, font=("Consolas", sf(14), "bold"))

    def _draw_frame(self):
        if getattr(self, "_skin_cache_dirty", False):
            # Clear PhotoImage cache strictly on the Tk thread to avoid Tcl cross-thread deadlocks
            self._skin_cache.clear()
            self._skin_cache_dirty = False
        self.canvas.delete("all")
        w = self.width
        h = self.height

        # Determine theme colors based on active theme and state
        palette = THEME_PALETTES.get(self.theme, THEME_PALETTES["cyberpunk"])
        if self.state == "listening":
            glow_color = palette["listening"]["glow"]
            bar_color1 = palette["listening"]["bar1"]
            bar_color2 = palette["listening"]["bar2"]
            dot_color = palette["listening"]["dot"]
            default_status = "Listening..."
        elif self.state == "speaking":
            glow_color = palette["speaking"]["glow"]
            bar_color1 = palette["speaking"]["bar1"]
            bar_color2 = palette["speaking"]["bar2"]
            dot_color = palette["speaking"]["dot"]
            default_status = "Speaking..."
        elif self.state == "paused":
            glow_color = "#ff9100"      # Orange
            bar_color1 = "#ffd600"      # Amber
            bar_color2 = "#ff9100"      # Gold
            dot_color = "#ffd600"       # Amber
            default_status = "Paused"
        elif self.state in ("processing", "thinking"):
            glow_color = "#ffd600"      # Amber
            bar_color1 = "#ff9100"      # Orange
            bar_color2 = "#ffd600"      # Gold
            dot_color = "#ffd600"       # Amber
            default_status = "Thinking..."
        elif self.state == "muted":
            glow_color = "#484f58"
            bar_color1 = "#6e7681"
            bar_color2 = "#484f58"
            dot_color = "#f85149"       # Red dot
            default_status = "Mic Muted"
        else:
            glow_color = "#30363d"
            bar_color1 = "#58a6ff"
            bar_color2 = "#8b949e"
            dot_color = "#8b949e"
            default_status = "Ready"

        bg = "#0c1017"

    def _draw_mini_spectrum(self, start_x: float, dot_y: float, glow_color: str, bar_color1: str, bar_color2: str, s: float):
        """Draw compact spectrum / thinking dots when listening or thinking (hidden while speaking/paused so text stays clear)."""
        if self.state in ("speaking", "paused"):
            return
        if self.state in ("processing", "thinking"):
            num_dots = 3
            dot_spacing = 9 * s
            for i in range(num_dots):
                pulse = (math.sin(self.phase * 3.6 - i * 0.9) + 1.0) / 2.0
                r = (1.8 + pulse * 1.6) * s
                dot_fill = "#ffd600" if pulse > 0.4 else "#ff9100"
                dx = start_x + 12 * s + i * dot_spacing
                self.canvas.create_oval(dx - r, dot_y - r, dx + r, dot_y + r, fill=dot_fill, outline="")
            return
        num_bars = 10
        bar_w = 3.0 * s
        spacing = 3.5 * s
        with self._lock:
            target_level = self.audio_level
        for i in range(num_bars):
            t = i / max(1, num_bars - 1)
            dist = abs(i - (num_bars - 1) / 2) / ((num_bars - 1) / 2)
            bell = math.exp(-1.4 * (dist ** 2))
            if self.state == "listening":
                ripple = math.sin(self.phase * 2.0 + i * 0.6) * 0.35 + 0.65
                target_h = max(3.0, (max(0.15, target_level) * 14.0 + 2.0) * bell * ripple)
            else:
                target_h = 3.0
            cur_h = self.bars[i]
            self.bars[i] = (cur_h * 0.30 + target_h * 0.70) if target_h > cur_h else (cur_h * 0.82 + target_h * 0.18)
            bh = min(18.0, max(2.5, self.bars[i])) * s
            bx = start_x + i * (bar_w + spacing)
            bar_color = _interpolate_color(bar_color1, bar_color2, t)
            self.canvas.create_line(bx, dot_y - bh / 2, bx, dot_y + bh / 2, fill=bar_color, width=bar_w, capstyle="round")

    def _draw_mini_dock(self, w: int, h: int, glow_color: str, bar_color1: str, bar_color2: str, dot_color: str, default_status: str):
        """Render the miniature '90s car-deck compact dock (base 480x84) matching the big HUD."""
        s = self.ui_scale or 1.0
        sf = lambda px: -max(8, int(round(px * s)))
        skin = self._get_scaled_skin(self._skin_filename("mini"), w, h)
        is_light_metal = getattr(self, "skin_finish", "dark") in ("stainless", "titanium")
        if skin is not None:
            self.canvas.create_image(0, 0, anchor="nw", image=skin)
        else:
            self._draw_rounded_rect(1, 1, w - 1, h - 1, 10, fill="#1f2736", outline="#475569", width=1)
            self._draw_rounded_rect(54 * s, 10 * s, 426 * s, 40 * s, 5, fill="#0d2247", outline="#071124", width=1)

        dot_y = 25 * s
        dot_r = 3.5 * s
        self.canvas.create_oval(64 * s - dot_r, dot_y - dot_r, 64 * s + dot_r, dot_y + dot_r, fill=dot_color, outline="")

        now = time.time()
        with self._lock:
            toast_active = bool(self._action_toast and now < self._action_toast_until)
            toast_msg = self._action_toast if toast_active else None
            prog = self.playback_progress

        if toast_msg:
            display_label = toast_msg
            txt_fill = glow_color
        elif self._hover_hint:
            display_label = self._hover_hint
            txt_fill = glow_color
        else:
            display_label = self.format_lcd_label(self.status_text, default_status)
            txt_fill = "#e6edf3"

        show_spec = (not toast_msg) and (self.state not in ("speaking", "paused"))
        max_txt_x = (306 * s) if show_spec else (390 * s)
        lbl_id = self.canvas.create_text(74 * s, dot_y, text=display_label, fill=txt_fill, font=("Segoe UI", sf(15), "bold"), anchor="w")
        lbl_bb = self.canvas.bbox(lbl_id)
        while lbl_bb and lbl_bb[2] > max_txt_x and len(display_label) > 8:
            display_label = display_label[:-4] + "…"
            self.canvas.itemconfig(lbl_id, text=display_label)
            lbl_bb = self.canvas.bbox(lbl_id)

        self._draw_top_right_buttons(w, 15, 35, glow_color)
        if not toast_msg:
            self._draw_mini_spectrum(314 * s, dot_y, glow_color, bar_color1, bar_color2, s)

        if self.state in ("speaking", "paused") and prog > 0.005:
            self.canvas.create_line(58 * s, 39 * s, 422 * s, 39 * s, fill="#10254a", width=max(1, int(2 * s)))
            self.canvas.create_line(58 * s, 39 * s, (58 + 364 * prog) * s, 39 * s, fill=glow_color, width=max(1, int(2 * s)))

        btn_y1, btn_y2 = 52 * s, 74 * s
        cy = (btn_y1 + btn_y2) / 2
        for btn_id, icon, ubx1, ubx2 in self._get_button_defs(w):
            bx1, bx2 = ubx1 * s, ubx2 * s
            is_hover = (self.hovered_button == btn_id)
            is_pressed = (self.pressed_button == btn_id)
            if is_pressed:
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 4, fill="", outline="#ffffff", width=1)
                txt_fill, draw_cy = "#ffffff", cy + 1
            elif is_hover:
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 4, fill="", outline="#60a5fa", width=1)
                txt_fill, draw_cy = "#93c5fd", cy
            elif btn_id == "play_pause":
                rim = "#facc15" if self.state == "paused" else ("#0284c7" if is_light_metal else "#38bdf8")
                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 4, fill="", outline=rim, width=1)
                txt_fill, draw_cy = ("#b45309" if (self.state == "paused" and is_light_metal) else ("#fde047" if self.state == "paused" else ("#0f172a" if is_light_metal else "#e0f2fe"))), cy
            else:
                txt_fill, draw_cy = ("#0f172a" if is_light_metal else "#f1f5f9"), cy
            f_spec = ("Segoe UI Symbol", sf(12), "bold") if "5s" in icon else ("Segoe UI Symbol", sf(14))
            self.canvas.create_text((bx1 + bx2) / 2, draw_cy, text=icon, fill=txt_fill, font=f_spec)

        # Right pill button: quick expand to Reader Deck
        ex_x1, ex_x2 = 359 * s, 445 * s
        ex_hover = (self.hovered_button == "expand")
        ex_txt = ("#1d4ed8" if is_light_metal else "#93c5fd") if ex_hover else ("#0f172a" if is_light_metal else "#e2e8f0")
        if ex_hover:
            self._draw_rounded_rect(ex_x1, btn_y1, ex_x2, btn_y2, 9, fill="", outline="#60a5fa", width=1)
        self.canvas.create_text((ex_x1 + ex_x2) / 2, cy, text="⤢ READER", fill=ex_txt, font=("Consolas", sf(12), "bold"))

    def _draw_mini_pill(self, w: int, h: int, glow_color: str, bar_color1: str, bar_color2: str, dot_color: str, default_status: str):
        """Render the miniature '90s car-deck idle pill (base 480x38) matching the big HUD."""
        s = self.ui_scale or 1.0
        sf = lambda px: -max(8, int(round(px * s)))
        skin = self._get_scaled_skin(self._skin_filename("pill"), w, h)
        if skin is not None:
            self.canvas.create_image(0, 0, anchor="nw", image=skin)
        else:
            self._draw_rounded_rect(1, 1, w - 1, h - 1, h // 2, fill="#1f2736", outline="#475569", width=1)

        dot_y = h / 2
        dot_r = 3.5 * s
        self.canvas.create_oval(64 * s - dot_r, dot_y - dot_r, 64 * s + dot_r, dot_y + dot_r, fill=dot_color, outline="")

        now = time.time()
        with self._lock:
            toast_active = bool(self._action_toast and now < self._action_toast_until)
            toast_msg = self._action_toast if toast_active else None
            prog = self.playback_progress

        if toast_msg:
            display_label = toast_msg
            txt_fill = glow_color
        else:
            display_label = self.format_lcd_label(self.status_text, default_status)
            txt_fill = "#e6edf3"

        show_spec = (not toast_msg) and (self.state not in ("speaking", "paused"))
        max_txt_x = (306 * s) if show_spec else (390 * s)
        lbl_id = self.canvas.create_text(74 * s, dot_y, text=display_label, fill=txt_fill, font=("Segoe UI", sf(15), "bold"), anchor="w")
        lbl_bb = self.canvas.bbox(lbl_id)
        while lbl_bb and lbl_bb[2] > max_txt_x and len(display_label) > 8:
            display_label = display_label[:-4] + "…"
            self.canvas.itemconfig(lbl_id, text=display_label)
            lbl_bb = self.canvas.bbox(lbl_id)

        self._draw_top_right_buttons(w, 9, 29, glow_color)
        if not toast_msg:
            self._draw_mini_spectrum(314 * s, dot_y, glow_color, bar_color1, bar_color2, s)

        if self.state in ("speaking", "paused") and prog > 0.005:
            self.canvas.create_line(58 * s, h - 4 * s, (58 + 364 * prog) * s, h - 4 * s, fill=glow_color, width=max(1, int(2 * s)))

    def _draw_frame(self):
        if getattr(self, "_skin_cache_dirty", False):
            # Clear PhotoImage cache strictly on the Tk thread to avoid Tcl cross-thread deadlocks
            self._skin_cache.clear()
            self._skin_cache_dirty = False
        self.canvas.delete("all")
        w = self.width
        h = self.height

        # Determine theme colors based on active theme and state
        palette = THEME_PALETTES.get(self.theme, THEME_PALETTES["cyberpunk"])
        if self.state == "listening":
            glow_color = palette["listening"]["glow"]
            bar_color1 = palette["listening"]["bar1"]
            bar_color2 = palette["listening"]["bar2"]
            dot_color = palette["listening"]["dot"]
            default_status = "Listening..."
        elif self.state == "speaking":
            glow_color = palette["speaking"]["glow"]
            bar_color1 = palette["speaking"]["bar1"]
            bar_color2 = palette["speaking"]["bar2"]
            dot_color = palette["speaking"]["dot"]
            default_status = "Speaking..."
        elif self.state == "paused":
            glow_color = "#ff9100"
            bar_color1 = "#ffd600"
            bar_color2 = "#ff9100"
            dot_color = "#ffd600"
            default_status = "Paused"
        elif self.state in ("processing", "thinking"):
            glow_color = "#ffd600"
            bar_color1 = "#ff9100"
            bar_color2 = "#ffd600"
            dot_color = "#ffd600"
            default_status = "Thinking..."
        elif self.state == "muted":
            glow_color = "#484f58"
            bar_color1 = "#6e7681"
            bar_color2 = "#484f58"
            dot_color = "#f85149"
            default_status = "Mic Muted"
        else:
            glow_color = "#30363d"
            bar_color1 = "#58a6ff"
            bar_color2 = "#8b949e"
            dot_color = "#8b949e"
            default_status = "Ready"

        mode = self._active_mode()
        if mode == "expanded":
            self._draw_expanded_deck(w, h, glow_color, bar_color1, bar_color2, dot_color, default_status)
        elif mode == "dock":
            self._draw_mini_dock(w, h, glow_color, bar_color1, bar_color2, dot_color, default_status)
        else:
            self._draw_mini_pill(w, h, glow_color, bar_color1, bar_color2, dot_color, default_status)

    def destroy(self):
        self.is_running = False
        if self.root:
            try:
                self.root.after(0, self._safe_destroy)
            except Exception:
                pass

    def _safe_destroy(self):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

if __name__ == "__main__":
    print("[*] Testing Modern Micro-Capsule Waveform HUD with DPI fix...")
    hud = WaveformHud(position="bottom_right")
    hud.start()
    time.sleep(0.5)

    hud.show(state="listening", status="Anti • Listening")
    for t in range(30):
        level = 0.5 + 0.45 * math.sin(t * 0.3)
        hud.update_audio_level(level)
        time.sleep(0.04)

    hud.set_status("Anti • Paused", state="paused")
    time.sleep(1.0)

    hud.set_status("Anti • Speaking", state="speaking")
    for t in range(30):
        level = 0.6 + 0.35 * math.cos(t * 0.4)
        hud.update_audio_level(level)
        time.sleep(0.04)

    hud.hide()
    time.sleep(0.5)
    hud.destroy()
    print("[+] HUD test completed.")
