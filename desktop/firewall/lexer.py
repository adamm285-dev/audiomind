"""
AST-based Lexer and Tokenizer for Voice Command Security Firewall.
Conforms to SPEC-001 & Antigravity Defense-in-Depth Architecture.
Prevents naive substring false positives (e.g., 'del' inside 'model' or 'delivery').
"""

import re
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

class TokenType(Enum):
    VERB = auto()
    PATH = auto()
    FLAG = auto()
    SYSTEM_KEYWORD = auto()
    IDENTIFIER = auto()
    TEXT = auto()

@dataclass
class Token:
    type: TokenType
    value: str
    original: str
    is_destructive: bool = False
    is_system_restricted: bool = False

# Known destructive verbs when used as action words
DESTRUCTIVE_VERBS = {
    "delete", "remove", "del", "rm", "rmdir", "erase", "format", 
    "drop", "truncate", "wipe", "destroy", "kill", "purge", "uninstall"
}

# Safe diagnostic / read verbs
SAFE_VERBS = {
    "check", "show", "get", "status", "list", "read", "view", "inspect",
    "diff", "test", "audit", "verify", "diagnose", "battery", "pull"
}

# Mutation / build verbs (Yellow tier)
MUTATION_VERBS = {
    "build", "run", "launch", "compile", "commit", "push", "install", 
    "start", "restart", "deploy", "update", "generate", "create", "add"
}

# Dangerous Windows system keywords & utilities
DANGEROUS_SYSTEM_KEYWORDS = {
    "reg", "regedit", "netsh", "vssadmin", "bcdedit", "diskpart",
    "powershell -enc", "invoke-expression", "iex", "runas", "format.com",
    "cipher", "attrib", "takeown", "icacls", "schtasks", "sc.exe"
}

# Sensitive Windows paths that must never be targeted by voice
RESTRICTED_PATH_PATTERNS = [
    re.compile(r"^[a-zA-Z]:\\windows", re.IGNORECASE),
    re.compile(r"^[a-zA-Z]:\\program files", re.IGNORECASE),
    re.compile(r"appdata", re.IGNORECASE),
    re.compile(r"system32", re.IGNORECASE),
    re.compile(r"hklm", re.IGNORECASE),
    re.compile(r"hkcu", re.IGNORECASE),
    re.compile(r"\.git\\hooks", re.IGNORECASE),
    re.compile(r"\.githooks", re.IGNORECASE),
]

class CommandLexer:
    """Parses a voice/text utterance into structured tokens with semantic risk metadata."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = os.path.normpath(workspace_root or os.getcwd()).lower()

    def tokenize(self, utterance: str) -> List[Token]:
        tokens: List[Token] = []
        raw_words = utterance.strip().split()
        if not raw_words:
            return tokens

        i = 0
        while i < len(raw_words):
            word = raw_words[i]
            lower_word = word.lower().strip(",.!?\"'();")

            # Check multi-word system phrases (e.g., 'powershell -enc', 'reg add')
            if i + 1 < len(raw_words):
                two_word = f"{lower_word} {raw_words[i+1].lower()}"
                if two_word in DANGEROUS_SYSTEM_KEYWORDS:
                    tokens.append(Token(
                        type=TokenType.SYSTEM_KEYWORD,
                        value=two_word,
                        original=f"{word} {raw_words[i+1]}",
                        is_system_restricted=True
                    ))
                    i += 2
                    continue

            # 1. System Keywords
            if lower_word in DANGEROUS_SYSTEM_KEYWORDS:
                tokens.append(Token(
                    type=TokenType.SYSTEM_KEYWORD,
                    value=lower_word,
                    original=word,
                    is_system_restricted=True
                ))
            # 2. Command Flags (e.g. -f, /s, --force)
            elif re.match(r"^[-/]{1,2}[a-zA-Z0-9]+", word):
                is_force = lower_word in ["-f", "--force", "/f", "-rf", "/s", "/q"]
                tokens.append(Token(
                    type=TokenType.FLAG,
                    value=lower_word,
                    original=word,
                    is_destructive=is_force
                ))
            # 3. Path detection (Windows drive letters, backslashes, forward slashes, or extensions)
            elif (re.match(r"^[a-zA-Z]:[\\/]", word) or 
                  "\\" in word or "/" in word or 
                  re.search(r"\.(exe|bat|ps1|dll|sys|vbs|sh)$", lower_word)):
                is_restricted = any(p.search(word) for p in RESTRICTED_PATH_PATTERNS)
                tokens.append(Token(
                    type=TokenType.PATH,
                    value=word,
                    original=word,
                    is_system_restricted=is_restricted
                ))
            # 4. Strict Discrete Verb Matching (Whole-word only)
            elif lower_word in DESTRUCTIVE_VERBS:
                tokens.append(Token(
                    type=TokenType.VERB,
                    value=lower_word,
                    original=word,
                    is_destructive=True
                ))
            elif lower_word in SAFE_VERBS or lower_word in MUTATION_VERBS:
                tokens.append(Token(
                    type=TokenType.VERB,
                    value=lower_word,
                    original=word,
                    is_destructive=False
                ))
            # 5. Normal text / identifier (e.g., 'model', 'delegate', 'delivery')
            else:
                tokens.append(Token(
                    type=TokenType.TEXT,
                    value=lower_word,
                    original=word,
                    is_destructive=False
                ))
            i += 1

        return tokens
