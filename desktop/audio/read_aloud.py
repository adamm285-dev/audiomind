"""
Anti Read-Aloud Engine & Active Transcript Watcher.
Monitors the Antigravity conversation transcript and automatically speaks
new assistant responses out loud using Edge-TTS Ava @ 48kHz stereo.
"""
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import re
import json
import glob
import time
import threading
from typing import Optional, Callable
try:
    from desktop.audio.tts import speak, normalize_phonetics
except ImportError:
    from audio.tts import speak, normalize_phonetics

def clean_markdown_for_speech(text: str) -> str:
    """Cleans raw markdown, code blocks, diagrams, and formatting into fluid conversational speech."""
    if not text:
        return ""

    # 1. Remove code blocks entirely (both 4-backtick and 3-backtick)
    text = re.sub(r'````[\s\S]*?````', '', text)
    text = re.sub(r'```[\s\S]*?```', '', text)

    # 2. Remove LaTeX math blocks and inline math
    text = re.sub(r'\$\$[\s\S]*?\$\$', '', text)
    text = re.sub(r'\\\[[\s\S]*?\\\]', '', text)
    text = re.sub(r'\\\([^\)]+\\\)', '', text)
    text = re.sub(r'\$[^$\n]+\$', '', text)

    # 3. Remove markdown table separator rows (e.g. |:---|:---|)
    text = re.sub(r'^\s*\|?[\s\-:|]+\|?\s*$', '', text, flags=re.MULTILINE)

    # 4. Remove blockquote / callout markers (> [!NOTE], > [!IMPORTANT], etc.)
    text = re.sub(r'^\s*>\s*(\[![\w\s]+\])?\s*', '', text, flags=re.MULTILINE)

    # 5. Remove inline code backticks: `variable` -> variable
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # 6. Clean markdown links: [Title](url) -> Title (strip #L10-L20)
    def clean_link(match):
        label = match.group(1)
        label = re.sub(r'#L\d+(-L\d+)?', '', label)
        return label
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', clean_link, text)

    # 7. Remove raw URLs (including URLs inside parentheses)
    text = re.sub(r'\(\s*https?://[^\)]*\)', '', text)
    text = re.sub(r'https?://[^\s\)]+', '', text)
    text = re.sub(r'file:///[^\s\)]+', '', text)

    # 7b. Clean dangling empty parentheses or leftover connector words from stripped URLs
    text = re.sub(r'\(\s*(?:and|or)?\s*\)', '', text)
    text = re.sub(r'\(\s*(?:and|or)\s+', '(', text)
    text = re.sub(r'\s+(?:and|or)\s*\)', ')', text)
    text = re.sub(r'\(\s*\)', '', text)

    # 8. Remove ASCII / box diagrams and table pipes
    text = re.sub(r'[┌┐└┘├┤┬┴┼─│━┃┏┓┗┛┣┫┳┻╋►▼▲◄|]+', ' ', text)

    # 9. Remove markdown headers (#, ##, ###)
    text = re.sub(r'#+\s*', '', text)

    # 10. Remove bold/italic markers (*, _)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)

    # 11. Convert bullet points and numbered lists to natural clauses
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # 12. Clean horizontal rules (--- or ***)
    text = re.sub(r'[-*_]{3,}', '', text)

    # 13. Clean HTML tags and transcript truncation tags
    text = re.sub(r'<truncated\s+\d+\s+bytes>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)

    # 14. Ensure lines ending without punctuation get a period for natural speech pauses
    text = re.sub(r'([^.!?:\s])\n(?!\n)', r'\1. ', text)
    text = re.sub(r'([^.!?:\s])\n\n+', r'\1.\n\n', text)
    # Convert single newlines inside paragraphs to spaces (soft wrap), but preserve paragraph breaks (\n\n)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+([.,!?:])', r'\1', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()

    # 15. Normalize phonetics ('Anti' -> 'Ante' for /æn.ti/)
    text = normalize_phonetics(text)

    return text

def extract_visible_blocks_from_markdown(raw_text: str) -> list[str]:
    """
    Converts raw assistant Markdown into contiguous strings that match
    Antigravity's rendered HTML chat DOM for Ctrl+F (FindInPage).
    Non-prose elements (code blocks, math, URLs, dividers) become block breaks
    so phrases never stitch words across hidden elements.
    """
    if not raw_text or not raw_text.strip():
        return []

    text = raw_text

    # 1. Replace fenced code blocks with block breaks
    text = re.sub(r'````[\s\S]*?````', '\n', text)
    text = re.sub(r'```[\s\S]*?```', '\n', text)

    # 2. Replace display & inline math with block breaks
    text = re.sub(r'\$\$[\s\S]*?\$\$', '\n', text)
    text = re.sub(r'\\\[[\s\S]*?\\\]', '\n', text)
    text = re.sub(r'\\\([^\)]+\\\)', '\n', text)
    text = re.sub(r'(?<!\\)\$[^$\n]+(?<!\\)\$', '\n', text)

    # 3. Convert markdown links [Label](url) to visible Label BEFORE stripping bare URLs
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # 4. Replace bare URLs and file links with block breaks
    text = re.sub(r'\(\s*https?://[^\)]*\)', '\n', text)
    text = re.sub(r'https?://[^\s\)]+', '\n', text)
    text = re.sub(r'file:///[^\s\)]+', '\n', text)

    # 5. Replace truncation/HTML tags with block breaks
    text = re.sub(r'<truncated\s+\d+\s+bytes>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '\n', text)

    # 6. Replace table separator rows, horizontal rules, alert badges, and box/table pipes
    text = re.sub(r'^\s*\|?[\s\-:|]+\|?\s*$', '\n', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*_]{3,}\s*$', '\n', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s*\[![\w\s]+\]\s*', '\n', text, flags=re.MULTILINE)
    text = re.sub(r'[┌┐└┘├┤┬┴┼─│━┃┏┓┗┛┣┫┳┻╋►▼▲◄|]+', '\n', text)

    # 7. Unescape Markdown backslash escapes (e.g. \$100 -> $100)
    text = re.sub(r'\\([\\`*_{}\[\]()#+\-.!$])', r'\1', text)

    # 8. Strip inline formatting wrappers that render contiguously in HTML
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(
        r'(?:^|(?<=[\s(\["\']))_{1,3}([^_\n]+?)_{1,3}(?=$|[\s.,!?:;)\]\'"])',
        r'\1',
        text,
    )
    text = re.sub(r'~~([^~\n]+)~~', r'\1', text)

    blocks = []
    for line in text.split('\n'):
        line = re.sub(r'^\s*>\s*', '', line)
        line = re.sub(r'^\s*#+\s*', '', line)
        line = re.sub(r'^\s*[-*•]\s+', '', line)
        line = re.sub(r'^\s*\d+[\.)]\s+', '', line)
        line = re.sub(r'[ \t]+', ' ', line).strip()
        if line:
            blocks.append(line)

    return blocks

def align_subchunks_to_visible_blocks(sub_chunks: list[str], visible_blocks: list[str]) -> list[list[tuple[int, str]]]:
    """
    Maps each speech sub_chunk in a chapter to a list of (block_id, verbatim_word)
    tuples from visible_blocks so located Ctrl+F phrases stay verbatim.
    """
    if not sub_chunks:
        return []

    def _norm_tok(w: str) -> str:
        low = re.sub(r'\bante\b', 'anti', w.lower())
        return re.sub(r'[^a-z0-9]', '', low)

    flat_vis = [
        (b_idx, word, _norm_tok(word))
        for b_idx, blk in enumerate(visible_blocks)
        for word in blk.split()
        if word.strip()
    ]

    if not flat_vis:
        return [
            [(sc_idx, re.sub(r'\bAnte\b', 'Anti', w)) for w in sc.split() if w.strip()]
            for sc_idx, sc in enumerate(sub_chunks)
        ]

    results: list[list[tuple[int, str]]] = []
    vis_cursor = 0
    n_vis = len(flat_vis)

    for idx, sc in enumerate(sub_chunks):
        if idx == len(sub_chunks) - 1:
            assigned = [(b, w) for b, w, _ in flat_vis[vis_cursor:]]
            if not assigned and flat_vis:
                assigned = [(b, w) for b, w, _ in flat_vis[-min(6, n_vis):]]
            results.append(assigned)
            continue

        sc_norms = [t for t in (_norm_tok(w) for w in sc.split()) if t]
        pos = vis_cursor
        for target_t in sc_norms:
            if pos >= n_vis:
                break
            window_end = min(n_vis, pos + 8)
            found_idx = None
            for k in range(pos, window_end):
                if flat_vis[k][2] == target_t:
                    found_idx = k
                    break
            if found_idx is not None:
                pos = found_idx + 1
            elif (n_vis - pos) > 1:
                pos = min(n_vis, pos + 1)

        assigned = [(b, w) for b, w, _ in flat_vis[vis_cursor:pos]]
        if not assigned and sc_norms and vis_cursor < n_vis:
            end_fallback = min(n_vis, vis_cursor + len(sc_norms))
            assigned = [(b, w) for b, w, _ in flat_vis[vis_cursor:end_fallback]]
            pos = end_fallback
        elif not assigned and sc.strip():
            assigned = [(idx, re.sub(r'\bAnte\b', 'Anti', w)) for w in sc.split() if w.strip()]

        vis_cursor = pos
        results.append(assigned)

    return results

def get_full_content(transcript_path: str, step_index: int) -> Optional[str]:
    """
    If transcript.jsonl has truncated content (due to Antigravity's compact transcript logger),
    retrieves the complete unabridged content from transcript_full.jsonl.
    """
    full_path = transcript_path.replace("transcript.jsonl", "transcript_full.jsonl")
    if not os.path.exists(full_path):
        return None
    try:
        file_size = os.path.getsize(full_path)
        # Search backwards from the end of transcript_full.jsonl in 512KB chunks
        chunk_size = 512 * 1024
        bytes_checked = 0
        max_bytes_to_check = min(file_size, 10 * 1024 * 1024)  # check up to 10MB back
        while bytes_checked < max_bytes_to_check:
            read_size = min(chunk_size, max_bytes_to_check - bytes_checked)
            offset = max(0, file_size - bytes_checked - read_size)
            with open(full_path, "rb") as f:
                f.seek(offset)
                raw = f.read(read_size + 8192).decode("utf-8", errors="ignore")
            for line in reversed(raw.splitlines()):
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                    if d.get("step_index") == step_index:
                        return d.get("content", "")
                except Exception:
                    continue
            bytes_checked += read_size
    except Exception as e:
        print(f"[!] Error fetching full content from {full_path}: {e}")
    return None

def truncate_for_audio_summary(cleaned_text: str, max_words: int = 3500) -> str:
    """
    Ensures spoken assistant responses are coherent, comprehensive, and non-repetitive.
    If the response is within max_words (default 3500), speaks the full text.
    If the response exceeds max_words, preserves up to max_words while keeping
    clean sentence boundaries and concluding action items.
    """
    words = cleaned_text.split()
    if len(words) <= max_words:
        return cleaned_text

    # Keep a comprehensive opening budget (up to max_words - 250) plus the concluding section (~250 words)
    head_budget = max(400, max_words - 250)
    tail_budget = min(250, len(words) - head_budget)

    head_text = ' '.join(words[:head_budget])
    last_p = max(head_text.rfind('.'), head_text.rfind('!'), head_text.rfind('?'))
    if last_p > 100:
        head_text = head_text[:last_p + 1]

    if tail_budget > 40:
        tail_text = ' '.join(words[-tail_budget:])
        first_p = min(
            [idx for idx in (tail_text.find('. '), tail_text.find('! '), tail_text.find('? ')) if idx != -1] or [-1]
        )
        if first_p != -1 and first_p < len(tail_text) - 20:
            tail_text = tail_text[first_p + 2:].strip()
        if tail_text and tail_text not in head_text:
            return f"{head_text}\n\n{tail_text}"

    return head_text


_VERIFICATION_TITLE_VOCAB = frozenset({
    "verification", "re-verification", "and", "or", "of", "for", "in", "on", "to",
    "post", "pre", "the", "all", "final", "latest", "observed", "full",
    "full-suite", "suite", "independent", "offline", "online", "anti-bias",
    "live", "end-to-end", "e2e", "automated", "unit", "integration",
    "empirical", "standing", "gate", "gates", "test", "tests", "testing",
    "build", "lint", "typecheck", "validation", "sdcs", "check", "checks",
    "receipt", "receipts", "report", "reports", "result", "results",
    "summary", "status", "state", "scorecard", "telemetry", "matrix",
    "log", "logs", "output", "close-out", "closeout", "governance", "git",
    "repository", "repo", "memory", "hud", "commit", "commits",
    "documentation", "docs", "artifacts", "artifact", "updated", "cloud",
    "bundles", "bundle", "post-edit", "post-final", "regression", "smoke",
    "sanity", "baseline", "daemon", "local", "cleanup",
})

_VERIFICATION_EXCLUSIONS_RE = re.compile(
    r"\b(?:plan|plans|planning|strategy|strategies|architecture|design|"
    r"mirage|story|guide|tutorial|protocol|workflow|pipeline|framework|"
    r"engine|module|layer|hook|hooks|tweet|tweets|thread|"
    r"account\s+verification|email\s+verification|phone\s+verification|"
    r"identity\s+verification|kyc|two-factor|2fa|auth\s+verification|"
    r"signature\s+verification|token\s+verification|webhook\s+verification|"
    r"ssl\s+verification|certificate\s+verification|cyber\s+verification)\b"
)

_VERIFICATION_PREFIX_EXCLUSIONS_RE = re.compile(
    r"^(?:what\s+(?:was|is|we|changed)|how\s+(?:to|we|it)|why\s+|when\s+|"
    r"where\s+|component\s+\d+|option\s+[a-z0-9]\b)"
)

_CLOSEOUT_SUBHEADING_RE = re.compile(
    r"\b(?:close-?out|closeout|handoff|next\s+steps?|takeaways?|remaining|open\s+questions?)\b"
)

_WRAPUP_PROMPT_RE = re.compile(
    r"\b(?:would you like|let me know|shall i|want me to|do you want|"
    r"if you(?:'d| would)?\s+like|if you want|next step|"
    r"whenever you(?:'re| are) ready|feel free|ready for your|"
    r"ready to commit|ready for review|uncommitted|working tree|"
    r"left uncommitted|pushed to|committed to|live daemon|"
    r"restarted and active|now active|try saying|give it a try)\b",
    re.IGNORECASE,
)

_RAW_VERDICT_RE = re.compile(
    r"^(?:all\s+\d+(?:/\d+)?\s+(?:\w+\s+){0,3}passed|\d+/\d+\s+(?:tests?\s+)?passed|"
    r"pytest\b|passed\s+in\s+\d|0\s+(?:errors?|warnings?|failures?|matches?)\b|"
    r"exit(?:ed)?\s+(?:code\s+)?0\b|status:\s*verified\b|no\s+regressions?\b)",
    re.IGNORECASE,
)


def _compute_fenced_line_indices(lines: list[str]) -> set[int]:
    """
    Returns line indices inside matched Markdown code fences while ignoring
    orphaned closing fences left behind by '<truncated ...>' log markers.
    """
    fenced: set[int] = set()
    open_idx: Optional[int] = None
    open_char = ""
    open_len = 0
    after_truncation_unpaired = False

    for idx, line in enumerate(lines):
        if "<truncated " in line:
            open_idx = None
            open_char = ""
            open_len = 0
            after_truncation_unpaired = True

        if open_idx is None:
            m_open = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
            if m_open:
                fence_tok, info_str = m_open.group(1), m_open.group(2).strip()
                if after_truncation_unpaired and not info_str:
                    after_truncation_unpaired = False
                    continue
                after_truncation_unpaired = False
                open_idx = idx
                open_char = fence_tok[0]
                open_len = len(fence_tok)
            elif after_truncation_unpaired and re.match(r"^\s*#{1,6}\s+\S", line):
                after_truncation_unpaired = False
        else:
            if re.match(rf"^\s*{re.escape(open_char)}{{{open_len},}}\s*$", line):
                fenced.update(range(open_idx, idx + 1))
                open_idx = None
                open_char = ""
                open_len = 0

    return fenced


def _normalize_header_title(raw_title: str) -> str:
    """Normalizes Markdown heading/bold title text for classification."""
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", raw_title or "")
    s = s.replace("`", "").replace("*", "").replace("_", "").replace("~", "")
    s = re.sub(r"^[^\w\s]+", "", s).strip()
    s = re.sub(r"^(?:step\s+)?\d+(?:\.\d+)*[.):\-]?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^[^\w\s]+", "", s).strip()
    s = s.replace("&", " and ")
    s = s.rstrip(":").strip().lower()
    return re.sub(r"\s+", " ", s)


def _is_verification_section_title(raw_title: str) -> bool:
    """Returns True only when a header names a Verification Report section."""
    norm = _normalize_header_title(raw_title)
    if not re.search(r"\b(?:re-?)?verification\b", norm):
        return False
    if _VERIFICATION_EXCLUSIONS_RE.search(norm):
        return False
    if _VERIFICATION_PREFIX_EXCLUSIONS_RE.search(norm):
        return False

    core = re.sub(r"\([^)]*\)", " ", norm)
    core = re.sub(r"\bacross\s+(?:all|\d+)\b.*$", "", core)
    core = re.sub(r"[,+/:]+", " ", core)
    core = re.sub(r"\s+", " ", core).strip()
    if not core:
        return False

    tokens = [tok.strip(".'\"") for tok in core.split() if tok.strip(".'\"")]
    if not tokens:
        return False

    for tok in tokens:
        if tok in _VERIFICATION_TITLE_VOCAB:
            continue
        subparts = [p for p in tok.split("-") if p]
        if len(subparts) > 1 and all(p in _VERIFICATION_TITLE_VOCAB for p in subparts):
            continue
        return False
    return True


def _classify_verification_header(line: str) -> Optional[tuple[str, int, str]]:
    """Detects Markdown headings, standalone bold headers, and header list items for verification sections."""
    m_hd = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
    if m_hd and _is_verification_section_title(m_hd.group(2)):
        return ("md_heading", len(m_hd.group(1)), _normalize_header_title(m_hd.group(2)))

    m_bld = re.match(r"^\s*\*\*([^*]+?)\*\*\s*:?\s*$", line)
    if m_bld and _is_verification_section_title(m_bld.group(1)):
        return ("bold_header", 7, _normalize_header_title(m_bld.group(1)))

    m_lst = re.match(r"^ ?(?:[-*+]|\d+[.)])\s+\*\*([^*]+?)\*\*\s*:?\s*$", line)
    if m_lst and _is_verification_section_title(m_lst.group(1)):
        return ("list_header", 8, _normalize_header_title(m_lst.group(1)))

    return None


def _find_verification_section_end(
    lines: list[str],
    start_idx: int,
    kind: str,
    level: int,
    fenced_lines: set[int],
) -> int:
    """Finds the exclusive end line index for a matched Verification section."""
    for j in range(start_idx + 1, len(lines)):
        if j in fenced_lines:
            continue
        line = lines[j]
        if re.match(r"^\s*(?:---+|\*\*\*+|___+)\s*$", line):
            return j

        m_hd = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
        if m_hd:
            if kind != "md_heading":
                return j
            sub_lvl = len(m_hd.group(1))
            if sub_lvl <= level:
                return j
            sub_norm = _normalize_header_title(m_hd.group(2))
            if not _is_verification_section_title(m_hd.group(2)) and _CLOSEOUT_SUBHEADING_RE.search(sub_norm):
                return j
            continue

        if kind == "list_header":
            if line.strip() and (len(line) - len(line.lstrip(" "))) <= 1:
                return j
        elif kind == "bold_header":
            m_bld = re.match(r"^\s*\*\*([^*]+?)\*\*\s*:?\s*$", line)
            if m_bld:
                bnorm = _normalize_header_title(m_bld.group(1))
                if not _is_verification_section_title(m_bld.group(1)) and re.search(
                    r"\b(?:close-?out|closeout|handoff|next\s+steps?|summary|takeaways?)\b", bnorm
                ):
                    return j
            if (
                j > start_idx + 1
                and not lines[j - 1].strip()
                and line.strip()
                and (len(line) - len(line.lstrip(" ")) == 0)
                and not re.match(r"^(?:[-*+]|\d+[.)]|\||>|\*\*)", line.strip())
            ):
                return j

    return len(lines)


def _extract_embedded_closeout_blocks(
    lines: list[str],
    start_idx: int,
    end_idx: int,
    kind: str,
    level: int,
    parent_norm: str,
    fenced_lines: set[int],
) -> tuple[list[list[str]], set[int]]:
    """Extracts any nested Close-Out bullet/bold sub-blocks inside a skipped Verification section."""
    parent_has_closeout = bool(re.search(r"\b(?:close-?out|closeout|handoff|documentation|commit)\b", parent_norm))
    preserved: list[list[str]] = []
    captured: set[int] = set()

    k = start_idx + 1
    while k < end_idx:
        if k in fenced_lines:
            k += 1
            continue
        line = lines[k]
        indent = len(line) - len(line.lstrip(" "))
        m_bul = re.match(r"^(\s*)(?:[-*+]|\d+[.)])\s+(\*\*([^*]+?)\*\*(?::)?)(.*)$", line) if indent <= 2 else None
        m_bld = re.match(r"^(\s*)(\*\*([^*]+?)\*\*\s*:?\s*)$", line) if (m_bul is None and indent <= 2) else None
        if not m_bul and not m_bld:
            k += 1
            continue

        bold_label = m_bul.group(3) if m_bul else m_bld.group(3)
        b_norm = _normalize_header_title(bold_label)
        is_closeout = bool(
            re.search(r"\b(?:close-?out|closeout|handoff|7-pillar|pillar\s+sync|six-step\s+close)\b", b_norm)
            and not re.search(r"\bpre-close-?out\b", b_norm)
        )
        if not is_closeout and parent_has_closeout:
            is_closeout = bool(
                re.search(r"\b(?:sdcs\s+gates?|updated\s+docs|pillars?|state\s+lock|blackboard|flight\s+recorder)\b", b_norm)
            )
        if not is_closeout:
            k += 1
            continue

        block: list[str] = []
        captured.add(k)
        if m_bul and kind == "md_heading":
            hashes = "#" * min(level, 4)
            bold_head = m_bul.group(2)
            trailing_inline = m_bul.group(4).strip()
            block.append(f"{hashes} {bold_head}")
            if trailing_inline:
                block.append(trailing_inline)
        else:
            block.append(line)

        m = k + 1
        while m < end_idx:
            if m in fenced_lines:
                block.append(lines[m])
                captured.add(m)
                m += 1
                continue
            sub_line = lines[m]
            if not sub_line.strip():
                next_non_blank = m + 1
                while next_non_blank < end_idx and not lines[next_non_blank].strip():
                    next_non_blank += 1
                if next_non_blank < end_idx and (
                    (len(lines[next_non_blank]) - len(lines[next_non_blank].lstrip(" "))) > indent
                    or next_non_blank in fenced_lines
                ):
                    block.append(sub_line)
                    captured.add(m)
                    m += 1
                    continue
                break
            if (len(sub_line) - len(sub_line.lstrip(" "))) > indent:
                block.append(sub_line)
                captured.add(m)
                m += 1
                continue
            break

        preserved.append(block)
        k = m

    return preserved, captured


def _extract_trailing_wrapup_paragraphs(
    lines: list[str],
    start_idx: int,
    end_idx: int,
    captured_indices: set[int],
    fenced_lines: set[int],
) -> list[list[str]]:
    """Preserves conversational closing questions or wrap-up sentences at the bottom of a Verification section."""
    cursor = end_idx - 1
    while cursor > start_idx and not lines[cursor].strip():
        cursor -= 1

    trailing_paras_rev: list[tuple[int, list[str]]] = []
    while cursor > start_idx:
        if cursor in fenced_lines or cursor in captured_indices:
            break
        if not lines[cursor].strip():
            cursor -= 1
            continue
        p_end = cursor
        p_start = cursor
        valid_para = True
        while p_start > start_idx and lines[p_start].strip():
            is_boundary_token = False
            if p_start in fenced_lines or p_start in captured_indices:
                is_boundary_token = True
            else:
                ln = lines[p_start]
                st = ln.strip()
                if re.match(r"^(?:[-*+•]|\d+[.)]|\||>|#{1,6}\s)", st) or re.match(r"^\*\*[^*]+?\*\*\s*:?\s*$", st):
                    is_boundary_token = True
                elif (len(ln) - len(ln.lstrip(" "))) > 0:
                    valid_para = False
                    break
            if is_boundary_token:
                if p_start == p_end:
                    valid_para = False
                break
            p_start -= 1
        if not valid_para:
            break
        para_lines = lines[p_start + 1 : p_end + 1]
        if not para_lines:
            break
        trailing_paras_rev.append((p_start + 1, para_lines))
        cursor = p_start if lines[p_start].strip() else (p_start - 1)

    if not trailing_paras_rev:
        return []

    kept_rev: list[list[str]] = []
    for para_start, para_lines in trailing_paras_rev:
        para_text = " ".join(ln.strip() for ln in para_lines).strip()
        if not para_text:
            continue
        plain_para = re.sub(r"[`*_]+", "", para_text).strip()
        had_structured = any(
            (idx in fenced_lines)
            or bool(re.match(r"^\s*(?:[-*+•]|\d+[.)]|\||>)", lines[idx]))
            for idx in range(start_idx + 1, para_start)
        )
        is_prompt = para_text.rstrip().endswith("?") or bool(_WRAPUP_PROMPT_RE.search(plain_para))
        is_non_verdict_closing = had_structured and not bool(_RAW_VERDICT_RE.match(plain_para))
        if is_prompt or is_non_verdict_closing:
            kept_rev.append(para_lines)
        else:
            break

    return list(reversed(kept_rev))


def filter_verification_report_for_speech(raw_text: str) -> str:
    """
    Removes only Verification Report sections from assistant responses before
    TTS playback while preserving everything else (summary, Close-Out reports,
    and trailing questions or takeaways) verbatim for Locate-in-Chat.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    lines = raw_text.splitlines()
    fenced_lines = _compute_fenced_line_indices(lines)
    out_lines: list[str] = []

    i = 0
    while i < len(lines):
        if i not in fenced_lines:
            hdr = _classify_verification_header(lines[i])
            if hdr is not None:
                kind, level, parent_norm = hdr
                end_idx = _find_verification_section_end(lines, i, kind, level, fenced_lines)
                closeout_blocks, captured = _extract_embedded_closeout_blocks(
                    lines, i, end_idx, kind, level, parent_norm, fenced_lines
                )
                wrapup_paras = _extract_trailing_wrapup_paragraphs(
                    lines, i, end_idx, captured, fenced_lines
                )

                for blk in closeout_blocks:
                    if out_lines and out_lines[-1].strip():
                        out_lines.append("")
                    out_lines.extend(blk)
                for para in wrapup_paras:
                    if out_lines and out_lines[-1].strip():
                        out_lines.append("")
                    out_lines.extend(para)

                i = end_idx
                continue

        out_lines.append(lines[i])
        i += 1

    # Collapse duplicate or orphaned horizontal rule dividers left around removed sections
    hr_re = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
    out_fenced = _compute_fenced_line_indices(out_lines)
    deduped: list[str] = []
    last_nonblank_was_hr = False
    for idx, ln in enumerate(out_lines):
        if idx not in out_fenced and hr_re.match(ln):
            if last_nonblank_was_hr or not any(prev.strip() for prev in deduped):
                continue
            last_nonblank_was_hr = True
            deduped.append(ln)
        else:
            if ln.strip():
                last_nonblank_was_hr = False
            deduped.append(ln)

    while deduped and not deduped[-1].strip():
        deduped.pop()
    if deduped and (len(deduped) - 1) not in _compute_fenced_line_indices(deduped) and hr_re.match(deduped[-1]):
        deduped.pop()
    while deduped and not deduped[0].strip():
        deduped.pop(0)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(deduped)).strip()
    if not cleaned:
        return raw_text
    return cleaned

def capture_highlighted_text(target_hwnd: Optional[int] = None) -> Optional[str]:
    """
    Universally captures highlighted/selected text from any active application on Windows.
    If target_hwnd is provided, restores focus to that window before simulating Ctrl+C.
    Returns cleaned text string or None if no text was selected.
    """
    import ctypes
    try:
        import pyperclip
    except ImportError:
        pyperclip = None

    if sys.platform == "darwin" and pyperclip:
        try:
            import subprocess
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "c" using command down'],
                capture_output=True,
                timeout=2,
            )
            time.sleep(0.15)
            t = pyperclip.paste()
            return t.strip() if t and t.strip() else None
        except Exception:
            pass

    if sys.platform != "win32" or not pyperclip:
        if pyperclip:
            try:
                t = pyperclip.paste()
                return t.strip() if t and t.strip() else None
            except Exception:
                pass
        return None

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # If target window provided and still valid, reliably restore foreground focus
    if target_hwnd:
        try:
            hwnd_val = getattr(target_hwnd, "value", target_hwnd)
            if user32.IsWindow(hwnd_val):
                # Standard Win32 foreground lock bypass:
                # 1. Tap Alt key to unlock Windows foreground lock
                VK_MENU = 0x12
                KEYEVENTF_KEYUP = 0x0002
                user32.keybd_event(VK_MENU, 0, 0, 0)
                user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

                # 2. Attach thread input if different threads
                fore_hwnd = user32.GetForegroundWindow()
                fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
                cur_tid = kernel32.GetCurrentThreadId()
                if fore_tid and fore_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, fore_tid, True)
                    user32.BringWindowToTop(hwnd_val)
                    user32.SetForegroundWindow(hwnd_val)
                    user32.AttachThreadInput(cur_tid, fore_tid, False)
                else:
                    user32.BringWindowToTop(hwnd_val)
                    user32.SetForegroundWindow(hwnd_val)
                time.sleep(0.10)
        except Exception:
            pass

    # Save prior clipboard content to restore later if no new text was copied
    prior_clip = ""
    try:
        prior_clip = pyperclip.paste()
    except Exception:
        pass

    sentinel = f"__ANTI_SENTINEL_{time.time()}__"
    try:
        pyperclip.copy(sentinel)
    except Exception:
        pass

    # Synthesize Ctrl+C
    VK_CONTROL = 0x11
    VK_C = 0x43
    KEYEVENTF_KEYUP = 0x0002

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    new_clip = None
    # Poll briefly for target app to process WM_COPY
    for _ in range(8):
        time.sleep(0.04)
        try:
            curr = pyperclip.paste()
            if curr and curr != sentinel:
                new_clip = curr
                break
        except Exception:
            pass

    if new_clip and new_clip != sentinel and new_clip.strip():
        return new_clip.strip()

    # If no new text was copied (no selection), restore prior clipboard and do NOT read stale data
    if prior_clip and prior_clip != sentinel:
        try:
            pyperclip.copy(prior_clip)
        except Exception:
            pass

    return None

class TranscriptWatcher:
    """
    Watches all active Antigravity session transcripts concurrently.
    Supports multi-project and multi-conversation workspaces without race conditions
    or dropped voice notifications when switching between tabs.
    """

    def __init__(
        self,
        on_new_response: Callable[..., None],
        on_user_input: Optional[Callable[[str, str, int], None]] = None,
        skip_verification_report: bool = True,
    ):
        self.on_new_response = on_new_response
        self.on_user_input = on_user_input
        self.skip_verification_report = skip_verification_report
        self.running = False
        # Map of file_path -> {"last_file_size": int, "last_step_index": int}
        self.tracked_files: dict[str, dict] = {}
        self._thread: Optional[threading.Thread] = None

    def get_candidate_transcripts(self) -> list[str]:
        """Dynamically locates all transcripts updated within the last 24 hours."""
        brain_dir = os.path.expanduser(r"~/.gemini/antigravity/brain")
        candidates = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl"))
        if not candidates:
            return []
        now = time.time()
        # Keep any transcript modified within the last 24 hours, ordered newest first
        recent = [p for p in candidates if (now - os.path.getmtime(p)) < 86400]
        recent.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return recent

    def _sync_file_to_end(self, filepath: str) -> dict:
        """On initial discovery, scan to the end of the transcript to avoid replaying old history."""
        state = {"last_file_size": 0, "last_step_index": 0}
        if not os.path.exists(filepath):
            return state

        state["last_file_size"] = os.path.getsize(filepath)
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        idx = d.get("step_index", 0)
                        if idx > state["last_step_index"]:
                            state["last_step_index"] = idx
                    except Exception:
                        pass
        except Exception:
            pass
        return state

    def start(self):
        for filepath in self.get_candidate_transcripts():
            self.tracked_files[filepath] = self._sync_file_to_end(filepath)
            print(f"[*] Watching transcript: {filepath} (from step {self.tracked_files[filepath]['last_step_index']})")
        self.running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _watch_loop(self):
        while self.running:
            try:
                candidates = self.get_candidate_transcripts()
                for filepath in candidates:
                    if filepath not in self.tracked_files:
                        self.tracked_files[filepath] = self._sync_file_to_end(filepath)
                        print(f"[*] Newly detected transcript: {filepath} (synced to step {self.tracked_files[filepath]['last_step_index']})")
                        continue

                    state = self.tracked_files[filepath]
                    if not os.path.exists(filepath):
                        continue

                    curr_size = os.path.getsize(filepath)
                    if curr_size <= state["last_file_size"]:
                        continue

                    # Read newly appended lines
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(state["last_file_size"])
                        new_lines = f.readlines()
                        state["last_file_size"] = f.tell()

                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            idx = entry.get("step_index", 0)
                            if idx <= state["last_step_index"]:
                                continue
                            state["last_step_index"] = idx

                            # Detect user prompt submission turn
                            is_user = entry.get("source") in ("USER_EXPLICIT", "USER") and entry.get("type") == "USER_INPUT"
                            if is_user:
                                user_text = entry.get("content", "").strip()
                                if user_text and self.on_user_input:
                                    try:
                                        self.on_user_input(user_text, filepath, idx)
                                    except Exception:
                                        pass

                            # Final user-facing assistant response turn:
                            # source == "MODEL", type == "PLANNER_RESPONSE", status == "DONE", tool_calls == []
                            is_model = entry.get("source") == "MODEL"
                            is_planner = entry.get("type") == "PLANNER_RESPONSE"
                            is_done = entry.get("status") == "DONE"
                            no_tools = len(entry.get("tool_calls", [])) == 0
                            content = entry.get("content", "").strip()

                            if is_model and is_planner and is_done and no_tools and content:
                                is_truncated = ("truncated_fields" in entry and "content" in entry.get("truncated_fields", [])) or ("<truncated " in content)
                                if is_truncated:
                                    full_content = get_full_content(filepath, idx)
                                    if full_content:
                                        content = full_content
                                speech_ready = content
                                if self.skip_verification_report:
                                    speech_ready = filter_verification_report_for_speech(speech_ready)
                                words = speech_ready.split()
                                if len(words) > 3500:
                                    speech_ready = truncate_for_audio_summary(speech_ready, max_words=3500)
                                try:
                                    self.on_new_response(speech_ready, filepath, idx)
                                except TypeError:
                                    self.on_new_response(speech_ready)
                        except Exception:
                            pass

            except Exception:
                time.sleep(1.0)

            time.sleep(1.0)
