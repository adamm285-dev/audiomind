# Engineering Shift Handoff: Pre-Release Adversarial Security Hardening
<!-- Flight Recorder: Immutable historical log. Do NOT ingest on system boot. -->

## Date & Session
- Timestamp: 2026-10-11 02:15 EDT
- Branch: `security/pre-release-hardening`
- Shift Focus: Remediation of all 8 items from the external adversarial security review before public open-source release.

## Completed Actions
1. **Firewall Sibling Path Traversal Fix (`desktop/firewall/policy.py`)**:
   - Replaced flawed `resolved.startswith(self.workspace_root)` check with `os.path.commonpath([self.workspace_root, resolved]) == self.workspace_root`.
   - Updated documentation clarifying the firewall is an advisory guard against accidental commands, not an impregnable security boundary.
   - Added traversal regression tests in `desktop/tests/test_firewall.py`.
2. **Cloud Relay Fail-Closed Auth & Tenant Isolation (`relay/server.py`, `relay/agent_dispatch_router.py`)**:
   - Enforced server refusal to boot if `RELAY_AUTH_SECRET` is unset or < 32 characters.
   - Enforced constant-time header comparison with `hmac.compare_digest`.
   - Derives tenant strictly from verified HMAC token (`<tenant>.<exp>.<sig>`) or server-side mapping; discarded client-controlled `X-Tenant-Id` header.
   - Restricted `/ack` endpoint to `DELIVERED` state and status values in `{EXECUTED, FAILED}`.
   - Stripped tenant echoes from 404 responses.
   - Defaulted server bind to `127.0.0.1` and `reload=False`.
   - Added comprehensive security tests in `relay/test_relay.py` (7/7 tests passing).
3. **Desktop Remote Dispatch Listener Hardening (`desktop/app.py`)**:
   - Disabled remote listener by default; requires explicit HTTPS (or local loopback) endpoint via `REMOTE_DISPATCH_API_URL` and valid secret.
   - Capped remote instruction length at 2000 characters and stripped ASCII/Unicode control characters.
   - Evaluated incoming remote dispatches through `self.firewall.evaluate()`; rejected RED-tier commands immediately.
   - Pastes remote instructions into Antigravity IDE chat without auto-submit (`press_enter=False`); human confirmation required.
   - Removed `X-Admin-Key` transmission and replaced `os.system('notepad ...')` with safe `os.startfile`.
4. **Android Companion URL Security & Intent Confirmation (`AntiVoiceClient.kt`, `AntiVoiceActivity.kt`, `AndroidManifest.xml`, `shortcuts.xml`)**:
   - Removed all hardcoded URLs and session tokens. Defaults to empty strings.
   - Enforced HTTPS URL validation; restricted HTTP to localhost/10.0.2.2 only in debug builds (`BuildConfig.DEBUG`).
   - Implemented runtime configuration dialog with persistent storage in `EncryptedSharedPreferences` (AES256-GCM / AES256-SIV).
   - Removed BROWSABLE `antigravity://` deep link intent filter.
   - Staged external intents (`SEND`, `SEARCH`, App Actions, Shortcuts) into the input box and prompted with an explicit confirmation dialog before dispatch.
   - Whitelisted only the 5 fixed shortcut actions; strictly ignored unknown actions.
   - Fixed shortcuts target package from `.debug` to `pro.antigravity.voice` and set `android:allowBackup="false"`.
   - Added extensive unit tests in `AntiVoiceClientTest.kt`.
5. **PII and Sensitive Path Sanitization**:
   - Verified zero matches across git tree for personal usernames, domain references, LAN IP ranges, and leaked tokens: `git grep -niE "adamm|fieldsmith|floorsm|192\.168\.|H:\\\\Downloads"` and `git grep -n "fs_session_ey"`.
6. **Repo Hygiene & Documentation (`.gitignore`, `desktop/requirements.txt`, `relay/requirements.txt`, `.env.example`, `README.md`, `SECURITY.md`)**:
   - Added `anti_*.log` and databases to `.gitignore`.
   - Pinned all Python dependencies with `==`.
   - Updated `.env.example` with clear secret and URL documentation.
   - Rewrote Security & Privacy Invariants in `README.md` with transparent disclosures of external services (Google STT, Edge-TTS, brain transcript watcher, `anti_tray.log`).
   - Created `SECURITY.md` with `<SECURITY_CONTACT>` placeholder.

## Verification Executed
- Cloud Relay Test Suite: 7/7 passed (`cd relay && pytest -q`).
- Desktop Harness & Firewall Suite: 8/8 passed (`cd desktop && pytest tests/`).
- Android Companion Test Suite: 28/28 tasks passed (`cd android && gradlew.bat testDebugUnitTest`).
- Sensitive Patterns Grep: 0 matches found.
- SDCS Invariants: Gate T (Topology), Gate M (Cartography), Gate L (Mocks), Gate P (Sandbox), Gate S (State budget: 303 tokens) all passing 100%.
