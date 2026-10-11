# Engineering Shift Handoff: Remote Listener Hardening & Ghost Commit Advisory
<!-- Flight Recorder: Immutable historical log. Do NOT ingest on system boot. -->

## Date & Session
- Timestamp: 2026-10-11 02:25 EDT
- Branch: `security/pre-release-hardening`
- Shift Focus: Remediation of adversarial edge cases (hostname bypass, textarea concatenation, uncorrelated Done-ACKs) and git history leak assessment.

## Completed Actions
1. **Strict Hostname Verification (`desktop/app.py`)**:
   - Replaced prefix matching (`url.startswith("http://localhost")`) with `urllib.parse.urlparse(url).hostname`.
   - Only allows `https://` (with valid hostname) or `http://` where `parsed.hostname in ("127.0.0.1", "localhost")`.
   - Defeats subdomain attacks such as `http://localhost.attacker.com` and `http://127.0.0.1.attacker.com`.
2. **Textarea Buffer Isolation (`desktop/app.py`)**:
   - Updated `submit_to_antigravity_chat` to send `Ctrl+A` before `Ctrl+V`.
   - Prevents incoming commands from concatenating onto unsubmitted remote instructions or leftover user text.
   - Updated `voice_loop` to detect when a local voice command arrives while an unconfirmed remote dispatch is pending; immediately cancels the remote dispatch, emits an ACK with status `FAILED` ("Superseded by local voice command before user confirmation"), and clears the pending state before typing the voice prompt.
3. **Correlated Remote Execution ACKs (`desktop/audio/read_aloud.py`, `desktop/app.py`)**:
   - Extended `TranscriptWatcher` to emit `on_user_input(text, filepath, idx)` when `USER_INPUT` turns appear.
   - In `desktop/app.py`, incoming remote dispatches are tracked with `submitted=False`.
   - When the user presses Enter, `_on_user_input` checks for a match with the staged remote instruction. If matched, it sets `submitted=True` and locks in `matched_transcript` and `matched_step_index`. If the user submits different text, the remote dispatch is marked cancelled.
   - `_on_assistant_response` now strictly checks that `submitted=True`, the response is from the same transcript file, and `step_index > matched_step_index` before transmitting the `EXECUTED` ACK to the cloud relay.
4. **Comprehensive Test Coverage (`desktop/tests/test_remote_listener_security.py`)**:
   - Added 7 unit tests verifying URL parsing edge cases, prefix spoofing rejection, textarea state management, transcript correlation, and cancellation on prompt divergence.
5. **Episodic Memory & Cartography Updates**:
   - Synchronized `app_map.md` with new test module.
   - Added `REJ-004` (URL prefix matching) and `REJ-005` (uncorrelated response ACKs) to `decisions.md`.
   - Updated `evals.md` empirical scorecard (Desktop suite: 15/15 passed).

## Critical Open-Source Release Advisory: Ghost Commit 7050c86
- **Investigation:** Git reflog and remote audit confirmed that commit `7050c86` (containing the hardcoded credential in `AntiVoiceClient.kt`) was pushed to `origin/main` before being amended to `bfdc0cb`.
- **GitHub Invariant:** GitHub retains loose/overwritten commits indefinitely by commit hash as long as the repository exists. Flipping the existing private repository to public makes commit `7050c86` accessible to anyone with the SHA.
- **Mandatory Safe Release Procedure:**
  1. Do NOT toggle `adamm285-dev/anti-voice-assistant` to public.
  2. Create a brand-new public repository on GitHub (e.g., `anti-voice-assistant`).
  3. Export a single clean squashed commit containing the current hardened tree and push to the new repository.
  4. Delete the old private repository from GitHub, permanently purging loose commit objects.

## Verification Executed
- Desktop Test Suite: 15/15 passed (`pytest desktop/tests/`).
- Cloud Relay Test Suite: 7/7 passed (`pytest relay/test_relay.py`).
- Android Companion Test Suite: 28/28 unit tests passed (`gradlew testDebugUnitTest`).
- SDCS Gates: AST Topology, Cartography drift, Mocks ledger, Working Memory Budget (301/350 tokens) all passed 100%.
