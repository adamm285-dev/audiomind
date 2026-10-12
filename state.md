# Dynamic Working Memory (The Blackboard)
<!-- SPEC-001 v1.9.0 Pillar 4 | Mutability: HIGH VOLATILITY | Budget: ~300 Tokens -->
<!-- Read on Turn 1 boot. Strictly pruned after milestone completion. -->

## Current Objective
- Offline SAPI Speech Fallback & Preparing State Freeze Resolution.

## Status & Gate Verification
- [x] Edge-TTS 403 Circuit Breaker: Rapidly trips on HTTP/WS 403 to prevent thread timeouts.
- [x] Local Offline SAPI Fallback: Windows SAPI.SpVoice (48kHz stereo float32 PCM) active for multi-chapter and single-pass speech.
- [x] HUD & Tray Freeze Remediation: Concurrency lock (_speak_lock), stop_speech() on new response, and explicit paused/stopped state cleanup in app worker.
- [x] Full Verification: Desktop (38/38 passed), Relay (7/7 passed), Android (28/28 verified). Clean git tree.

## Immediate Next Action (Post-Compact)
- Inform user of root cause, verified fixes, and provide instructions to start AudioMind.
