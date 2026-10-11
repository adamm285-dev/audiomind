# Engineering Shift Handoff: Antigravity IDE Window Selection, UIPI Boundary & Focus Refinements
<!-- Flight Recorder: Immutable historical log. Do NOT ingest on system boot. -->

## Date & Session
- Timestamp: 2026-10-11 12:20 EDT
- Branch: `security/pre-release-hardening`
- Shift Focus: Audit and ownership of commits `d7642bb`, `4bd3976`, `b2d708f`, `46ddc93`; live desktop telemetry on Windows hardware; UIPI elevation boundary discovery; clipboard protection and candidate gating.

## Actions & Architectural Decisions
1. **Ownership & Review of External Commits (`d7642bb`, `b2d708f`)**:
   - Commits introduced `is_foreground_window` gating and `Ctrl+L` (`antigravity.toggleChatFocus`) invocation for Antigravity IDE.
   - Refined `is_foreground_window` to support `wintypes.HWND` / int types safely and check root window ancestor (`GA_ROOT = 2`) so nested panel focus within the IDE window is correctly recognized without leaking keystrokes outside the application.
   - Moved `set_clipboard_text(prompt_text)` in `submit_to_antigravity_chat` to execute *only after* window focus is confirmed. This guarantees that if focus fails, the user's existing system clipboard is never overwritten.
2. **Window Selection & Standalone Fallback Gating (`desktop/app.py`)**:
   - Analyzed `_focus_antigravity()` behavior: `ide_candidates or candidates` previously fell back to the standalone `Antigravity.exe` app when `Antigravity IDE.exe` was closed.
   - Implemented `ANTIGRAVITY_TARGET_APP` environment variable defaulting to `"ide"` when `Antigravity IDE` is installed on the machine. This ensures that when the IDE is closed, the system strictly fails closed (`return None, None`), announcing `"I couldn't focus Antigravity, so nothing was typed"` rather than inadvertently typing into background `Antigravity.exe` processes.
3. **Live Desktop Telemetry & Findings**:
   - **Case 3c (IDE closed, standalone running):** Before the fix, `_focus_antigravity` selected standalone `Antigravity.exe` (PID 17332) and clicked coordinates. With the fix, closing `Antigravity IDE.exe` cleanly triggers the fail-closed path, returning `None, None` without typing or clobbering the clipboard. Verified live.
   - **UIPI (User Interface Privilege Isolation) Discovery:** Discovered `Antigravity IDE.exe` has `~ RUNASADMIN` configured in `HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers`. When an IDE runs elevated, non-elevated Python processes cannot inject synthetic keystrokes (`keybd_event` dropped by Windows UIPI). Recommendation: Clear the `~ RUNASADMIN` compatibility flag on `Antigravity IDE.exe` so both processes run at standard user integrity. Do not run `desktop/app.py` as Administrator.
   - **Case 3a & 3b (Editor tab & Terminal):** **UNVERIFIED** (Live execution not observed). Synthetic keystrokes were dropped by Windows UIPI due to the elevated IDE process. Live verification deferred until the owner clears the `~ RUNASADMIN` compatibility flag and restarts the IDE.

## Empirical Verification
- Desktop Test Suite: **24 passed, 1 skipped** in `0.17s` (`pytest desktop/tests/`).
- Cloud Relay Test Suite: **7 passed** in `0.93s` (`pytest relay/test_relay.py`).
- SDCS Verification: AST Topology (Gate T), Cartography (Gate M), Working Memory Budget (Gate S: 253 / 350 tokens), Cache Invariance (Gate C) all passing 100%.
