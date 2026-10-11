"""
Synthesized Audio Cues & Chimes for Voice Harness State Changes.
Uses Windows native winsound for zero-latency tone generation without audio file dependencies.
"""

import threading
import winsound
import time

def _beep_async(freq_duration_pairs):
    def run():
        for freq, duration in freq_duration_pairs:
            try:
                winsound.Beep(freq, duration)
            except Exception:
                pass
            time.sleep(0.01)
    threading.Thread(target=run, daemon=True).start()

def play_wake_chime():
    """Ascending two-tone chime indicating 'Hey Anti' was recognized and listening."""
    _beep_async([(659, 70), (880, 100)])  # E5 -> A5

def play_sleep_chime():
    """Descending chime indicating return to standby."""
    _beep_async([(880, 70), (587, 90)])   # A5 -> D5

def play_quarantine_chime():
    """Warning buzz indicating a Red-Tier command was blocked by the firewall."""
    _beep_async([(240, 120), (180, 150)])

def play_submit_chime():
    """Crisp high-speed confirmation chirp indicating command was submitted to chat."""
    _beep_async([(880, 45), (1175, 65)])  # A5 -> D6 (fast modern chirp)

def play_chime(rising: bool = True):
    """Play ascending (wake) or descending (sleep) chime."""
    if rising:
        play_wake_chime()
    else:
        play_quarantine_chime()
