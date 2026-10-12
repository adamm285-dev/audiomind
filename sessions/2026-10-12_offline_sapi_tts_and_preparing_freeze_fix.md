# Engineering Shift Handoff: Offline Windows SAPI TTS & Preparing State Freeze Resolution
<!-- Flight Recorder: Immutable historical log. Do NOT ingest on system boot. -->

## Date & Session
- Timestamp: 2026-10-12 04:52 UTC
- Shift Focus: Remediation of "AudioMind • Preparing..." UI freeze, Edge-TTS 403 failover, and offline SAPI speech integration.

## Root Cause Analysis
1. **Edge-TTS 403 Forbidden Handshake**: Microsoft rotated service tokens for `speech.platform.bing.com`, returning `WSServerHandshakeError: 403, message='Invalid response status'`. With no offline speech fallback, Edge-TTS repeatedly failed and returned empty audio bytes.
2. **HUD & Tray Cleanup Deadlock**: `_speak_worker` set HUD status to `AudioMind • Preparing...` and tray to `AudioMind: Preparing audio...`. Because `speak()` failed prior to invoking `play_pcm()`, previous audio (which was paused by the user) remained held in `global_player`. The worker's `finally:` block checked `if not is_speech_active():`, which evaluated to `False` due to `is_paused()` returning `True`. As a result, the worker never hid the HUD or restored the tray state, trapping the UI permanently in `"AudioMind • Preparing..."`.
3. **Unsynchronized Speech Workers**: Concurrent assistant responses spawned uncoordinated threads without stopping prior speech or preventing state collisions.

## Completed Actions
1. **Offline Local Windows SAPI TTS (`desktop/audio/tts.py`)**:
   - Implemented `synth_sapi_pcm()` utilizing `SAPI.SpVoice`, `SpMemoryStream`, and `SpAudioFormat` type 39 (`SAFT48kHz16BitStereo`).
   - Automatically selects natural voice (e.g. `Microsoft Zira Desktop`) and decodes raw int16 PCM into 48kHz stereo float32 arrays via `numpy` in < 150ms.
   - Preserves multi-chapter structure and chapter boundaries during offline synthesis.
2. **Edge-TTS Circuit Breaker & Safe Failover**:
   - Added `_EDGE_TTS_HEALTHY` circuit breaker in `_synth_one` to immediately trip on 403 errors and avoid cascading connection timeouts.
   - Automatic zero-delay failover to `synth_sapi_pcm()` whenever Edge-TTS is unhealthy or yields no audio.
3. **Fail-Safe HUD and Tray State Transitions (`desktop/app.py`)**:
   - Added reentrant `self._speak_lock` and explicit `stop_speech()` invocation prior to new response synthesis.
   - Rewrote `finally:` cleanup in `_speak_worker` and `read_highlighted_text` to explicitly handle `is_paused()` (updating status to `"AudioMind • Paused"` with paused waveform bars) and cleanly hide HUD and restore listening tray icon when audio is inactive or fails.
   - Synchronized `toggle_speech_pause` to directly update the HUD status and tray state on click.
   - Standardized all remaining `"Anti • ..."` and `"Anti: ..."` UI/tray strings to `"AudioMind"`.
4. **Unit Tests & Regression Gates (`desktop/tests/test_hud_and_tray.py`)**:
   - Added `test_tts_sapi_fallback_when_edge_tts_fails` asserting seamless offline SAPI failover when cloud TTS returns empty.
5. **Cross-Repository Synchronization**:
   - Cleanly committed and pushed changes to GitHub repository `adamm285-dev/audiomind` on branch `main` (`38cc3f3`, `c943980`).
   - Committed changes locally to `anti-voice-assistant` on branch `security/pre-release-hardening` (`3e6f90f`, `05ccaf6`).

## Verification Executed
- Desktop Unit Tests: 38/38 PASSED (`pytest desktop/tests/`)
- Cloud Relay Test Suite: 7/7 PASSED (`pytest relay/test_relay.py`)
- Gate T Topology Audit: PASSED (`sdcs verify --topology`)
- Gate M Cartography Audit: PASSED (`sdcs map --check`)
- Gate L Mock Ledger Audit: PASSED (`sdcs verify --mocks`)
- Gate P Working Memory Budget: PASSED (237/350 tokens, `sdcs verify --state`)
- Stale Process PID 49404 terminated.
