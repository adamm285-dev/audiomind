"""
Semantic Command Firewall & Policy Engine.
Conforms to SPEC-001 Pillar 1 (The Law) & Antigravity Defense-in-Depth Architecture.
Evaluates tokens to classify into Green, Yellow, or Red tier and strictly bounds execution.

SECURITY NOTICE:
The Command Firewall is an advisory heuristic guard against accidental commands during
hands-free operation, NOT an absolute security boundary against malicious or adversarial LLM prompts.
The Antigravity IDE agent's own workspace containment and approval settings provide the authoritative control.
"""

import os
import hashlib
import hmac
import time
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional
try:
    from desktop.firewall.lexer import CommandLexer, Token, TokenType
except ImportError:
    from firewall.lexer import CommandLexer, Token, TokenType

class SecurityTier(Enum):
    GREEN = auto()    # Read-only, diagnostics, audits (Instant auto-execution)
    YELLOW = auto()   # Safe workspace mutations, builds, testing (Logged execution)
    RED = auto()      # Destructive, administrative, or out-of-bounds (BLOCKED / Physical confirmation)

RiskTier = SecurityTier

@dataclass
class FirewallVerdict:
    tier: SecurityTier
    allowed: bool
    reason: str
    tokens: List[Token]
    sanitized_prompt: str
    audit_hash: str
    timestamp: float

class CommandFirewall:
    """Enforces zero-trust execution boundaries for spoken/incoming commands."""

    def __init__(self, workspace_root: Optional[str] = None, secret_key: Optional[bytes] = None):
        self.workspace_root = os.path.realpath(workspace_root or os.getcwd()).lower()
        self.lexer = CommandLexer(workspace_root=self.workspace_root)
        self.secret_key = secret_key or os.urandom(32)

    def evaluate(self, raw_command: str) -> FirewallVerdict:
        ts = time.time()
        tokens = self.lexer.tokenize(raw_command)

        # Generate HMAC audit hash for non-repudiation
        msg = f"{raw_command}|{ts}".encode("utf-8")
        audit_hash = hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()

        if not tokens:
            return FirewallVerdict(
                tier=SecurityTier.GREEN,
                allowed=True,
                reason="Empty command utterance.",
                tokens=tokens,
                sanitized_prompt="",
                audit_hash=audit_hash,
                timestamp=ts
            )

        # 1. Check for Hard-Red System Violations
        for tok in tokens:
            if tok.type == TokenType.SYSTEM_KEYWORD:
                return FirewallVerdict(
                    tier=SecurityTier.RED,
                    allowed=False,
                    reason=f"Restricted system keyword detected: '{tok.value}'. Voice shell elevation is strictly prohibited.",
                    tokens=tokens,
                    sanitized_prompt=raw_command,
                    audit_hash=audit_hash,
                    timestamp=ts
                )

        # 2. Check for Path Boundary Violations
        for tok in tokens:
            if tok.type == TokenType.PATH:
                if tok.is_system_restricted:
                    return FirewallVerdict(
                        tier=SecurityTier.RED,
                        allowed=False,
                        reason=f"Path targets protected system location: '{tok.value}'.",
                        tokens=tokens,
                        sanitized_prompt=raw_command,
                        audit_hash=audit_hash,
                        timestamp=ts
                    )
                # Resolve relative or absolute path to check workspace containment using commonpath
                try:
                    resolved = os.path.realpath(os.path.join(self.workspace_root, tok.value)).lower()
                    try:
                        common = os.path.commonpath([self.workspace_root, resolved]).lower()
                    except ValueError:
                        # Raised on Windows when paths are on different drives
                        common = ""

                    if common != self.workspace_root:
                        return FirewallVerdict(
                            tier=SecurityTier.RED,
                            allowed=False,
                            reason=f"Directory traversal / out-of-workspace boundary violation: '{tok.value}' -> '{resolved}'.",
                            tokens=tokens,
                            sanitized_prompt=raw_command,
                            audit_hash=audit_hash,
                            timestamp=ts
                        )
                except Exception as e:
                    return FirewallVerdict(
                        tier=SecurityTier.RED,
                        allowed=False,
                        reason=f"Malformed path argument: '{tok.value}' ({str(e)}).",
                        tokens=tokens,
                        sanitized_prompt=raw_command,
                        audit_hash=audit_hash,
                        timestamp=ts
                    )

        # 3. Check for Destructive Operations (RED TIER)
        has_destructive_verb = any(t.is_destructive and t.type == TokenType.VERB for t in tokens)
        has_destructive_flag = any(t.is_destructive and t.type == TokenType.FLAG for t in tokens)

        if has_destructive_verb or has_destructive_flag:
            bad_tokens = [t.value for t in tokens if t.is_destructive]
            return FirewallVerdict(
                tier=SecurityTier.RED,
                allowed=False,
                reason=f"Destructive action or flags detected: {bad_tokens}. Requires physical human keyboard confirmation.",
                tokens=tokens,
                sanitized_prompt=raw_command,
                audit_hash=audit_hash,
                timestamp=ts
            )

        # 4. Check for Safe Workspace Mutations (YELLOW TIER)
        mutation_verbs = {"build", "run", "launch", "compile", "commit", "push", "install", "start", "restart", "deploy"}
        has_mutation = any(t.type == TokenType.VERB and t.value in mutation_verbs for t in tokens)

        if has_mutation:
            return FirewallVerdict(
                tier=SecurityTier.YELLOW,
                allowed=True,
                reason="Safe workspace mutation / dev action. Authorized with flight recorder logging.",
                tokens=tokens,
                sanitized_prompt=raw_command,
                audit_hash=audit_hash,
                timestamp=ts
            )

        # 5. Default: Informational / Read-Only / Diagnostic (GREEN TIER)
        return FirewallVerdict(
            tier=SecurityTier.GREEN,
            allowed=True,
            reason="Read-only query, test, or diagnostic. Authorized for instant execution.",
            tokens=tokens,
            sanitized_prompt=raw_command,
            audit_hash=audit_hash,
            timestamp=ts
        )
