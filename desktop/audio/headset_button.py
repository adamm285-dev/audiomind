"""Hardware headset button listener for SteelSeries Arctis Nova Pro Wireless (Windows USB HID).

Listens on the SteelSeries wireless DAC vendor HID interface (VID_1038, PID_12E0,
UsagePage 0xFF00) for ANC / noise-filtering button state transitions (report ``07 bd <state>``)
and invokes ``on_toggle_pause`` with debounce so a single press pauses or resumes AudioMind
playback hands-free.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from typing import Callable, Optional

STEELSERIES_VID = 0x1038
ARCTIS_NOVA_PRO_PID = 0x12E0
VENDOR_USAGE_PAGE = 0xFF00


def parse_steelseries_anc_button_packet(data: bytes) -> Optional[int]:
    """Return the ANC mode byte if ``data`` is a SteelSeries ANC button report, else None."""
    if not data or len(data) < 3:
        return None
    if data[0] == 0x07 and data[1] == 0xBD:
        return int(data[2])
    return None


class HeadsetButtonListener:
    """Background USB HID listener for SteelSeries wireless DAC button events."""

    def __init__(
        self,
        on_toggle_pause: Callable[[], None],
        on_double_press: Optional[Callable[[], None]] = None,
        debounce_sec: float = 0.08,
        double_press_window_sec: float = 0.95,
    ):
        self.on_toggle_pause = on_toggle_pause
        self.on_double_press = on_double_press
        self.debounce_sec = debounce_sec
        self.double_press_window_sec = double_press_window_sec
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._handle = None
        self._last_trigger_time: float = 0.0
        self._last_anc_state: Optional[int] = None
        self._timer_lock = threading.Lock()
        self._pending_single_timer: Optional[threading.Timer] = None

    def _fire_single_press(self):
        with self._timer_lock:
            self._pending_single_timer = None
        try:
            self.on_toggle_pause()
        except Exception as exc:
            print(f"[!] Headset button callback error: {exc}")

    def _fire_double_press(self):
        if self.on_double_press is None:
            return
        try:
            self.on_double_press()
        except Exception as exc:
            print(f"[!] Headset double-press callback error: {exc}")

    def handle_packet(self, data: bytes, now: Optional[float] = None) -> bool:
        """Process one raw 64-byte HID report; return True if a button action was scheduled/triggered."""
        anc_state = parse_steelseries_anc_button_packet(data)
        if anc_state is None:
            return False

        ts = time.monotonic() if now is None else now
        if self._last_anc_state is not None and anc_state == self._last_anc_state:
            return False
        if (ts - self._last_trigger_time) < self.debounce_sec:
            return False

        self._last_anc_state = anc_state
        self._last_trigger_time = ts

        if self.on_double_press is None:
            self._fire_single_press()
            return True

        trigger_double = False
        with self._timer_lock:
            if self._pending_single_timer is not None:
                self._pending_single_timer.cancel()
                self._pending_single_timer = None
                trigger_double = True
            else:
                timer = threading.Timer(self.double_press_window_sec, self._fire_single_press)
                timer.daemon = True
                self._pending_single_timer = timer
                timer.start()

        if trigger_double:
            self._fire_double_press()
        return True

    def start(self) -> bool:
        """Start the background HID reader thread on Windows."""
        if sys.platform != "win32":
            return False
        if self.running:
            return True
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop the HID reader thread and close any open device handle."""
        self.running = False
        with self._timer_lock:
            if self._pending_single_timer is not None:
                self._pending_single_timer.cancel()
                self._pending_single_timer = None
        if sys.platform == "win32" and self._handle is not None:
            try:
                ctypes.windll.kernel32.CancelIoEx(self._handle, None)
            except Exception:
                pass
            try:
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None

    def _find_dac_hid_path(self) -> Optional[tuple[str, int]]:
        """Return ``(device_path, input_report_len)`` for SteelSeries 0xFF00 HID if present."""
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hid = ctypes.windll.hid

        RIM_TYPEHID = 2
        RIDI_DEVICENAME = 0x20000007
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        class RAWINPUTDEVICELIST(ctypes.Structure):
            _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]

        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [
                ("Usage", wintypes.USHORT),
                ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT),
                ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT),
                ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT),
                ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT),
                ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT),
                ("NumberFeatureDataIndices", wintypes.USHORT),
            ]

        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
        hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]

        count = wintypes.UINT(0)
        user32.GetRawInputDeviceList(None, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
        if count.value == 0:
            return None

        arr = (RAWINPUTDEVICELIST * count.value)()
        user32.GetRawInputDeviceList(arr, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))

        vid_tag = f"VID_{STEELSERIES_VID:04X}"
        pid_tag = f"PID_{ARCTIS_NOVA_PRO_PID:04X}"

        for dev in arr:
            if dev.dwType != RIM_TYPEHID:
                continue
            nlen = wintypes.UINT(0)
            user32.GetRawInputDeviceInfoW(dev.hDevice, RIDI_DEVICENAME, None, ctypes.byref(nlen))
            buf = ctypes.create_unicode_buffer(nlen.value + 1)
            user32.GetRawInputDeviceInfoW(dev.hDevice, RIDI_DEVICENAME, buf, ctypes.byref(nlen))
            path = buf.value
            upper = path.upper()
            if vid_tag not in upper or pid_tag not in upper:
                continue

            h = kernel32.CreateFileW(
                path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if h == INVALID_HANDLE_VALUE:
                continue
            try:
                ppd = ctypes.c_void_p()
                if hid.HidD_GetPreparsedData(h, ctypes.byref(ppd)):
                    caps = HIDP_CAPS()
                    hid.HidP_GetCaps(ppd, ctypes.byref(caps))
                    hid.HidD_FreePreparsedData(ppd)
                    if caps.UsagePage == VENDOR_USAGE_PAGE and caps.InputReportByteLength > 0:
                        return path, int(caps.InputReportByteLength)
            finally:
                kernel32.CloseHandle(h)
        return None

    def _run_loop(self):
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]

        while self.running:
            found = self._find_dac_hid_path()
            if not found:
                time.sleep(3.0)
                continue

            path, in_len = found
            h = kernel32.CreateFileW(
                path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if h == INVALID_HANDLE_VALUE:
                time.sleep(3.0)
                continue

            self._handle = h
            print(f"[🎧 HEADSET HID]: Connected to SteelSeries DAC ({in_len}-byte reports on 0x{VENDOR_USAGE_PAGE:04X})")
            buf = (ctypes.c_ubyte * max(in_len, 64))()
            read_bytes = wintypes.DWORD(0)

            try:
                while self.running:
                    ok = kernel32.ReadFile(h, buf, in_len, ctypes.byref(read_bytes), None)
                    if not ok or read_bytes.value == 0:
                        break
                    self.handle_packet(bytes(buf[:read_bytes.value]))
            except Exception as exc:
                if self.running:
                    print(f"[!] Headset HID read error: {exc}")
            finally:
                try:
                    kernel32.CloseHandle(h)
                except Exception:
                    pass
                if self._handle == h:
                    self._handle = None
            if self.running:
                time.sleep(1.5)
