# Session Handoff: Kokoro-ONNX Neural Speech Integration & Robot Voice Remediation
**Date:** 2026-10-12  
**Topic:** Restoring High-Definition Neural Voice Playback (Replacing Robotic Windows SAPI)

## 1. Problem Diagnosis
- **Observation:** When AudioMind was relaunched, it sounded like a robotic synthesizer (`Microsoft Zira Desktop`) instead of the warm, human neural voice (`en-US-AvaNeural`).
- **Root Cause:** Microsoft's Edge Read Aloud WebSocket endpoint (`wss://speech.platform.bing.com/...`) rejected `edge-tts` connections with `WSServerHandshakeError: 403, message='Invalid response status'`. The application circuit breaker dropped straight to Windows SAPI 5.0 fallback (`SAPI.SpVoice`), which is a legacy concatenative synthesizer.

## 2. Engineering Solution
- **Local Neural Engine (Kokoro-82M ONNX):** Integrated the open-weights Kokoro-82M model running locally on CPU via ONNX Runtime (`onnxruntime` + `kokoro-onnx`).
- **Acoustic Quality:** Synthesizes warm, expressive neural audio (`af_heart` voice profile, with `af_bella`, `af_nicole`, `am_adam`, etc.).
- **Hardware Integration:** Resamples 24kHz model output to 48kHz stereo `float32` PCM via `scipy.signal.resample_poly`, matching the Arctis Nova Pro / soundcard DAC without transcoding latency.
- **Tiered Multi-Tier Synthesis:**
  - **Tier 1:** Kokoro-ONNX Local Neural Engine (Primary: 100% offline, 48kHz stereo, zero network dependencies, immune to Microsoft 403 blocks).
  - **Tier 2:** Edge-TTS Cloud Neural Synthesis (Secondary fallback if model weights are not present).
  - **Tier 3:** Windows SAPI.SpVoice (Tertiary offline failsafe).
- **Navigation Invariant Preserved:** Multi-chapter responses, chapter markers, seeking, rewind, pause, resume, and real-time waveform HUD telemetry remain fully functional.

## 3. Verification & Metrics
- `pytest desktop/tests/`: 39/39 passing (includes Kokoro chapter alignment, SAPI fallback isolation, HUD, and security tests).
- `pytest relay/test_relay.py`: 7/7 passing.
- Audio Quality: Pristine 48kHz stereo playback verified live.
- Process Status: AudioMind successfully relaunched and active in the system tray.
