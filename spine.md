# Constitutional Invariants (The Law)
<!-- SPEC-001 v1.9.0 Pillar 1 | Mutability: IMMUTABLE (Human-Only) -->

## Non-Negotiable Domain Axioms
1. Zero-Trust Voice Execution: Spoken commands must never execute destructive operations (RED Tier: file deletions, disk formatting, registry edits, system configuration, directory traversal outside workspace) without explicit physical human keyboard confirmation. Command evaluations generate SHA-256 HMAC non-repudiation audit tokens.
2. Tenant Isolation & Authorization: Cloud relay operations must strictly verify session bearer tokens (RELAY_AUTH_SECRET) and isolate dispatches by tenant ID, failing closed (HTTP 401) on missing or invalid authentication.
3. Secret & PII Hygiene: Zero plaintext secrets, developer credentials, personal user paths (e.g. `C:\Users\<user>`), or private device IP addresses committed to git.
4. Non-Blocking Ambient Audio: Audio streams (WASAPI AEC dual-stream capture) and Edge-TTS playback must run on background threads without locking the main Win32 tray thread.

## Deterministic Verification Gates
- Cloud Relay Test Suite: `pytest relay/test_relay.py` (Must pass 100%).
- Desktop Harness & Firewall Suite: `pytest desktop/tests/` (Must pass 100%).
- Android Companion Unit Tests: `cd android && ./gradlew test` (or `gradlew.bat test` on Windows, Must pass 100%).
- SDCS Invariant Gates: `sdcs doctor`, `sdcs verify`, `sdcs map`, `sdcs audit`.

## Absolute Forbidden Operations
- Destructive git operations (`git push --force`, `git reset --hard` on tracked public branches).
- Bypassing pre-commit hooks via `--no-verify`.
- Bypassing the AST Command Firewall in automated execution pathways.
- Reading `sessions/*.md` flight recorder archives during Turn 1 boot hydration.
