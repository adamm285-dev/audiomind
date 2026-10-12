# Negative Episodic Memory (The Graveyard)
<!-- SPEC-001 v1.9.0 Pillar 6 | Mutability: APPEND-ONLY -->
<!-- Mandatory 3-part schema: Claim -> Measurement -> Reopen Condition -->

## REJ-001: Monolithic Session Diary Ingestion
- **The Claim:** Ingesting all past session logs on Turn 1 boot provides comprehensive historical context.
- **The Measurement:** Exhausted 28k tokens of context window within 3 conversational turns; induced severe context drift and hallucinated file boundaries.
- **What Would Reopen It:** LLM architecture with sub-linear attention latency and zero needle-in-a-haystack degradation beyond 1M tokens.

## REJ-002: Hardcoded Developer Workstation Paths
- **The Claim:** Hardcoding absolute user directories (e.g. `C:\Users\...\agy.exe`) accelerates startup and script execution.
- **The Measurement:** Induced `FileNotFoundError` and `ModuleNotFoundError` across any machine other than the author's workstation; leaked local user identifiers and personal directory structures.
- **What Would Reopen It:** Never. Invariant: all executable binaries and model paths must be dynamically resolved via `shutil.which`, `AppDomain.CurrentDomain.BaseDirectory`, or environment variables.

## REJ-003: Substring Matching for Voice Command Security
- **The Claim:** Simple keyword substring matching (e.g., checking if `"del"` or `"rm"` is inside the command utterance) is sufficient to intercept destructive actions.
- **The Measurement:** Caused frequent false-positive rejections on completely safe developer prompts containing words like `"model"`, `"delegate"`, `"delivery"`, or `"delightful"`.
- **What Would Reopen It:** Never. Replaced by an AST lexer and tokenizer (`CommandLexer`) that evaluates semantic word boundaries, flags, and parameter paths.

## REJ-004: URL Prefix Matching for Localhost Whitelisting
- **The Claim:** Checking `url.startswith("http://localhost")` or `url.startswith("http://127.0.0.1")` is sufficient to allow local dev relays safely.
- **The Measurement:** Permitted arbitrary hostnames beginning with those prefixes (e.g., `http://localhost.attacker.com`), bypassing network boundary restrictions.
- **What Would Reopen It:** Never. Replaced by `urllib.parse.urlparse(url).hostname` strict equality matching.

## REJ-005: Uncorrelated Single-Turn Response Acknowledgment
- **The Claim:** Acknowledging a remote dispatch on the next received LLM assistant response string guarantees completion of that dispatch.
- **The Measurement:** Sent false-positive `EXECUTED` ACKs to the cloud relay when users typed unrelated prompts in different IDE chat tabs, or when remote dispatches were pending unconfirmed.
- **What Would Reopen It:** Never. Replaced by stateful tracking verifying user prompt submission (`USER_INPUT`), matching transcript path, and subsequent response step indices.

## REJ-006: Running Desktop Harness as Administrator to Bypass UIPI
- **The Claim:** Launching `desktop/app.py` with Administrator elevation allows keystroke injection into elevated Antigravity IDE instances.
- **The Measurement:** Violates the principle of least privilege, exposes developer tooling and ambient microphone listeners to unnecessary elevated privileges, and risks privilege escalation.
- **What Would Reopen It:** Never. Invariant: all processes must run at standard user integrity; clear the `~ RUNASADMIN` compatibility flag on `Antigravity IDE.exe`.

## REJ-007: Non-Reentrant Mutex Lock in Speech Player
- **The Claim:** Standard non-reentrant `threading.Lock()` is sufficient for synchronizing speech playback buffer indices and chapter markers.
- **The Measurement:** Induced deadlocks when composite navigation routines (`skip_to_next_chapter()`, `repeat_last_chapter()`) accessed atomic properties (`current_chapter_index`) while already holding the lock.
- **What Would Reopen It:** Never. Invariant: composite audio playback engines must employ reentrant synchronization (`threading.RLock()`).

