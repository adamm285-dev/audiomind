"""
Voice profile previewer for Anti.
Run this script to sample 4 different high-fidelity voice profiles.
"""
import os
import sys
import time

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from desktop.audio.tts import speak, VOICE_PROFILES
except ImportError:
    from audio.tts import speak, VOICE_PROFILES

def preview_all():
    samples = [
        ("ava", "Hello, Anti here using the Ava Multilingual neural profile. Crisp, modern, and expressive."),
        ("emma", "Hello, this is Anti using the Emma neural profile. Warm, gentle, and conversational."),
        ("andrew", "Hello, Anti here with the Andrew voice profile. Natural, relaxed, and casual."),
        ("brian", "Hello, this is Anti with the Brian voice profile. Direct, clear, and articulate.")
    ]

    for name, text in samples:
        print(f"\n[*] Playing profile '{name}' ({VOICE_PROFILES[name]})...")
        speak(text, voice=VOICE_PROFILES[name])
        time.sleep(0.5)

if __name__ == "__main__":
    preview_all()
