"""
Unit and Regression Tests for Voice Command Firewall & AST Lexer.
Verifies defense against malware injection, path traversal, and ensures zero false-positives
on words like 'model', 'delegate', 'delivery'.
"""

import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import pytest
from desktop.firewall.lexer import CommandLexer, TokenType
from desktop.firewall.policy import CommandFirewall, SecurityTier

@pytest.fixture
def firewall():
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return CommandFirewall(workspace_root=workspace_root)

# --- Test 1: Substring Non-Collision Proof ---
def test_no_false_positives_on_similar_words(firewall):
    """Prove that words like 'model', 'delegate', 'delivery' don't trigger 'del'."""
    safe_prompts = [
        "check the gemini nano model status",
        "delegate this task to the research subagent",
        "verify the food delivery test scenario",
        "show the delightful onboarding animation",
        "format_string is defined in utils",
    ]
    for prompt in safe_prompts:
        verdict = firewall.evaluate(prompt)
        assert verdict.allowed is True, f"Failed on safe prompt: {prompt} (Reason: {verdict.reason})"
        assert verdict.tier in [SecurityTier.GREEN, SecurityTier.YELLOW]

# --- Test 2: Destructive Attack Interception ---
def test_destructive_commands_intercepted(firewall):
    """Prove that deletion, formatting, and forced removals are blocked (RED tier)."""
    malicious_prompts = [
        "delete all files in the directory",
        "del /f scripts/launch_cockpit.ps1",
        "rm -rf build/",
        "format C:",
        "drop table users",
        "truncate table session_logs",
        "erase the evidence folder"
    ]
    for prompt in malicious_prompts:
        verdict = firewall.evaluate(prompt)
        assert verdict.allowed is False, f"Did not block malicious prompt: {prompt}"
        assert verdict.tier == SecurityTier.RED

# --- Test 3: Path Traversal & System Root Boundary Enforcement ---
def test_path_traversal_and_system_roots_blocked(firewall):
    """Prove that paths outside workspace or inside system directories are blocked."""
    boundary_attacks = [
        "inspect C:\\Windows\\System32\\cmd.exe",
        "read C:\\Users\\DefaultUser\\AppData\\Roaming\\credentials.json",
        "open ..\\..\\Windows\\win.ini",
        "view HKLM\\Software\\Policies",
        "modify .githooks\\pre-commit",
    ]
    for prompt in boundary_attacks:
        verdict = firewall.evaluate(prompt)
        assert verdict.allowed is False, f"Did not block path escape: {prompt}"
        assert verdict.tier == SecurityTier.RED

# --- Test 4: Dangerous Windows Keywords Blocked ---
def test_windows_system_keywords_blocked(firewall):
    """Prove that registry edits, network manipulation, and privilege escalation are blocked."""
    system_attacks = [
        "reg add HKLM\\Software\\Test",
        "netsh advfirewall set allprofiles state off",
        "powershell -enc aQB4A...",
        "runas /user:Administrator cmd",
    ]
    for prompt in system_attacks:
        verdict = firewall.evaluate(prompt)
        assert verdict.allowed is False, f"Did not block system keyword: {prompt}"
        assert verdict.tier == SecurityTier.RED

# --- Test 5: Legitimate Dev & Diagnostic Commands Allowed ---
def test_legitimate_dev_workflow_authorized(firewall):
    """Verify that daily developer actions pass smoothly."""
    dev_prompts = [
        ("check the battery on both phones", SecurityTier.GREEN),
        ("show connected adb devices", SecurityTier.GREEN),
        ("inspect the latest git diff", SecurityTier.GREEN),
        ("build the flutter apk for the new phone", SecurityTier.YELLOW),
        ("launch the dual cockpit script", SecurityTier.YELLOW),
        ("commit the changes to the repo", SecurityTier.YELLOW),
    ]
    for prompt, expected_tier in dev_prompts:
        verdict = firewall.evaluate(prompt)
        assert verdict.allowed is True, f"Blocked legitimate dev prompt: {prompt}"
        assert verdict.tier == expected_tier


# --- Test 6: Sibling Directory Prefix Traversal Bug ---
def test_path_prefix_traversal_blocked():
    """Prove that sibling directories sharing a common prefix (e.g. workspace-evil vs workspace) are blocked."""
    fw = CommandFirewall(workspace_root=r"C:\projects\my-app")
    
    # Absolute sibling prefix collision: C:\projects\my-app-evil\file.txt
    verdict_abs = fw.evaluate(r"read C:\projects\my-app-evil\exploit.py")
    assert verdict_abs.allowed is False, "Failed to block absolute sibling prefix collision"
    assert verdict_abs.tier == SecurityTier.RED
    assert "Directory traversal" in verdict_abs.reason

    # Relative traversal into sibling: ..\my-app-evil\file.txt
    verdict_rel = fw.evaluate(r"inspect ..\my-app-evil\secret.json")
    assert verdict_rel.allowed is False, "Failed to block relative sibling traversal"
    assert verdict_rel.tier == SecurityTier.RED
    assert "Directory traversal" in verdict_rel.reason