## REJ-008: Substring Containment for Voice Playback Controls
- **The Claim:** Substring matching playback phrases (e.g., "forward", "resume", "pause", "back up", "next section") across user utterances provides frictionless playback control.
- **The Measurement:** Collided with real developer prompts ("set up port forwarding", "continue with the refactor", "back up the database", "write the resume parser"), swallowing user instructions.
- **What Would Reopen It:** Never. Invariant: playback intents must only be evaluated when speech is active (`is_speech_active()`), and must match exact/anchored normalized command phrases (`match_playback_intent`). Forward is strictly button-only.

## REJ-009: Binary False on Win32 TokenElevation Query Failure (Failing Open)
- **The Claim:** Treating an inaccessible or unqueryable process token as unelevated (`False`) prevents false elevation alarms.
- **The Measurement:** Under Windows UIPI, an unelevated process querying an elevated process token can encounter `ERROR_ACCESS_DENIED`, returning `False` and erroneously allowing synthetic keystrokes that the OS silently drops.
- **What Would Reopen It:** Never. Invariant: elevation queries must return a tri-state (`True`, `False`, `None`), and unverifiable permissions must fail closed (`None` -> block typing and speak warning).
## REJ-010: Pre-Extraction Markdown Stripping and Abrupt Single-Chapter Termination
- **The Claim:** Flattening all markdown and stripping all newlines before passing text to the speech engine simplifies text processing.
- **The Measurement:** Stripped all markdown heading tags (`#`) and paragraph delimiters (`\n\n`), reducing multi-section assistant responses to a single unstructured chapter (`[("Overview", text)]`). When users clicked "Next Chapter", `skip_to_next_chapter()` evaluated `curr + 1 < total_chapters` as false and jumped to the end of audio (`len(audio_data)`), abruptly terminating speech and killing active conversations.
- **What Would Reopen It:** Never. Invariant: structured text/markdown headings and paragraph breaks must be preserved through chapter extraction, chapter titles must be sanitized of markdown links/symbols, chapter bodies cleaned per-chunk, and single-chapter streams must never abort on forward navigation.

## REJ-011: Cloud-Only Speech Synthesis & Unchecked Preparing State Gating
- **The Claim:** Relying exclusively on Edge-TTS cloud service without a local offline fallback is sufficient for ambient voice playback.
- **The Measurement:** Microsoft Edge-TTS rotated client tokens, returning 403 Forbidden. With no fallback, speech synthesis failed, returning empty audio without invoking the audio player. In the app worker, `finally:` checked `if not is_speech_active():`; if previous audio was paused, `is_speech_active()` returned `True`, trapping the HUD and tray in `"AudioMind • Preparing..."` indefinitely.
- **What Would Reopen It:** Never. Invariant: Ambient speech assistant must have offline local Windows SAPI fallback (`synth_sapi_pcm`) with fast circuit breaking on cloud errors, speech-stopping mutex synchronization (`self._speak_lock`), and fail-safe HUD/tray cleanup that handles paused and error states explicitly.

## REJ-012: Unauthenticated Web Scraper (Edge-TTS) as Primary Speech Engine
- **The Claim:** Relying on reverse-engineered Edge-TTS WebSocket endpoints (`wss://speech.platform.bing.com/...`) provides long-term free neural speech.
- **The Measurement:** Microsoft intermittently updates anti-abuse client tokens (`Sec-MS-GEC`), resulting in persistent HTTP/WebSocket 403 Forbidden handshake rejections. Dropping straight to legacy Windows SAPI 5.0 degrades the user experience to robotic 2005-era voice synthesis (`Microsoft Zira Desktop`).
- **What Would Reopen It:** Never for primary production speech. Upgraded to a tiered architecture with Kokoro-82M ONNX local neural synthesis as Tier 1 (100% offline, 48kHz stereo, zero network dependencies, warm human-grade voice), Edge-TTS as Tier 2, and SAPI strictly as emergency Tier 3 failsafe.

