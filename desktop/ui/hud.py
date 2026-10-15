"""
AudioMind Desktop Waveform HUD (Heads-Up Display).
A minimalist, ultra-compact floating micro-capsule pill widget that animates live 
audio waveforms when listening, thinking, speaking, or paused.
Positioned discreetly above the Windows taskbar and system tray clock.
"""
import math
import time
import threading
import tkinter as tk
import ctypes
from ctypes import wintypes

def attach_to_default_desktop():
    """Ensure the calling thread is attached to the user's interactive 'Default' desktop."""
    try:
        u = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        h_desk = u.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if h_desk:
            u.SetThreadDesktop(h_desk)
    except Exception:
        pass

def get_primary_work_area():
    """Returns (left, top, right, bottom) of the primary display work area excluding the taskbar."""
    try:
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    return (0, 0, 1920, 1040)

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
    def __init__(self, position="bottom_right", theme="cyberpunk", width=480):
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

        # Collapse callback (e.g. collapse straight to tray)
        self.on_collapse = None

        # Tactile button pressing & high-priority action flash feedback
        self.pressed_button = None
        self._action_toast = None
        self._action_toast_until = 0.0

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
        """Returns button definitions [(id, icon, bx1, bx2), ...] symmetrically centered within width w."""
        if w is None:
            w = self.width

        # Proportional button widths: compact single-glyph buttons (52px), medium transport (60-70px),
        # and generous width for '⏹ Skip' (82px) to prevent text overflow and ensure symmetrical chassis margins.
        btn_data = [
            ("prev", "⏮", 52),
            ("rewind", "⏪ 5s", 70),
            ("play_pause", "▶" if self.state == "paused" else "⏸", 60),
            ("forward", "⏩ 5s", 70),
            ("next", "⏭", 52),
            ("skip", "⏹ Skip", 82),
        ]

        total_base = sum(b[2] for b in btn_data)
        gap = 8
        num_btns = len(btn_data)
        total_w = total_base + (num_btns - 1) * gap

        # Dynamically scale down if width is narrower than total_w + 24
        if w < total_w + 24:
            avail = max(w - 24, 100)
            gap = max(4, int(avail * 0.08 / (num_btns - 1)))
            scale = (avail - (num_btns - 1) * gap) / max(1, total_base)
            defs = []
            cur_x = (w - avail) // 2
            for btn_id, icon, bw in btn_data:
                scaled_bw = int(bw * scale)
                defs.append((btn_id, icon, cur_x, cur_x + scaled_bw))
                cur_x += scaled_bw + gap
            return defs

        start_x = (w - total_w) // 2
        defs = []
        cur_x = start_x
        for btn_id, icon, bw in btn_data:
            bx1 = cur_x
            bx2 = cur_x + bw
            cur_x += bw + gap
            defs.append((btn_id, icon, bx1, bx2))
        return defs

    def _hit_test_collapse(self, x, y):
        """Hit-test (x, y) coordinates against the top-right collapse button."""
        w = self.width
        if not (w - 38 <= x <= w - 10):
            return False
        if self.height >= 60:
            return 12 <= y <= 38
        else:
            return 6 <= y <= 32

    def _hit_test_button(self, x, y):
        """Hit-test (x, y) coordinates against Row 2 CD-player transport buttons."""
        if self.height < 60:
            return None
        if not (46 <= y <= 78):
            return None
        for btn_id, _, bx1, bx2 in self._get_button_defs():
            if bx1 <= x <= bx2:
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
            elif self.height >= 50:
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

            if self.height >= 50:
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

        if self.height < 60:
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
        """Expand height to 84px when speaking/paused or hovered, collapse to 38px otherwise."""
        should_expand = self.is_hovered or (self.state in ("speaking", "paused"))
        target_h = 84 if should_expand else 38
        if self.height != target_h:
            self.height = target_h
            if self.canvas:
                try:
                    self.canvas.config(height=self.height)
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

    def _draw_frame(self):
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

        # 1. Sleek Outer Chassis
        r = 12 if h >= 60 else (h // 2)
        chassis_outline = glow_color if (self.is_hovered or self.state == "speaking") else "#2c3545"
        self._draw_rounded_rect(1, 1, w - 1, h - 1, r, fill=bg, outline=chassis_outline, width=1)

        if h >= 60:
            # === EXPANDED CD-PLAYER DOCK (h = 84) ===
            # Deck 1: Recessed LCD Display Pocket
            lcd_x1 = 10
            lcd_y1 = 8
            lcd_x2 = w - 10
            lcd_y2 = 42
            self._draw_rounded_rect(lcd_x1, lcd_y1, lcd_x2, lcd_y2, 6, fill="#06090e", outline="#1c2432", width=1)

            # LED Indicator Dot (inside LCD display)
            dot_x = 21
            dot_y = 25
            dot_r = 3.5
            self.canvas.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r, fill=dot_color, outline="")

            # LCD Text Display
            now = time.time()
            with self._lock:
                toast_active = bool(self._action_toast and now < self._action_toast_until)
                toast_msg = self._action_toast if toast_active else None

            if toast_msg:
                display_label = toast_msg
                txt_fill = glow_color
            elif self._hover_hint:
                display_label = self._hover_hint
                txt_fill = glow_color
            else:
                display_label = self.format_lcd_label(self.status_text, default_status)
                txt_fill = "#e6edf3"

            self.canvas.create_text(34, dot_y, text=display_label, fill=txt_fill, font=("Segoe UI", 9, "bold"), anchor="w")

            # Top-Right Collapse to Tray Button
            col_x1 = w - 34
            col_x2 = w - 14
            col_y1 = 15
            col_y2 = 35
            col_hover = (self.hovered_button == "collapse")
            col_pressed = (self.pressed_button == "collapse")
            if col_pressed:
                col_bg = "#2f415c"
                col_border = "#ffffff"
                col_txt = "#ffffff"
                col_cy = (col_y1 + col_y2) / 2 + 1
            elif col_hover:
                col_bg = "#222d3d"
                col_border = glow_color
                col_txt = glow_color
                col_cy = (col_y1 + col_y2) / 2
            else:
                col_bg = "#0d131d"
                col_border = "#212b3d"
                col_txt = "#8b949e"
                col_cy = (col_y1 + col_y2) / 2
            self._draw_rounded_rect(col_x1, col_y1, col_x2, col_y2, 4, fill=col_bg, outline=col_border, width=1)
            self.canvas.create_text((col_x1 + col_x2) / 2, col_cy, text="▼", fill=col_txt, font=("Segoe UI Symbol", 8, "bold"))

            # Right side inside LCD screen: EQ Spectrum Analyzer or Status Icons (positioned safely before collapse button)
            if self.state in ("processing", "thinking"):
                num_dots = 3
                dot_spacing = 9
                start_dot_x = w - 68
                for i in range(num_dots):
                    pulse = (math.sin(self.phase * 3.6 - i * 0.9) + 1.0) / 2.0
                    r = 1.8 + pulse * 1.6
                    dot_fill = "#ffd600" if pulse > 0.4 else "#ff9100"
                    dx = start_dot_x + i * dot_spacing
                    self.canvas.create_oval(dx - r, dot_y - r, dx + r, dot_y + r, fill=dot_fill, outline="")
            elif self.state == "paused":
                # Two crisp paused vertical bars || in amber
                pause_w = 3.0
                pause_h = 13.0
                p1_x = w - 52
                p2_x = w - 44
                self.canvas.create_line(p1_x, dot_y - pause_h/2, p1_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
                self.canvas.create_line(p2_x, dot_y - pause_h/2, p2_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
            else:
                # 10-Band Hi-Fi Digital Spectrum Analyzer inside LCD
                num_bars = 10
                bar_w = 3.5
                spacing = 4.5
                total_bars_w = num_bars * bar_w + (num_bars - 1) * spacing
                start_x = w - total_bars_w - 44

                with self._lock:
                    target_level = self.audio_level

                for i in range(num_bars):
                    t = i / max(1, num_bars - 1)
                    dist = abs(i - (num_bars - 1) / 2) / ((num_bars - 1) / 2)
                    bell = math.exp(-1.4 * (dist ** 2))

                    if self.state == "speaking":
                        # Multi-band frequency simulation: bass, vocal core, sibilants
                        if i < 3:
                            freq_wave = math.sin(self.phase * 1.6 + i * 0.5) * 0.35 + 0.65
                        elif i < 7:
                            freq_wave = math.sin(self.phase * 2.3 + i * 0.8) * 0.40 + 0.60
                        else:
                            freq_wave = math.sin(self.phase * 3.2 + i * 1.1) * 0.45 + 0.55

                        cadence = (math.sin(self.phase * 1.9 + i * 0.9) * 0.25 + 0.75)
                        level_mult = max(0.35, target_level)
                        target_h = max(4.0, (level_mult * 20.0 + 3.0) * bell * freq_wave * cadence)
                    elif self.state == "listening":
                        ripple = math.sin(self.phase * 2.0 + i * 0.6) * 0.35 + 0.65
                        level_mult = max(0.15, target_level)
                        target_h = max(3.5, (level_mult * 18.0 + 2.5) * bell * ripple)
                    else:
                        resting = math.sin(self.phase * 1.2 + i * 0.5) * 0.2 + 0.8
                        target_h = 3.5 * resting

                    # Snappy analog attack, smooth organic decay
                    cur_h = self.bars[i]
                    if target_h > cur_h:
                        self.bars[i] = cur_h * 0.30 + target_h * 0.70
                    else:
                        self.bars[i] = cur_h * 0.82 + target_h * 0.18

                    bh = min(24.0, max(3.5, self.bars[i]))
                    bx = start_x + i * (bar_w + spacing)
                    by1 = dot_y - bh / 2
                    by2 = dot_y + bh / 2

                    bar_color = _interpolate_color(bar_color1, bar_color2, t)
                    self.canvas.create_line(bx, by1, bx, by2, fill=bar_color, width=bar_w, capstyle="round")

            # Deck 2: Physical CD-Player Transport Buttons
            btn_defs = self._get_button_defs(w)

            btn_y1 = 48
            btn_y2 = 76
            cy = (btn_y1 + btn_y2) / 2

            for btn_id, icon, bx1, bx2 in btn_defs:
                is_btn_hover = (self.hovered_button == btn_id)
                is_btn_pressed = (self.pressed_button == btn_id)

                if is_btn_pressed:
                    btn_fill = "#2f415c"
                    btn_border = "#ffffff"
                    txt_fill = "#ffffff"
                    draw_cy = cy + 1
                elif is_btn_hover:
                    btn_fill = "#222d3d"
                    btn_border = glow_color
                    txt_fill = glow_color
                    draw_cy = cy
                elif btn_id == "play_pause":
                    # Center Play/Pause button styling
                    if self.state == "paused":
                        btn_fill = "#262012"
                        btn_border = "#ffd600"
                        txt_fill = "#ffd600"
                    else:
                        btn_fill = "#1b2535"
                        btn_border = glow_color
                        txt_fill = glow_color
                    draw_cy = cy
                else:
                    btn_fill = "#161c26"
                    btn_border = "#2b3648"
                    txt_fill = "#e6edf3"
                    draw_cy = cy

                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 5, fill=btn_fill, outline=btn_border, width=1)
                font_spec = ("Segoe UI Symbol", 9, "bold") if ("5s" in icon or "Skip" in icon) else ("Segoe UI Symbol", 11)
                self.canvas.create_text((bx1 + bx2) / 2, draw_cy, text=icon, fill=txt_fill, font=font_spec)

        else:
            # === COMPACT PILL MODE (h = 38) ===
            dot_y = h / 2
            dot_x = 18
            dot_r = 3.5
            self.canvas.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r, fill=dot_color, outline="")

            now = time.time()
            with self._lock:
                toast_active = bool(self._action_toast and now < self._action_toast_until)
                toast_msg = self._action_toast if toast_active else None

            if toast_msg:
                display_label = toast_msg
                txt_fill = glow_color
            else:
                display_label = self.format_lcd_label(self.status_text, default_status)
                txt_fill = "#e6edf3"
            self.canvas.create_text(32, dot_y, text=display_label, fill=txt_fill, font=("Segoe UI", 9, "bold"), anchor="w")

            # Top-Right Collapse to Tray Button
            col_x1 = w - 34
            col_x2 = w - 14
            col_y1 = 9
            col_y2 = 29
            col_hover = (self.hovered_button == "collapse")
            col_pressed = (self.pressed_button == "collapse")
            if col_pressed:
                col_bg = "#2f415c"
                col_border = "#ffffff"
                col_txt = "#ffffff"
                col_cy = (col_y1 + col_y2) / 2 + 1
            elif col_hover:
                col_bg = "#222d3d"
                col_border = glow_color
                col_txt = glow_color
                col_cy = (col_y1 + col_y2) / 2
            else:
                col_bg = "#0d131d"
                col_border = "#212b3d"
                col_txt = "#8b949e"
                col_cy = (col_y1 + col_y2) / 2
            self._draw_rounded_rect(col_x1, col_y1, col_x2, col_y2, 4, fill=col_bg, outline=col_border, width=1)
            self.canvas.create_text((col_x1 + col_x2) / 2, col_cy, text="▼", fill=col_txt, font=("Segoe UI Symbol", 8, "bold"))

            if self.state in ("processing", "thinking"):
                num_dots = 3
                dot_spacing = 9
                start_dot_x = w - 68
                for i in range(num_dots):
                    pulse = (math.sin(self.phase * 3.6 - i * 0.9) + 1.0) / 2.0
                    r = 1.8 + pulse * 1.6
                    dot_fill = "#ffd600" if pulse > 0.4 else "#ff9100"
                    dx = start_dot_x + i * dot_spacing
                    self.canvas.create_oval(dx - r, dot_y - r, dx + r, dot_y + r, fill=dot_fill, outline="")
            elif self.state == "paused":
                pause_w = 3.0
                pause_h = 13.0
                p1_x = w - 52
                p2_x = w - 44
                self.canvas.create_line(p1_x, dot_y - pause_h/2, p1_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
                self.canvas.create_line(p2_x, dot_y - pause_h/2, p2_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
            else:
                num_bars = 10
                bar_w = 3.0
                spacing = 3.5
                total_bars_w = num_bars * bar_w + (num_bars - 1) * spacing
                start_x = w - total_bars_w - 44

                with self._lock:
                    target_level = self.audio_level

                for i in range(num_bars):
                    t = i / max(1, num_bars - 1)
                    dist = abs(i - (num_bars - 1) / 2) / ((num_bars - 1) / 2)
                    bell = math.exp(-1.4 * (dist ** 2))

                    if self.state == "speaking":
                        if i < 3:
                            freq_wave = math.sin(self.phase * 1.6 + i * 0.5) * 0.35 + 0.65
                        elif i < 7:
                            freq_wave = math.sin(self.phase * 2.3 + i * 0.8) * 0.40 + 0.60
                        else:
                            freq_wave = math.sin(self.phase * 3.2 + i * 1.1) * 0.45 + 0.55

                        cadence = (math.sin(self.phase * 1.9 + i * 0.9) * 0.25 + 0.75)
                        level_mult = max(0.35, target_level)
                        target_h = max(3.5, (level_mult * 15.0 + 2.5) * bell * freq_wave * cadence)
                    elif self.state == "listening":
                        ripple = math.sin(self.phase * 2.0 + i * 0.6) * 0.35 + 0.65
                        level_mult = max(0.15, target_level)
                        target_h = max(3.0, (level_mult * 14.0 + 2.0) * bell * ripple)
                    else:
                        target_h = 3.0

                    cur_h = self.bars[i]
                    if target_h > cur_h:
                        self.bars[i] = cur_h * 0.30 + target_h * 0.70
                    else:
                        self.bars[i] = cur_h * 0.82 + target_h * 0.18

                    bh = min(18.0, max(2.5, self.bars[i]))
                    bx = start_x + i * (bar_w + spacing)
                    by1 = dot_y - bh / 2
                    by2 = dot_y + bh / 2

                    bar_color = _interpolate_color(bar_color1, bar_color2, t)
                    self.canvas.create_line(bx, by1, bx, by2, fill=bar_color, width=bar_w, capstyle="round")

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
