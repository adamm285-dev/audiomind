"""
Microphone and Audio Device Diagnostic Tool.
Verifies which device WASAPI opens, reads 3 seconds of live audio from mic,
computes RMS, and runs openWakeWord predictions in real-time.
"""
import os
import sys
import time
import pyaudiowpatch as pyaudio
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from desktop.audio.wasapi_stream import WasapiAecStream
except ImportError:
    from audio.wasapi_stream import WasapiAecStream

from openwakeword.model import Model

def diagnose():
    p = pyaudio.PyAudio()
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        print(f"[*] WASAPI Host API Index: {wasapi_info['index']}, Device Count: {wasapi_info['deviceCount']}")
        default_in = wasapi_info['defaultInputDevice']
        default_out = wasapi_info['defaultOutputDevice']
        print(f"[*] Default WASAPI Input Index: {default_in}")
        if default_in >= 0:
            in_info = p.get_device_info_by_index(default_in)
            print(f"    Name: {in_info['name']}")
            print(f"    Default Sample Rate: {in_info['defaultSampleRate']}, Max Input Channels: {in_info['maxInputChannels']}")
        print(f"[*] Default WASAPI Output Index: {default_out}")
        if default_out >= 0:
            out_info = p.get_device_info_by_index(default_out)
            print(f"    Name: {out_info['name']}")
    finally:
        p.terminate()

    print("\n[*] Initializing WasapiAecStream...")
    with WasapiAecStream() as stream:
        print(f"[+] Mic selected: index={stream.mic_idx}, rate={stream.mic_rate}, channels={stream.mic_channels}")
        print(f"[+] Loopback selected: index={stream.loopback_idx}, rate={stream.loopback_rate}, channels={stream.loopback_channels}")

        print("\n[*] Loading 'hey_anti' model...")
        model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "models", "hey_anti.onnx"))
        model = Model(wakeword_models=[model_path], inference_framework="onnx")
        print(f"[+] Loaded model: {list(model.models.keys())}")

        print("\n[*] READING LIVE AUDIO FOR 5 SECONDS. Say 'Hey Anti' into your microphone now...")
        start = time.time()
        max_score = 0.0
        max_rms = 0.0

        while time.time() - start < 5.0:
            frame, spk_active, mic_rms = stream.read_frame()
            max_rms = max(max_rms, mic_rms)
            
            # Predict
            pred = model.predict(frame)
            score = pred.get("hey_anti", 0.0)
            if score > max_score:
                max_score = score
            
            print(f"\rTime: {time.time()-start:.1f}s | Mic RMS: {mic_rms:.5f} | Spk Active: {spk_active} | Score: {score:.4f} | Max: {max_score:.4f}", end="", flush=True)
            time.sleep(0.01)

        print(f"\n\n[RESULTS]")
        print(f"Peak Mic RMS: {max_rms:.5f}")
        print(f"Peak Wake-Word Score: {max_score:.4f}")

if __name__ == "__main__":
    diagnose()
