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
        "listening": {"glow": "#80deea", "bar1": "#b2ebf2", "bar2": "#ffffff", "dot": "#ffffff"},
        "speaking":  {"glow": "#ffffff", "bar1": "#ffffff", "bar2": "#90a4ae", "dot": "#80d8ff"},
    },
}

class WaveformHud:
    def __init__(self, position="bottom_right", theme="cyberpunk"):
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
        self.bars = [3.0] * 7
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
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.root.bind("<Button-1>", self._on_canvas_click)
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

        btn_data = [
            ("prev", "⏮"),
            ("rewind", "⏪ 5s"),
            ("play_pause", "▶" if self.state == "paused" else "⏸"),
            ("forward", "⏩ 5s"),
            ("next", "⏭"),
            ("skip", "⏹ Skip"),
        ]

        num_btns = len(btn_data)
        bw = 70
        gap = 8
        total_w = num_btns * bw + (num_btns - 1) * gap

        # Dynamically scale down if width is narrower than total_w + 20
        if w < total_w + 20:
            avail = max(w - 20, 100)
            gap = max(4, int(avail * 0.08 / (num_btns - 1)))
            bw = int((avail - (num_btns - 1) * gap) / num_btns)
            total_w = num_btns * bw + (num_btns - 1) * gap

        start_x = max(6, (w - total_w) // 2)

        defs = []
        for i, (btn_id, icon) in enumerate(btn_data):
            bx1 = start_x + i * (bw + gap)
            bx2 = bx1 + bw
            defs.append((btn_id, icon, bx1, bx2))
        return defs

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

    def _on_canvas_click(self, event=None):
        """Invoke button transport callback or general on_click (play/pause toggle)."""
        if event and self.height >= 50:
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
        if not event or self.height < 60:
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

        if self.position == "bottom_center":
            x = left + ((right - left) - self.width) // 2
            y = bottom - self.height - 12
        else:  # "bottom_right" (above system tray clock)
            x = right - self.width - 20
            y = bottom - self.height - 12

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
            if self._hover_hint:
                display_label = self._hover_hint
                txt_fill = glow_color
            else:
                display_label = self.status_text
                for prefix in ("AudioMind • ", "AudioMind: ", "Anti • ", "Anti: "):
                    if display_label.startswith(prefix):
                        display_label = display_label[len(prefix):].strip()

                if display_label in ("AudioMind", "AudioMind is online", "Anti", "Anti is online", ""):
                    display_label = default_status

                # Strip everything after bracketed chat name if present (e.g. "[Open Source] Ch 1/3: Intro • Q:2" -> "[Open Source]")
                if display_label.startswith("[") and "]" in display_label:
                    end_b = display_label.find("]")
                    display_label = display_label[:end_b + 1]

                if len(display_label) > 42:
                    display_label = display_label[:41] + "…"
                txt_fill = "#e6edf3"

            self.canvas.create_text(34, dot_y, text=display_label, fill=txt_fill, font=("Segoe UI", 9, "bold"), anchor="w")

            # Right side inside LCD screen: EQ Spectrum Analyzer or Status Icons
            if self.state in ("processing", "thinking"):
                num_dots = 3
                dot_spacing = 9
                start_dot_x = w - 44
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
                p1_x = w - 34
                p2_x = w - 26
                self.canvas.create_line(p1_x, dot_y - pause_h/2, p1_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
                self.canvas.create_line(p2_x, dot_y - pause_h/2, p2_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
            else:
                # 8 Digital EQ Spectrum Analyzer Bars inside LCD
                num_bars = 8
                bar_w = 2.5
                spacing = 4.5
                total_bars_w = num_bars * bar_w + (num_bars - 1) * spacing
                start_x = w - total_bars_w - 20

                with self._lock:
                    target_level = self.audio_level

                for i in range(num_bars):
                    dist = abs(i - num_bars / 2) / (num_bars / 2)
                    bell = math.exp(-2.0 * (dist ** 2))
                    wave = math.sin(self.phase * 2.4 + i * 0.65) * 0.35 + 0.65

                    if self.state == "speaking":
                        cadence = (math.sin(self.phase * 1.8 + i * 1.2) * 0.25 + 0.75)
                        level_factor = max(target_level, 0.40)
                        target_h = max(3.5, (level_factor * 18.0 + 3.0) * bell * wave * cadence)
                    elif self.state == "listening":
                        target_h = max(3.0, (target_level * 18.0 + 3.0) * bell * wave)
                    else:
                        target_h = 3.0

                    self.bars[i % 7] = self.bars[i % 7] * 0.55 + target_h * 0.45
                    bh = min(18.0, max(2.5, self.bars[i % 7]))

                    bx = start_x + i * (bar_w + spacing)
                    by1 = dot_y - bh / 2
                    by2 = dot_y + bh / 2

                    t = i / num_bars
                    bar_color = bar_color1 if t < 0.5 else bar_color2
                    self.canvas.create_line(bx, by1, bx, by2, fill=bar_color, width=bar_w, capstyle="round")

            # Deck 2: Physical CD-Player Transport Buttons
            btn_defs = self._get_button_defs(w)

            btn_y1 = 48
            btn_y2 = 76
            cy = (btn_y1 + btn_y2) / 2

            for btn_id, icon, bx1, bx2 in btn_defs:
                is_btn_hover = (self.hovered_button == btn_id)

                if is_btn_hover:
                    btn_fill = "#222d3d"
                    btn_border = glow_color
                    txt_fill = glow_color
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
                else:
                    btn_fill = "#161c26"
                    btn_border = "#2b3648"
                    txt_fill = "#e6edf3"

                self._draw_rounded_rect(bx1, btn_y1, bx2, btn_y2, 5, fill=btn_fill, outline=btn_border, width=1)
                font_spec = ("Segoe UI Symbol", 9, "bold") if ("5s" in icon or "Skip" in icon) else ("Segoe UI Symbol", 11)
                self.canvas.create_text((bx1 + bx2) / 2, cy, text=icon, fill=txt_fill, font=font_spec)

        else:
            # === COMPACT PILL MODE (h = 38) ===
            dot_y = h / 2
            dot_x = 18
            dot_r = 3.5
            self.canvas.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r, fill=dot_color, outline="")

            display_label = self.status_text
            for prefix in ("AudioMind • ", "AudioMind: ", "Anti • ", "Anti: "):
                if display_label.startswith(prefix):
                    display_label = display_label[len(prefix):].strip()

            if display_label in ("AudioMind", "AudioMind is online", "Anti", "Anti is online", ""):
                display_label = default_status

            if display_label.startswith("[") and "]" in display_label:
                end_b = display_label.find("]")
                display_label = display_label[:end_b + 1]

            if len(display_label) > 42:
                display_label = display_label[:41] + "…"

            self.canvas.create_text(32, dot_y, text=display_label, fill="#e6edf3", font=("Segoe UI", 9, "bold"), anchor="w")

            if self.state in ("processing", "thinking"):
                num_dots = 3
                dot_spacing = 9
                start_dot_x = w - 44
                for i in range(num_dots):
                    pulse = (math.sin(self.phase * 3.6 - i * 0.9) + 1.0) / 2.0
                    r = 1.8 + pulse * 1.6
                    dot_fill = "#ffd600" if pulse > 0.4 else "#ff9100"
                    dx = start_dot_x + i * dot_spacing
                    self.canvas.create_oval(dx - r, dot_y - r, dx + r, dot_y + r, fill=dot_fill, outline="")
            elif self.state == "paused":
                pause_w = 3.0
                pause_h = 13.0
                p1_x = w - 34
                p2_x = w - 26
                self.canvas.create_line(p1_x, dot_y - pause_h/2, p1_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
                self.canvas.create_line(p2_x, dot_y - pause_h/2, p2_x, dot_y + pause_h/2, fill="#ffd600", width=pause_w, capstyle="round")
            else:
                num_bars = 8
                bar_w = 2.5
                spacing = 4.5
                total_bars_w = num_bars * bar_w + (num_bars - 1) * spacing
                start_x = w - total_bars_w - 20

                with self._lock:
                    target_level = self.audio_level

                for i in range(num_bars):
                    dist = abs(i - num_bars / 2) / (num_bars / 2)
                    bell = math.exp(-2.0 * (dist ** 2))
                    wave = math.sin(self.phase * 2.4 + i * 0.65) * 0.35 + 0.65

                    if self.state == "speaking":
                        cadence = (math.sin(self.phase * 1.8 + i * 1.2) * 0.25 + 0.75)
                        level_factor = max(target_level, 0.40)
                        target_h = max(3.5, (level_factor * 18.0 + 3.0) * bell * wave * cadence)
                    elif self.state == "listening":
                        target_h = max(3.0, (target_level * 18.0 + 3.0) * bell * wave)
                    else:
                        target_h = 3.0

                    self.bars[i % 7] = self.bars[i % 7] * 0.55 + target_h * 0.45
                    bh = min(18.0, max(2.5, self.bars[i % 7]))

                    bx = start_x + i * (bar_w + spacing)
                    by1 = dot_y - bh / 2
                    by2 = dot_y + bh / 2

                    t = i / num_bars
                    bar_color = bar_color1 if t < 0.5 else bar_color2
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
