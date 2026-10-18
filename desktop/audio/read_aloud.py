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

def truncate_for_audio_summary(cleaned_text: str, max_words: int = 1200) -> str:
    """
    Ensures spoken assistant responses are coherent, comprehensive, and non-repetitive.
    If the response is within max_words (default 1200), speaks the full cleaned text.
    If the response exceeds max_words, extracts a structured summary covering all
    distinct sections/items followed by the concluding action items, avoiding any overlapping duplicate clauses.
    """
    words = cleaned_text.split()
    if len(words) <= max_words:
        return cleaned_text

    # Response is longer than max_words (e.g. multi-page technical report)
    # Check if text has structured numbered points or sections (e.g. 1. ... 2. ... or Item 1 ...)
    sections = re.split(r'(?:^|\n+)(?=[A-Z0-9][\w\s]*[:\-]|(?:\d+\.|\bItem\s+\d+\b))', cleaned_text)

    if len(sections) >= 3:
        summary_parts = []
        # Take introductory clause / first section
        intro = sections[0].strip()
        if intro:
            intro_sentences = re.split(r'(?<=[.!?])\s+', intro)
            summary_parts.append(' '.join(intro_sentences[:2]).strip())

        # Check if last section is a conclusion/action plan
        last_sec = sections[-1].strip()
        has_plan = bool(re.search(r'\b(plan|action|recommendation|next steps?|decision|proceed)\b', last_sec, re.IGNORECASE))

        body_sections = sections[1:-1] if has_plan else sections[1:]
        per_item_budget = max(1, (max_words - 200) // max(1, len(body_sections)))

        for s in body_sections:
            s = s.strip()
            if not s:
                continue
            s_sentences = re.split(r'(?<=[.!?])\s+', s)
            # Grab the key takeaway sentences of this item
            item_takeaway = ' '.join(s_sentences[:2]).strip()
            item_words = item_takeaway.split()
            if len(item_words) > per_item_budget:
                item_takeaway = ' '.join(item_words[:per_item_budget])
                last_p = max(item_takeaway.rfind('.'), item_takeaway.rfind('!'), item_takeaway.rfind('?'))
                if last_p > 20:
                    item_takeaway = item_takeaway[:last_p + 1]
            summary_parts.append(item_takeaway)

        if has_plan and last_sec:
            plan_sentences = re.split(r'(?<=[.!?])\s+', last_sec)
            summary_parts.append(' '.join(plan_sentences[:4]).strip())

        candidate = '\n\n'.join(summary_parts).strip()
        if len(candidate.split()) <= max_words + 200:
            return candidate

    # Standard clean fallback: take opening overview up to budget
    opening_words = words[:max_words]
    opening_text = ' '.join(opening_words)
    last_p = max(opening_text.rfind('.'), opening_text.rfind('!'), opening_text.rfind('?'))
    if last_p > 100:
        opening_text = opening_text[:last_p + 1]
    return opening_text

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
        on_user_input: Optional[Callable[[str, str, int], None]] = None
    ):
        self.on_new_response = on_new_response
        self.on_user_input = on_user_input
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
                                words = content.split()
                                if len(words) > 1400:
                                    cleaned = clean_markdown_for_speech(content)
                                    speech_ready = truncate_for_audio_summary(cleaned, max_words=1200)
                                else:
                                    speech_ready = content
                                try:
                                    self.on_new_response(speech_ready, filepath, idx)
                                except TypeError:
                                    self.on_new_response(speech_ready)
                        except Exception:
                            pass

            except Exception:
                time.sleep(1.0)

            time.sleep(1.0)
