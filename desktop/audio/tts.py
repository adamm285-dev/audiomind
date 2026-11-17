"""
Anti Voice Output Engine.
Synthesizes speech using ultra-realistic Edge-TTS neural models and renders 
direct 48kHz stereo PCM matching the Arctis Nova Pro Wireless DAC.
Features interactive seekable playback, pause, resume, and 5s/10s rewind.
"""
import os
import re
import asyncio
import time
import threading
import sys
import subprocess
import shutil
from typing import Optional, Callable, Any
import numpy as np
import edge_tts

try:
    from desktop.audio.player import global_player, SpeechPlayer
except ImportError:
    try:
        from audio.player import global_player, SpeechPlayer
    except ImportError:
        global_player = None
        SpeechPlayer = None

# High-fidelity Kokoro & Edge conversational neural voices
KOKORO_VOICES = {
    "heart": "af_heart",        # Warm, natural, expressive female (default)
    "bella": "af_bella",        # Clear, friendly, articulate female
    "nicole": "af_nicole",      # Relaxed, casual female
    "sky": "af_sky",            # Breezy, upbeat female
    "sarah": "af_sarah",        # Crisp, professional female
    "adam": "am_adam",          # Conversational, natural male
    "michael": "am_michael",    # Deep, warm male
    "echo": "am_echo",          # Smooth, mellow male
    "onyx": "am_onyx",          # Resonant, authoritative male
    "emma": "bf_emma",          # Expressive British female
    "isabella": "bf_isabella",  # Eloquent British female
    "george": "bm_george",      # Clear British male
    "fable": "bm_fable",        # Expressive storyteller British male
}

VOICE_PROFILES = {
    **KOKORO_VOICES,
    # Direct IDs
    "af_heart": "af_heart",
    "af_bella": "af_bella",
    "af_nicole": "af_nicole",
    "af_sky": "af_sky",
    "af_sarah": "af_sarah",
    "am_adam": "am_adam",
    "am_michael": "am_michael",
    "am_echo": "am_echo",
    "am_onyx": "am_onyx",
    "bf_emma": "bf_emma",
    "bf_isabella": "bf_isabella",
    "bm_george": "bm_george",
    "bm_fable": "bm_fable",
    # Backward compatible aliases
    "ava": "af_heart",
    "andrew": "am_adam",
    "brian": "bm_george",
}

EDGE_VOICE_MAP = {
    "af_heart": "en-US-AvaNeural",
    "heart": "en-US-AvaNeural",
    "ava": "en-US-AvaNeural",
    "af_bella": "en-US-EmmaNeural",
    "bella": "en-US-EmmaNeural",
    "af_nicole": "en-US-JennyNeural",
    "nicole": "en-US-JennyNeural",
    "af_sky": "en-US-AnaNeural",
    "sky": "en-US-AnaNeural",
    "af_sarah": "en-US-AriaNeural",
    "sarah": "en-US-AriaNeural",
    "emma": "en-GB-SoniaNeural",
    "bf_emma": "en-GB-SoniaNeural",
    "bf_isabella": "en-GB-LibbyNeural",
    "isabella": "en-GB-LibbyNeural",
    "am_adam": "en-US-AndrewNeural",
    "adam": "en-US-AndrewNeural",
    "andrew": "en-US-AndrewNeural",
    "am_michael": "en-US-ChristopherNeural",
    "michael": "en-US-ChristopherNeural",
    "am_echo": "en-US-GuyNeural",
    "echo": "en-US-GuyNeural",
    "am_onyx": "en-US-EricNeural",
    "onyx": "en-US-EricNeural",
    "bm_george": "en-GB-RyanNeural",
    "george": "en-GB-RyanNeural",
    "brian": "en-GB-RyanNeural",
    "bm_fable": "en-GB-ThomasNeural",
    "fable": "en-GB-ThomasNeural",
}

DEFAULT_VOICE = VOICE_PROFILES["heart"]

def set_default_voice(voice: str):
    """Sets global active neural voice profile."""
    global DEFAULT_VOICE
    v_clean = VOICE_PROFILES.get(voice.lower() if isinstance(voice, str) else "", voice)
    DEFAULT_VOICE = v_clean

def get_default_voice() -> str:
    """Returns active neural voice profile key."""
    return DEFAULT_VOICE
FFMPEG_PATH = shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH") or (r"C:\ffmpeg\bin\ffmpeg.exe" if os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe") else "ffmpeg")

def normalize_phonetics(text: str) -> str:
    """Normalize 'Anti' to 'Ante' for Edge-TTS pronunciation as /æn.ti/ ('ant-tea')."""
    return re.sub(r'\bAnti\b', 'Ante', text, flags=re.IGNORECASE)

