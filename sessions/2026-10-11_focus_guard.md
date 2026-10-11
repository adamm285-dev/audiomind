# 2026-10-11: Keystroke focus guard

## Work completed
- `desktop/app.py`: `submit_to_antigravity_chat` now returns bool and sends no keystrokes unless the Antigravity window was found and is the foreground window, checked after focusing and again right before Ctrl+A/Ctrl+V/Enter. Added `is_foreground_window()`.
- Remote dispatch path: a failed paste clears the pending dispatch and ACKs `FAILED` ("Nothing was typed").
- Voice path: a failed paste is announced with a spoken message.
- Tests: 4 new cases in `desktop/tests/test_remote_listener_security.py` (window missing, focus not taken, focus stolen after click, happy path). They fail against the pre-fix code.

## Why
Before this fix, select-all + paste (+ Enter on auto-submit) ran even when focusing failed, so keystrokes could replace a focused editor/document or execute in a terminal.

## Verification
- Desktop: 19 passed, 1 skipped. Relay: 7 passed. `sdcs verify --all`: PASSED.

## Residual risk
- The chat-box click is still a coordinate guess inside the IDE; a miss lands in the editor (recoverable with Ctrl+Z). Long-term: submit via `agy` CLI instead of synthetic input.

## Next
- Fresh public repo + push, then delete the old private repo (ghost commit `7050c86`).

## Addendum: Ctrl+L chat focus
- Verified in the installed Antigravity IDE (`workbench.desktop.main.js`): `antigravity.toggleChatFocus` ("Open Chat with Agent") is bound to Ctrl+L (`primary:2090`, `when: !chatFocus`). It is on the integrated terminal's skip-shell list, and the user has no keybinding overrides.
- `_focus_antigravity` now prefers `Antigravity IDE.exe` over the standalone `Antigravity.exe` (both installed; previously it picked whichever window was largest) and records `_focused_is_ide`.
- IDE: Ctrl+L replaces the coordinate click. Standalone app: the click is kept as a fallback (no verified shortcut).
- Tests: 3 new cases (Ctrl+L order and no click, abort on focus loss, standalone fallback). Desktop: 22 passed, 1 skipped.
- Not yet verified live: run one voice command with focus in the editor, and one with focus in the integrated terminal.
