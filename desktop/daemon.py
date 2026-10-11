"""
Hey Anti Background Voice Automation Daemon.
Orchestrates:
1. WASAPI Acoustic Echo Cancellation (AEC) dual-stream capture.
2. Local openWakeWord 'Hey Anti' detection.
3. Responsive audio feedback chimes.
4. Voice Activity Detection (VAD) buffer capture.
5. Speech-to-Text transcription.
6. Multi-tier AST Command Firewall security verification.
7. Antigravity CLI execution (agy --continue -p).
"""

import os
import sys
import time
import subprocess
import threading
import numpy as np
import speech_recognition as sr

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import shutil

# Local harness imports
try:
    from desktop.audio.wasapi_stream import WasapiAecStream
    from desktop.audio.chime import play_chime
    from desktop.audio.tts import speak
    from desktop.firewall.policy import CommandFirewall, RiskTier
except ImportError:
    from audio.wasapi_stream import WasapiAecStream
    from audio.chime import play_chime
    from audio.tts import speak
    from firewall.policy import CommandFirewall, RiskTier

import openwakeword
from openwakeword.model import Model

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
MODEL_PATH = os.path.join(os.path.dirname(__file__), "resources", "models", "hey_anti.onnx")

class VoiceHarnessDaemon:
    def __init__(self, wakeword_threshold: float = 0.55):
        self.wakeword_threshold = wakeword_threshold
        self.firewall = CommandFirewall(workspace_root=os.path.abspath("."))
        self.recognizer = sr.Recognizer()
        self.running = False
        
        print("[*] Initializing 'Hey Anti' Wake-Word Detector...")
        # Check if custom model exists, otherwise load baseline model
        if os.path.exists(MODEL_PATH):
            print(f"[+] Loading custom trained wake-word model: {MODEL_PATH}")
            self.model = Model(wakeword_models=[MODEL_PATH], inference_framework="onnx")
            self.model_name = "hey_anti"
        else:
            print("[!] Custom model not yet found. Falling back to 'hey_jarvis' for initial testing.")
            self.model = Model(wakeword_models=["hey_jarvis_v0.1.onnx"], inference_framework="onnx")
            self.model_name = "hey_jarvis_v0.1"

        print(f"[+] Wake-word engine loaded: {list(self.model.models.keys())}")

    def capture_command_audio(self, aec_stream: WasapiAecStream, max_duration_sec: float = 10.0, silence_timeout_sec: float = 1.2) -> np.ndarray:
        """Capture spoken prompt after wake-word trigger until silence is detected."""
        print("[*] Listening for command...")
        collected_frames = []
        silence_start = None
        start_time = time.time()
        
        # Approximate silence RMS threshold
        SILENCE_RMS_THRESHOLD = 250

        while time.time() - start_time < max_duration_sec:
            chunk = aec_stream.read_chunk()
            collected_frames.append(chunk)

            rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
            
            if rms < SILENCE_RMS_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= silence_timeout_sec:
                    # User stopped speaking
                    break
            else:
                silence_start = None

        if collected_frames:
            return np.concatenate(collected_frames)
        return np.array([], dtype=np.int16)

    def transcribe(self, pcm_16k: np.ndarray) -> str:
        """Transcribe 16kHz PCM audio buffer using SpeechRecognition."""
        if len(pcm_16k) < 8000:  # Less than 0.5s
            return ""

        audio_bytes = pcm_16k.tobytes()
        audio_data = sr.AudioData(audio_bytes, sample_rate=16000, sample_width=2)
        
        try:
            # Use Google Speech Recognition API (fast, reliable default)
            text = self.recognizer.recognize_google(audio_data)
            return text.strip()
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            print(f"[!] STT Error: {e}")
            return ""

    def execute_in_antigravity(self, prompt: str):
        """Invoke Antigravity CLI with the sanitized prompt."""
        print(f"[*] Dispatching prompt to Antigravity CLI: '{prompt}'")
        try:
            # Run asynchronously so daemon doesn't hang
            cmd = [AGY_PATH, "--continue", "-p", prompt]
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(cmd, cwd=os.path.abspath("."), creationflags=creationflags)
        except Exception as e:
            print(f"[!] Error invoking agy.exe: {e}")

    def run(self):
        self.running = True
        print("\n========================================================")
        print("  🛡️  HEY ANTI SECURE VOICE HARNESS ACTIVE")
        print("  AEC: WASAPI Loopback Capture (Microphone + Speaker)")
        print(f"  Wake-Word: '{self.model_name}' (Threshold: {self.wakeword_threshold})")
        print("  Firewall: AST 3-Tier Security Policy Active")
        print("========================================================\n")
        print("[*] Ready and listening for 'Hey Anti'...")

        with WasapiAecStream() as aec_stream:
            while self.running:
                chunk = aec_stream.read_chunk()
                predictions = self.model.predict(chunk)
                
                score = predictions.get(self.model_name, 0.0)
                if score >= self.wakeword_threshold:
                    print(f"\n[⚡ TRIGGER] Wake word detected! Score: {score:.3f}")
                    # 1. Immediate acknowledgment chime
                    play_chime(rising=True)
                    
                    # 2. Capture user voice command
                    audio_buf = self.capture_command_audio(aec_stream)
                    if len(audio_buf) == 0:
                        continue
                    
                    # 3. Transcribe speech
                    prompt_text = self.transcribe(audio_buf)
                    if not prompt_text:
                        print("[-] Could not understand speech.")
                        continue
                    
                    print(f"[🗣️ USER SPOKE]: \"{prompt_text}\"")

                    # 4. Firewall Inspection
                    evaluation = self.firewall.evaluate(prompt_text)
                    print(f"[🛡️ FIREWALL EVALUATION]: Tier={evaluation.tier.name} Reason={evaluation.reason}")

                    if evaluation.tier == RiskTier.RED:
                        play_chime(rising=False)
                        msg = f"Command blocked by Anti firewall: {evaluation.reason}"
                        print(f"[🛑 BLOCKED]: {msg}")
                        speak("Anti cannot execute that command. It was blocked by the security firewall.")
                    
                    elif evaluation.tier == RiskTier.YELLOW:
                        play_chime(rising=True)
                        print(f"[⚠️ CAUTION]: Proceeding with caution. {evaluation.reason}")
                        speak("Caution verified. Anti is dispatching to Antigravity.")
                        self.execute_in_antigravity(prompt_text)

                    elif evaluation.tier == RiskTier.GREEN:
                        print(f"[✅ APPROVED]: Safe workspace prompt.")
                        speak("Anti is on it.")
                        self.execute_in_antigravity(prompt_text)

                time.sleep(0.005)

if __name__ == "__main__":
    daemon = VoiceHarnessDaemon()
    daemon.run()