def decode_mp3_to_pcm(mp3_data: bytes) -> np.ndarray:
    """Converts MP3 byte stream to 48,000 Hz Stereo float32 PCM via ffmpeg."""
    if not mp3_data:
        return np.empty((0, 2), dtype=np.float32)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [FFMPEG_PATH, "-i", "pipe:0", "-f", "f32le", "-ar", "48000", "-ac", "2", "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=creationflags
    )
    raw_pcm, _ = proc.communicate(input=mp3_data)
    if not raw_pcm:
        return np.empty((0, 2), dtype=np.float32)
    return np.frombuffer(raw_pcm, dtype=np.float32).reshape(-1, 2)

def extract_chapters_from_text(raw_text: str) -> list[tuple[str, str]]:
    """
    Extracts structured chapters from an assistant response text or highlighted text.
    Returns list of (title, chapter_text).
    Detects:
      1. Markdown headings (## or ### or ####)
      2. Bold bullet points (* **Topic**: or - **Topic**: or • **Topic**:)
      3. Numbered points (1. ..., 2. ..., Step 1: ..., Item 1: ...)
      4. Horizontal rule section dividers (---)
      5. Distinct paragraph blocks (for multi-paragraph responses)
      6. Sentence-based chunking for long continuous text (> 50 words)
    If text is short or cannot be segmented, returns [("Overview", raw_text)].
    """
    if not raw_text or not raw_text.strip():
        return [("Overview", "")]
    text = raw_text.strip()

    def _clean_title(raw_t: str) -> str:
        t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw_t)
        t = re.sub(r'[*_`#]', '', t)
        t = re.sub(r'^[*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf:]+\s*', '', t)
        t = t.strip().rstrip(':').strip()
        return t[:40].strip()

    # 1. Heading-based splitting (## or ### or ####)
    header_pattern = r'(?:^|\n)(#{1,4}\s+[^\n]+)'
    parts = re.split(header_pattern, text)
    if len(parts) >= 3:
        chapters = []
        intro = parts[0].strip()
        if intro and len(intro.split()) >= 6:
            chapters.append(("Overview", intro))
        for i in range(1, len(parts), 2):
            h_line = parts[i].strip().lstrip('#').strip()
            h_title = _clean_title(h_line)
            body = parts[i+1].strip() if i+1 < len(parts) else ''
            if body:
                chapters.append((h_title or f"Chapter {len(chapters)+1}", body))
        if len(chapters) > 1:
            return chapters

    # 2. Bold / Bullet section splitting (* **Title**: or - **Title**: or • **Title**:)
    bullet_pattern = r'(?:^|\n)(?=\s*[-*•]\s+\*\*[^*]+\*\*[:\s-]*)'
    b_parts = [p.strip() for p in re.split(bullet_pattern, text) if p.strip()]
    if len(b_parts) >= 2:
        chapters = []
        for i, p in enumerate(b_parts):
            m_bold = re.search(r'\*\*([^*]+)\*\*', p)
            raw_title = m_bold.group(1).strip() if m_bold else p.split('\n')[0].strip()
            title = _clean_title(raw_title)
            chapters.append((title or f"Point {i+1}", p))
        if len(chapters) > 1:
            return chapters

    # 3. Numbered item splitting (1. ... 2. ... or Item 1: ... Step 1: ...)
    numbered_pattern = r'(?:^|\n)(?=(?:\d+[\.)]|\b(?:Item|Step|Section|Part|Phase)\s+\d+[:\.]?)\s+)'
    num_parts = [p.strip() for p in re.split(numbered_pattern, text) if p.strip()]
    if len(num_parts) >= 2:
        chapters = []
        for i, p in enumerate(num_parts):
            first_line = p.split('\n')[0].strip()
            m_bold = re.search(r'\*\*([^*]+)\*\*', first_line)
            raw_title = m_bold.group(1).strip() if m_bold else first_line
            title = _clean_title(raw_title)
            chapters.append((title or f"Point {i+1}", p))
        if len(chapters) > 1:
            return chapters

    # 4. Horizontal rule section splitting (--- or ***)
    hr_pattern = r'(?:^|\n)\s*[-*_]{3,}\s*(?:\n|$)'
    hr_parts = [p.strip() for p in re.split(hr_pattern, text) if p.strip()]
    if len(hr_parts) >= 2:
        chapters = []
        for i, p in enumerate(hr_parts):
            first_line = p.split('\n')[0].strip()
            title = _clean_title(first_line)
            chapters.append((title or f"Section {i+1}", p))
        if len(chapters) > 1:
            return chapters

    # 5. Paragraph-based splitting (\n\n+)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    words = text.split()
    if len(paragraphs) >= 2 and len(words) >= 25:
        chapters = []
        buf = []
        buf_words = 0
        for p in paragraphs:
            p_words = len(p.split())
            if buf_words > 0 and (buf_words + p_words) > 25:
                c_text = '\n\n'.join(buf)
                first_line = buf[0].split('\n')[0].strip()
                title = _clean_title(first_line)
                chapters.append((title or f"Section {len(chapters)+1}", c_text))
                buf = [p]
                buf_words = p_words
            else:
                buf.append(p)
                buf_words += p_words
        if buf:
            c_text = '\n\n'.join(buf)
            first_line = buf[0].split('\n')[0].strip()
            title = _clean_title(first_line)
            chapters.append((title or f"Section {len(chapters)+1}", c_text))
        if len(chapters) > 1:
            return chapters

    # 6. Long continuous text fallback: chunk by sentences (~45-75 words each)
    if len(words) > 50:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) >= 2:
            chapters = []
            buf = []
            buf_w = 0
            for s in sentences:
                s_w = len(s.split())
                if buf_w > 0 and (buf_w + s_w) >= 45:
                    c_text = ' '.join(buf)
                    first_words = ' '.join(buf[0].split()[:6])
                    title = _clean_title(first_words)
                    chapters.append((title or f"Part {len(chapters)+1}", c_text))
                    buf = [s]
                    buf_w = s_w
                else:
                    buf.append(s)
                    buf_w += s_w
            if buf:
                c_text = ' '.join(buf)
                first_words = ' '.join(buf[0].split()[:6])
                title = _clean_title(first_words)
                chapters.append((title or f"Part {len(chapters)+1}", c_text))
            if len(chapters) > 1:
                return chapters

    return [("Overview", text)]

_EDGE_TTS_HEALTHY = True
_EDGE_TTS_LAST_FAILURE = 0.0

_kokoro_instance = None
_kokoro_lock = threading.Lock()

def _resolve_kokoro_model_paths() -> tuple[Optional[str], Optional[str]]:
    """Locate Kokoro ONNX model and voice embeddings file across known directories."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "resources", "models"),
        os.path.join(os.path.expanduser("~"), ".cache", "audiomind", "models"),
        r"H:\Downloads\anti-voice-assistant\desktop\resources\models",
        r"H:\Downloads\audiomind\desktop\resources\models",
    ]
    for d in candidates:
        if not d or not os.path.isdir(d):
            continue
        m = os.path.join(d, "kokoro-v1.0.onnx")
        v = os.path.join(d, "voices-v1.0.bin")
        if os.path.exists(m) and os.path.exists(v):
            return m, v
    return None, None

def get_kokoro() -> Optional[Any]:
    """Returns the singleton Kokoro neural TTS instance, or None if unavailable."""
    global _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is not None:
            return _kokoro_instance
        try:
            from kokoro_onnx import Kokoro
            m_path, v_path = _resolve_kokoro_model_paths()
            if m_path and v_path:
                _kokoro_instance = Kokoro(m_path, v_path)
                return _kokoro_instance
        except Exception as e:
            print(f"[!] Kokoro initialization failed: {e}")
    return None

def is_kokoro_available() -> bool:
    """Returns True if Kokoro-ONNX and its model weights are available."""
    m_path, v_path = _resolve_kokoro_model_paths()
DEFAULT_SPEED = 1.0

def set_speech_speed(speed: float):
    """Sets global speech playback speed multiplier (0.5 to 2.5)."""
    global DEFAULT_SPEED
    DEFAULT_SPEED = max(0.5, min(2.5, float(speed)))

def get_speech_speed() -> float:
    """Returns global speech playback speed multiplier."""
    return DEFAULT_SPEED

def split_text_for_streaming(text: str, max_words_per_chunk: int = 45) -> list[str]:
    """
    Splits a chapter body into sentence-aligned sub-chunks of ~max_words_per_chunk words
    so that Kokoro neural synthesis streams smoothly in ~3-5s increments without ever
    blocking or starving audio playback on long chapters.
    """
    if not text or not text.strip():
        return []
    words = text.split()
    if len(words) <= max_words_per_chunk + 15:
        return [text.strip()]

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    if len(sentences) <= 1:
        return [text.strip()]

    chunks = []
    cur_buf = []
    cur_words = 0
    for s in sentences:
        s_words = len(s.split())
        if cur_words > 0 and (cur_words + s_words) > max_words_per_chunk:
            chunks.append(" ".join(cur_buf))
            cur_buf = [s]
            cur_words = s_words
        else:
            cur_buf.append(s)
            cur_words += s_words
    if cur_buf:
        chunks.append(" ".join(cur_buf))
    return chunks

def synth_kokoro_pcm(text: str, voice: str = DEFAULT_VOICE, speed: float = None) -> np.ndarray:
    """
    Synthesizes speech using Kokoro-ONNX local neural model.
    Outputs 48,000 Hz Stereo float32 PCM matching Arctis Nova Pro / soundcard DAC.
    """
    if not text or not text.strip():
        return np.empty((0, 2), dtype=np.float32)
    if speed is None:
        speed = DEFAULT_SPEED
    kokoro = get_kokoro()
    if kokoro is None:
        return np.empty((0, 2), dtype=np.float32)
    try:
        import scipy.signal
        v_key = VOICE_PROFILES.get(voice.lower(), voice)
        try:
            available = kokoro.get_voices()
            if v_key not in available:
                v_key = "af_heart"
        except Exception:
            v_key = "af_heart"

        samples, sr = kokoro.create(text, voice=v_key, speed=speed)
        if samples is None or len(samples) == 0:
            return np.empty((0, 2), dtype=np.float32)

        # Resample to 48kHz stereo float32
        if sr == 24000:
            samples_48k = scipy.signal.resample_poly(samples, 2, 1)
        elif sr != 48000:
            samples_48k = scipy.signal.resample(samples, int(len(samples) * 48000 / sr))
        else:
            samples_48k = samples

        stereo = np.column_stack((samples_48k, samples_48k)).astype(np.float32)
        return stereo
    except Exception as e:
        print(f"[!] Kokoro synthesis error: {e}")
        return np.empty((0, 2), dtype=np.float32)

def synth_sapi_pcm(text: str, samplerate: int = 48000) -> np.ndarray:
    """
    Offline local Windows TTS fallback via SAPI.SpVoice and SpMemoryStream.
    Produces 48kHz stereo float32 PCM without network dependencies or 403 errors.
    """
    if sys.platform != "win32" or not text or not text.strip():
        return np.empty((0, 2), dtype=np.float32)
    try:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        voice = comtypes.client.CreateObject('SAPI.SpVoice')
        try:
            for token in voice.GetVoices():
                if "zira" in token.GetDescription().lower():
                    voice.Voice = token
                    break
        except Exception:
            pass
        stream = comtypes.client.CreateObject('SAPI.SpMemoryStream')
        fmt = comtypes.client.CreateObject('SAPI.SpAudioFormat')
        fmt.Type = 39  # SAFT48kHz16BitStereo
        stream.Format = fmt
        voice.AudioOutputStream = stream
        voice.Speak(text)
        raw_bytes = bytes(stream.GetData())
        if not raw_bytes:
            return np.empty((0, 2), dtype=np.float32)
        pcm = (np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0).reshape(-1, 2)
        return pcm
    except Exception as e:
        print(f"[!] SAPI fallback error: {e}")
        return np.empty((0, 2), dtype=np.float32)

async def _synth_one(c_text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz", timeout: float = 6.0) -> bytes:
    """Synthesizes a single chunk of text into MP3 bytes via Edge-TTS with timeout, circuit breaker and 1 retry."""
    global _EDGE_TTS_HEALTHY, _EDGE_TTS_LAST_FAILURE
    if not _EDGE_TTS_HEALTHY and (time.time() - _EDGE_TTS_LAST_FAILURE < 300):
        return b""

    clean_c = normalize_phonetics(c_text)
    if not clean_c or not clean_c.strip():
        return b""
    for attempt in range(2):
        try:
            async def _stream_one():
                communicate = edge_tts.Communicate(clean_c, voice, rate=rate, pitch=pitch)
                data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        data += chunk["data"]
                return data

            data = await asyncio.wait_for(_stream_one(), timeout=timeout)
            if data:
                _EDGE_TTS_HEALTHY = True
                return data
        except Exception as e:
            err_str = str(e)
            if "403" in err_str or "Invalid response status" in err_str:
                _EDGE_TTS_HEALTHY = False
                _EDGE_TTS_LAST_FAILURE = time.time()
                print(f"[!] Edge-TTS service returned 403 Forbidden. Tripping circuit breaker.")
                return b""
            if attempt == 0:
                await asyncio.sleep(0.3)
            else:
                return b""
    return b""

async def speak_async(
    text: str, 
    voice: str = DEFAULT_VOICE, 
    rate: str = "+0%", 
    pitch: str = "+0Hz",
    speed: Optional[float] = None,
    on_start: Optional[Callable] = None,
    on_level: Optional[Callable[[float], None]] = None,
    on_finish: Optional[Callable] = None
):
    """
    Synthesize text and stream directly to 48kHz stereo audio device with seek, pause, and chapter support.
    Tiered Synthesis Architecture:
      Tier 1: Kokoro-ONNX Local Neural Engine (100% offline, 48kHz stereo, warm human-grade voice)
      Tier 2: Edge-TTS Cloud Neural Engine (Ava/Emma, if network unblocked)
      Tier 3: Windows SAPI Offline Engine (Emergency failsafe)
    """
    if not text or not text.strip():
        return

    effective_speed = speed if speed is not None else DEFAULT_SPEED

    chapters = extract_chapters_from_text(text)
    try:
        from desktop.audio.read_aloud import (
            clean_markdown_for_speech,
            extract_visible_blocks_from_markdown,
            align_subchunks_to_visible_blocks,
        )
    except ImportError:
        try:
            from audio.read_aloud import (
                clean_markdown_for_speech,
                extract_visible_blocks_from_markdown,
                align_subchunks_to_visible_blocks,
            )
        except ImportError:
            clean_markdown_for_speech = lambda t: t
            extract_visible_blocks_from_markdown = lambda t: [t.strip()] if t and t.strip() else []
            align_subchunks_to_visible_blocks = lambda scs, vbs: [
                [(i, w) for w in sc.split() if w.strip()] for i, sc in enumerate(scs)
            ]

    def _register_player_segment(tokens, start_sample=None, end_sample=None, chapter_title=""):
        if global_player is not None and hasattr(global_player, "register_segment_tokens") and tokens:
            try:
                global_player.register_segment_tokens(
                    tokens,
                    start_sample=start_sample,
                    end_sample=end_sample,
                    chapter_title=chapter_title,
                )
            except Exception:
                pass

    cleaned_chapters = []
    chapter_vis_blocks = []
    for title, body in chapters:
        c_body = clean_markdown_for_speech(body)
        if c_body and c_body.strip():
            cleaned_chapters.append((title, c_body))
            chapter_vis_blocks.append(extract_visible_blocks_from_markdown(body))
    if cleaned_chapters:
        chapters = cleaned_chapters
    else:
        chapter_vis_blocks = [extract_visible_blocks_from_markdown(body) for _, body in chapters]

    full_vis_blocks = extract_visible_blocks_from_markdown(text)
    clean_text = clean_markdown_for_speech(text)
    clean_text = normalize_phonetics(clean_text)

    # 1. Tier 1: Kokoro Local Neural TTS (Primary: pristine human voice, offline, 403-immune)
    kokoro = get_kokoro()
    if kokoro is not None:
        try:
            if len(chapters) > 1 and hasattr(global_player, "append_pcm"):
                # Sentence-chunked streaming chapter synthesis:
                # Synthesize first sub-chunk of Chapter 1 for sub-2s Time-To-First-Audio (TTFA),
                # and stream all remaining sub-chunks and chapters seamlessly without buffer underruns.
                planned_titles = [c[0] for c in chapters]
                started_playback = False

                for ch_idx, (ch_title, ch_body) in enumerate(chapters):
                    if started_playback and hasattr(global_player, "is_active") and not global_player.is_active:
                        break
                    sub_chunks = split_text_for_streaming(normalize_phonetics(ch_body), max_words_per_chunk=45)
                    if not sub_chunks:
                        continue

                    vis_blocks = chapter_vis_blocks[ch_idx] if ch_idx < len(chapter_vis_blocks) else []
                    aligned_subs = align_subchunks_to_visible_blocks(sub_chunks, vis_blocks)

                    is_first_sub_of_chapter = True
                    for sub_i, sub_text in enumerate(sub_chunks):
                        if started_playback and hasattr(global_player, "is_active") and not global_player.is_active:
                            break
                        sub_pcm = synth_kokoro_pcm(sub_text, voice=voice, speed=effective_speed)
                        if len(sub_pcm) == 0:
                            continue

                        seg_tokens = aligned_subs[sub_i] if sub_i < len(aligned_subs) else []
                        if not started_playback:
                            global_player.play_pcm(
                                sub_pcm,
                                chapter_markers=[0],
                                chapter_titles=planned_titles,
                                total_planned_chapters=len(chapters),
                                stream_complete=False,
                                on_start=on_start,
                                on_level=on_level,
                                on_finish=on_finish
                            )
                            _register_player_segment(seg_tokens, start_sample=0, end_sample=len(sub_pcm), chapter_title=ch_title)
                            started_playback = True
                            is_first_sub_of_chapter = False
                        else:
                            if is_first_sub_of_chapter:
                                global_player.append_pcm(
                                    sub_pcm,
                                    chapter_title=ch_title,
                                    pause_sec=0.25,
                                    new_chapter=True
                                )
                                _register_player_segment(seg_tokens, chapter_title=ch_title)
                                is_first_sub_of_chapter = False
                            else:
                                try:
                                    global_player.append_pcm(
                                        sub_pcm,
                                        chapter_title=ch_title,
                                        pause_sec=0.08,
                                        new_chapter=False
                                    )
                                except TypeError:
                                    global_player.append_pcm(sub_pcm, chapter_title=ch_title, pause_sec=0.08)
                                _register_player_segment(seg_tokens, chapter_title=ch_title)

                if started_playback:
                    global_player.set_stream_complete(True)
                    global_player.wait()
                    return
            elif len(chapters) > 1:
                # Non-streaming batch fallback (for players without dynamic append support)
                pcm_chunks = []
                titles = []
                batch_vis = []
                for ch_idx, (title, body) in enumerate(chapters):
                    norm_body = normalize_phonetics(body)
                    c_pcm = synth_kokoro_pcm(norm_body, voice=voice, speed=effective_speed)
                    if len(c_pcm) > 0:
                        pcm_chunks.append(c_pcm)
                        titles.append(title)
                        vis_blocks = chapter_vis_blocks[ch_idx] if ch_idx < len(chapter_vis_blocks) else []
                        aligned = align_subchunks_to_visible_blocks([norm_body], vis_blocks)
                        batch_vis.append(aligned[0] if aligned else [])
                if pcm_chunks:
                    silence = np.zeros((int(0.25 * 48000), 2), dtype=np.float32)
                    combined = []
                    markers = []
                    seg_ranges = []
                    curr_s = 0
                    for i, pcm in enumerate(pcm_chunks):
                        markers.append(curr_s)
                        combined.append(pcm)
                        seg_start = curr_s
                        curr_s += len(pcm)
                        seg_ranges.append((seg_start, curr_s, batch_vis[i], titles[i]))
                        if i < len(pcm_chunks) - 1:
                            combined.append(silence)
                            curr_s += len(silence)
                    if combined:
                        audio_f32 = np.concatenate(combined)
                        global_player.play_pcm(
                            audio_f32,
                            chapter_markers=markers,
                            chapter_titles=titles,
                            on_start=on_start,
                            on_level=on_level,
                            on_finish=on_finish
                        )
                        for s_start, s_end, s_toks, s_title in seg_ranges:
                            _register_player_segment(s_toks, start_sample=s_start, end_sample=s_end, chapter_title=s_title)
                        global_player.wait()
                        return
            else:
                sub_chunks = split_text_for_streaming(clean_text, max_words_per_chunk=45)
                aligned_subs = align_subchunks_to_visible_blocks(sub_chunks, full_vis_blocks)
                if len(sub_chunks) > 1 and hasattr(global_player, "append_pcm"):
                    c1_pcm = synth_kokoro_pcm(sub_chunks[0], voice=voice, speed=effective_speed)
                    if len(c1_pcm) > 0:
                        ch_title = chapters[0][0] if chapters else "Overview"
                        global_player.play_pcm(
                            c1_pcm,
                            chapter_markers=[0],
                            chapter_titles=[ch_title],
                            total_planned_chapters=1,
                            stream_complete=False,
                            on_start=on_start,
                            on_level=on_level,
                            on_finish=on_finish
                        )
                        _register_player_segment(aligned_subs[0] if aligned_subs else [], start_sample=0, end_sample=len(c1_pcm), chapter_title=ch_title)
                        for sub_idx, s_chunk in enumerate(sub_chunks[1:], start=1):
                            if hasattr(global_player, "is_active") and not global_player.is_active:
                                break
                            s_pcm = synth_kokoro_pcm(s_chunk, voice=voice, speed=effective_speed)
                            if len(s_pcm) > 0:
                                try:
                                    global_player.append_pcm(s_pcm, chapter_title=ch_title, pause_sec=0.08, new_chapter=False)
                                except TypeError:
                                    global_player.append_pcm(s_pcm, chapter_title=ch_title, pause_sec=0.08)
                                _register_player_segment(aligned_subs[sub_idx] if sub_idx < len(aligned_subs) else [], chapter_title=ch_title)
                        global_player.set_stream_complete(True)
                        global_player.wait()
                        return
                else:
                    c_pcm = synth_kokoro_pcm(clean_text, voice=voice, speed=effective_speed)
                    if len(c_pcm) > 0:
                        ch_title = chapters[0][0] if chapters else "Overview"
                        global_player.play_pcm(
                            c_pcm,
                            chapter_markers=[0],
                            chapter_titles=[ch_title],
                            stream_complete=True,
                            on_start=on_start,
                            on_level=on_level,
                            on_finish=on_finish
                        )
                        _register_player_segment(aligned_subs[0] if aligned_subs else [], start_sample=0, end_sample=len(c_pcm), chapter_title=ch_title)
                        global_player.wait()
                        return
        except Exception as e:
            print(f"[!] Kokoro speech synthesis failed, falling back to secondary tier: {e}")

    # 2. Tier 2: Edge-TTS Cloud Neural Synthesis (if healthy)
    global _EDGE_TTS_HEALTHY, _EDGE_TTS_LAST_FAILURE
    use_edge = _EDGE_TTS_HEALTHY or (time.time() - _EDGE_TTS_LAST_FAILURE >= 300)
    edge_voice = EDGE_VOICE_MAP.get(voice, EDGE_VOICE_MAP.get(DEFAULT_VOICE, "en-US-AvaNeural"))

    if use_edge and len(chapters) > 1:
        try:
            sem = asyncio.Semaphore(3)
            async def _synth_with_sem(c_text: str) -> bytes:
                async with sem:
                    return await _synth_one(c_text, voice=edge_voice, rate=rate, pitch=pitch)

            tasks = [_synth_with_sem(c[1]) for c in chapters]
            mp3_list = await asyncio.gather(*tasks)

            pcm_chunks = []
            titles = []
            edge_vis = []
            for i, (title, body) in enumerate(chapters):
                mp3_data = mp3_list[i] if i < len(mp3_list) else b""
                if not mp3_data and _EDGE_TTS_HEALTHY:
                    notice_text = f"Part {i + 1} could not be read."
                    print(f"[!] Chapter {i + 1} ('{title}') synthesis failed. Synthesizing spoken notice.")
                    notice_mp3 = await _synth_with_sem(notice_text)
                    if notice_mp3:
                        mp3_data = notice_mp3

                if mp3_data:
                    pcm = decode_mp3_to_pcm(mp3_data)
                    pcm_chunks.append(pcm)
                    titles.append(title)
                    vis_blocks = chapter_vis_blocks[i] if i < len(chapter_vis_blocks) else []
                    aligned = align_subchunks_to_visible_blocks([body], vis_blocks)
                    edge_vis.append(aligned[0] if aligned else [])
                else:
                    raise RuntimeError(f"Failed to synthesize chapter {i + 1} or its spoken notice.")

            if pcm_chunks and len(pcm_chunks) == len(chapters):
                silence = np.zeros((int(0.30 * 48000), 2), dtype=np.float32)
                combined = []
                markers = []
                seg_ranges = []
                curr_s = 0
                for i, pcm in enumerate(pcm_chunks):
                    markers.append(curr_s)
                    combined.append(pcm)
                    seg_start = curr_s
                    curr_s += len(pcm)
                    seg_ranges.append((seg_start, curr_s, edge_vis[i], titles[i]))
                    if i < len(pcm_chunks) - 1:
                        combined.append(silence)
                        curr_s += len(silence)

                if combined:
                    audio_f32 = np.concatenate(combined)
                    global_player.play_pcm(
                        audio_f32,
                        chapter_markers=markers,
                        chapter_titles=titles,
                        on_start=on_start,
                        on_level=on_level,
                        on_finish=on_finish
                    )
                    for s_start, s_end, s_toks, s_title in seg_ranges:
                        _register_player_segment(s_toks, start_sample=s_start, end_sample=s_end, chapter_title=s_title)
                    global_player.wait()
                    return
        except Exception as e:
            print(f"[!] Parallel Edge-TTS chapter synthesis skipped/failed: {e}")

    # Single-chapter Edge-TTS synthesis (if healthy)
    if use_edge and _EDGE_TTS_HEALTHY:
        try:
            mp3_data = await _synth_one(clean_text, voice=edge_voice, rate=rate, pitch=pitch)
            if mp3_data:
                audio_f32 = decode_mp3_to_pcm(mp3_data)
                ch_title = chapters[0][0] if chapters else "Overview"
                global_player.play_pcm(
                    audio_f32,
                    chapter_markers=[0],
                    chapter_titles=[ch_title],
                    on_start=on_start,
                    on_level=on_level,
                    on_finish=on_finish
                )
                aligned = align_subchunks_to_visible_blocks([clean_text], full_vis_blocks)
                _register_player_segment(aligned[0] if aligned else [], start_sample=0, end_sample=len(audio_f32), chapter_title=ch_title)
                global_player.wait()
                return
        except Exception as e:
            print(f"[!] Edge-TTS single pass synthesis failed: {e}")

    # 3. Tier 3: Local Windows SAPI Offline Fallback (Immediate, Fail-Safe, 403-Immune)
    print("[!] Seamlessly using local Windows SAPI speech engine (offline fail-safe).")
    if len(chapters) > 1:
        c1_pcm = synth_sapi_pcm(chapters[0][1])
        if len(c1_pcm) > 0:
            planned_titles = [c[0] for c in chapters]
            global_player.play_pcm(
                c1_pcm,
                chapter_markers=[0],
                chapter_titles=planned_titles,
                total_planned_chapters=len(chapters),
                stream_complete=False,
                on_start=on_start,
                on_level=on_level,
                on_finish=on_finish
            )
            vis0 = chapter_vis_blocks[0] if chapter_vis_blocks else []
            aligned0 = align_subchunks_to_visible_blocks([chapters[0][1]], vis0)
            _register_player_segment(aligned0[0] if aligned0 else [], start_sample=0, end_sample=len(c1_pcm), chapter_title=chapters[0][0])
            for i in range(1, len(chapters)):
                if not is_speech_active():
                    break
                ci_pcm = synth_sapi_pcm(chapters[i][1])
                if len(ci_pcm) > 0:
                    global_player.append_pcm(ci_pcm, chapter_title=chapters[i][0], pause_sec=0.25)
                    vis_i = chapter_vis_blocks[i] if i < len(chapter_vis_blocks) else []
                    aligned_i = align_subchunks_to_visible_blocks([chapters[i][1]], vis_i)
                    _register_player_segment(aligned_i[0] if aligned_i else [], chapter_title=chapters[i][0])
            global_player.set_stream_complete(True)
            global_player.wait()
            return

    sapi_pcm = synth_sapi_pcm(clean_text)
    if len(sapi_pcm) > 0:
        ch_title = chapters[0][0] if chapters else "Overview"
        global_player.play_pcm(
            sapi_pcm,
            chapter_markers=[0],
            chapter_titles=[ch_title],
            stream_complete=True,
            on_start=on_start,
            on_level=on_level,
            on_finish=on_finish
        )
        aligned = align_subchunks_to_visible_blocks([clean_text], full_vis_blocks)
        _register_player_segment(aligned[0] if aligned else [], start_sample=0, end_sample=len(sapi_pcm), chapter_title=ch_title)
        global_player.wait()

def stop_speech():
    """Immediately halt any active audio playback."""
    try:
        global_player.stop()
    except Exception:
        pass

def pause_speech() -> bool:
    """Pause speech playback and hold current position."""
    try:
        return global_player.pause()
    except Exception:
        return False

def resume_speech() -> bool:
    """Resume speech playback from paused position."""
    try:
        return global_player.resume()
    except Exception:
        return False

def toggle_pause() -> bool:
    """Toggle between paused and playing states."""
    try:
        return global_player.toggle_pause()
    except Exception:
        return False

def rewind_speech(seconds: float = 5.0) -> float:
    """Rewind active speech by seconds (default 5s). Returns new position in seconds."""
    try:
        return global_player.rewind(seconds)
    except Exception:
        return 0.0

def fast_forward_speech(seconds: float = 5.0) -> float:
    """Fast-forward active speech by seconds (default 5s). Returns new position in seconds."""
    try:
        return global_player.fast_forward(seconds)
    except Exception:
        return 0.0

def skip_to_next_chapter() -> Optional[int]:
    """Jumps playback to the next chapter. Returns new 0-based chapter index or None."""
    try:
        return global_player.skip_to_next_chapter()
    except Exception:
        return None

def repeat_current_chapter() -> Optional[int]:
    """Restarts the current chapter from its beginning. Returns target chapter index."""
    try:
        return global_player.repeat_current_chapter()
    except Exception:
        return None

def repeat_last_chapter() -> Optional[int]:
    """Repeats the current chapter or jumps to the previous chapter. Returns target chapter index."""
    try:
        return global_player.repeat_last_chapter()
    except Exception:
        return None

def get_chapter_info() -> tuple[int, int, str]:
    """Returns (current_chapter_1_based, total_chapters, current_chapter_title)."""
    try:
        return (
            global_player.current_chapter_index + 1,
            global_player.total_chapters,
            global_player.current_chapter_title
        )
    except Exception:
        return (1, 1, "Overview")

def is_speaking() -> bool:
    """Returns True if speech is actively audible."""
    try:
        return bool(getattr(global_player, "is_playing", False))
    except Exception:
        return False

def is_paused() -> bool:
    """Returns True if speech is currently paused."""
    try:
        return bool(getattr(global_player, "is_paused", False))
    except Exception:
        return False

def is_speech_active() -> bool:
    """Returns True if speech is either playing or paused."""
    try:
        return bool(getattr(global_player, "is_active", False))
    except Exception:
        return False

def get_speech_player() -> SpeechPlayer:
    """Returns the underlying SpeechPlayer instance."""
    return global_player

def get_current_locator_info(target_words: int = 6) -> Optional[dict]:
    """Returns sample-accurate Ctrl+F phrase and section info for active playback, or None."""
    try:
        if global_player is not None and getattr(global_player, "is_active", False) and hasattr(global_player, "get_locator_at_sample"):
            return global_player.get_locator_at_sample(target_words=target_words)
    except Exception:
        pass
    return None

def extract_fallback_locator_phrase(raw_text: str, target_words: int = 6) -> str:
    """Extracts a clean verbatim Ctrl+F phrase from raw Markdown when active playback just ended."""
    if not raw_text or not raw_text.strip():
        return ""
    try:
        from desktop.audio.read_aloud import extract_visible_blocks_from_markdown
    except ImportError:
        try:
            from audio.read_aloud import extract_visible_blocks_from_markdown
        except ImportError:
            extract_visible_blocks_from_markdown = lambda t: [t.strip()] if t and t.strip() else []

    blocks = extract_visible_blocks_from_markdown(raw_text)
    if not blocks:
        return ""
    chosen = blocks[-1]
    for blk in reversed(blocks):
        if len(blk.split()) >= 3:
            chosen = blk
            break
    words = chosen.split()[:target_words]
    if SpeechPlayer is not None and hasattr(SpeechPlayer, "_clean_search_phrase"):
        return SpeechPlayer._clean_search_phrase(words)
    return " ".join(words).strip()

def speak(
    text: str, 
    voice: str = DEFAULT_VOICE, 
    rate: str = "+0%", 
    pitch: str = "+0Hz",
    speed: Optional[float] = None,
    on_start: Optional[Callable] = None,
    on_level: Optional[Callable[[float], None]] = None,
    on_finish: Optional[Callable] = None
):
    """Synchronous helper for speak_async."""
    try:
        asyncio.run(speak_async(
            text, 
            voice=voice, 
            rate=rate, 
            pitch=pitch, 
            speed=speed,
            on_start=on_start,
            on_level=on_level,
            on_finish=on_finish
        ))
    except Exception as e:
        print(f"[!] TTS Error: {e}")

if __name__ == "__main__":
    print("[*] Testing Anti TTS Engine with Ava & seekable player...")
    speak("Hey! Anti here. All systems are operational, and the security firewall is active.")
    print("[+] Done!")
