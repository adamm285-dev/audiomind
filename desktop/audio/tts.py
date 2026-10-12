"""
Anti Voice Output Engine.
Synthesizes speech using ultra-realistic Edge-TTS neural models and renders 
direct 48kHz stereo PCM matching the Arctis Nova Pro Wireless DAC.
Features interactive seekable playback, pause, resume, and 5s/10s rewind.
"""
import os
import re
import asyncio
import sys
import subprocess
from typing import Optional, Callable
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

# Ultra-realistic, expressive conversational neural voices
import shutil

VOICE_PROFILES = {
    "ava": "en-US-AvaNeural",                  # Modern, expressive, warm & natural (pure English, zero language-flipping)
    "emma": "en-US-EmmaNeural",                # Friendly, clear, articulate
    "andrew": "en-US-AndrewNeural",            # Conversational, natural male tone
    "brian": "en-US-BrianNeural",              # Crisp, balanced tone
}

DEFAULT_VOICE = VOICE_PROFILES["ava"]
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
    Extracts structured chapters from an assistant response text.
    Returns list of (title, chapter_text).
    Detects markdown headings (## or ###), numbered points (1. ..., 2. ...),
    or paragraph boundaries for long texts.
    If text is short or cannot be segmented, returns [("Overview", raw_text)].
    """
    if not raw_text or not raw_text.strip():
        return [("Overview", "")]
    text = raw_text.strip()

    # 1. Heading-based splitting (## or ###)
    header_pattern = r'(?:^|\n)(#{1,4}\s+[^\n]+)'
    parts = re.split(header_pattern, text)
    if len(parts) >= 3:
        chapters = []
        intro = parts[0].strip()
        if intro and len(intro.split()) >= 6:
            chapters.append(("Overview", intro))
        for i in range(1, len(parts), 2):
            h_line = parts[i].strip().lstrip('#').strip()
            h_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', h_line)
            h_clean = re.sub(r'[*_`]', '', h_clean)
            h_title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', h_clean)[:45].strip()
            body = parts[i+1].strip() if i+1 < len(parts) else ''
            if body:
                chapters.append((h_title or f"Chapter {len(chapters)+1}", body))
        if len(chapters) > 1:
            return chapters[:6]

    # 2. Numbered item splitting (1. ... 2. ...)
    numbered_pattern = r'(?:^|\n)(?=(?:\d+\.|\bItem\s+\d+:?)\s+)'
    num_parts = [p.strip() for p in re.split(numbered_pattern, text) if p.strip()]
    if len(num_parts) >= 2:
        chapters = []
        for i, p in enumerate(num_parts):
            first_line = p.split('\n')[0].strip()
            t_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_line)
            t_clean = re.sub(r'[*_`]', '', t_clean)
            title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', t_clean)[:40].strip()
            chapters.append((title or f"Point {i+1}", p))
        if len(chapters) > 1:
            return chapters[:6]

    # 3. Paragraph-based splitting (\n\n+)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paragraphs) >= 2:
        chapters = []
        buf = []
        buf_words = 0
        for p in paragraphs:
            p_words = len(p.split())
            if buf_words > 0 and (buf_words + p_words) > 40:
                c_text = '\n\n'.join(buf)
                first_line = buf[0].split('\n')[0].strip()
                t_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_line)
                t_clean = re.sub(r'[*_`]', '', t_clean)
                title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', t_clean)[:40].strip()
                chapters.append((title or f"Section {len(chapters)+1}", c_text))
                buf = [p]
                buf_words = p_words
            else:
                buf.append(p)
                buf_words += p_words
        if buf:
            c_text = '\n\n'.join(buf)
            first_line = buf[0].split('\n')[0].strip()
            t_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_line)
            t_clean = re.sub(r'[*_`]', '', t_clean)
            title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', t_clean)[:40].strip()
            chapters.append((title or f"Section {len(chapters)+1}", c_text))
        if len(chapters) > 1:
            return chapters[:6]

    # 4. Long continuous text fallback: chunk by sentences (~50-80 words each)
    words = text.split()
    if len(words) > 75:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) >= 2:
            chapters = []
            buf = []
            buf_w = 0
            for s in sentences:
                s_w = len(s.split())
                if buf_w > 0 and (buf_w + s_w) >= 60:
                    c_text = ' '.join(buf)
                    first_words = ' '.join(buf[0].split()[:6])
                    t_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_words)
                    t_clean = re.sub(r'[*_`]', '', t_clean)
                    title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', t_clean)[:40].strip()
                    chapters.append((title or f"Part {len(chapters)+1}", c_text))
                    buf = [s]
                    buf_w = s_w
                else:
                    buf.append(s)
                    buf_w += s_w
            if buf:
                c_text = ' '.join(buf)
                first_words = ' '.join(buf[0].split()[:6])
                t_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_words)
                t_clean = re.sub(r'[*_`]', '', t_clean)
                title = re.sub(r'^[#*\-\d.\s\U00010000-\U0010ffff\u2600-\u27bf]+\s*', '', t_clean)[:40].strip()
                chapters.append((title or f"Part {len(chapters)+1}", c_text))
            if len(chapters) > 1:
                return chapters[:8]

    return [("Overview", text)]

_EDGE_TTS_HEALTHY = True
_EDGE_TTS_LAST_FAILURE = 0.0

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
                print(f"[!] Edge-TTS service returned 403 Forbidden. Tripping circuit breaker to local SAPI.")
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
    on_start: Optional[Callable] = None,
    on_level: Optional[Callable[[float], None]] = None,
    on_finish: Optional[Callable] = None
):
    """Synthesize text and stream directly to 48kHz stereo audio device with seek, pause, and chapter support."""
    if not text or not text.strip():
        return

    chapters = extract_chapters_from_text(text)
    try:
        from desktop.audio.read_aloud import clean_markdown_for_speech
    except ImportError:
        try:
            from audio.read_aloud import clean_markdown_for_speech
        except ImportError:
            clean_markdown_for_speech = lambda t: t

    cleaned_chapters = []
    for title, body in chapters:
        c_body = clean_markdown_for_speech(body)
        if c_body and c_body.strip():
            cleaned_chapters.append((title, c_body))
    if cleaned_chapters:
        chapters = cleaned_chapters

    clean_text = clean_markdown_for_speech(text)
    clean_text = normalize_phonetics(clean_text)

    # 1. Multi-chapter parallel synthesis with Edge-TTS (if healthy)
    global _EDGE_TTS_HEALTHY, _EDGE_TTS_LAST_FAILURE
    use_edge = _EDGE_TTS_HEALTHY or (time.time() - _EDGE_TTS_LAST_FAILURE >= 300)

    if use_edge and len(chapters) > 1:
        try:
            sem = asyncio.Semaphore(3)
            async def _synth_with_sem(c_text: str) -> bytes:
                async with sem:
                    return await _synth_one(c_text, voice=voice, rate=rate, pitch=pitch)

            tasks = [_synth_with_sem(c[1]) for c in chapters]
            mp3_list = await asyncio.gather(*tasks)

            pcm_chunks = []
            titles = []
            for i, (title, _) in enumerate(chapters):
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
                else:
                    raise RuntimeError(f"Failed to synthesize chapter {i + 1} or its spoken notice.")

            if pcm_chunks and len(pcm_chunks) == len(chapters):
                silence = np.zeros((int(0.30 * 48000), 2), dtype=np.float32)
                combined = []
                markers = []
                curr_s = 0
                for i, pcm in enumerate(pcm_chunks):
                    markers.append(curr_s)
                    combined.append(pcm)
                    curr_s += len(pcm)
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
                    global_player.wait()
                    return
        except Exception as e:
            print(f"[!] Parallel Edge-TTS chapter synthesis skipped/failed: {e}")

    # 2. Single-chapter Edge-TTS synthesis (if healthy)
    if use_edge and _EDGE_TTS_HEALTHY:
        try:
            mp3_data = await _synth_one(clean_text, voice=voice, rate=rate, pitch=pitch)
            if mp3_data:
                audio_f32 = decode_mp3_to_pcm(mp3_data)
                global_player.play_pcm(
                    audio_f32,
                    chapter_markers=[0],
                    chapter_titles=[chapters[0][0] if chapters else "Overview"],
                    on_start=on_start,
                    on_level=on_level,
                    on_finish=on_finish
                )
                global_player.wait()
                return
        except Exception as e:
            print(f"[!] Edge-TTS single pass synthesis failed: {e}")

    # 3. Local Windows SAPI Offline Fallback (Immediate, Fail-Safe, 403-Immune)
    print("[!] Seamlessly using local Windows SAPI speech engine (offline fail-safe).")
    if len(chapters) > 1:
        pcm_chunks = []
        titles = []
        for title, body in chapters:
            c_pcm = synth_sapi_pcm(body)
            if len(c_pcm) > 0:
                pcm_chunks.append(c_pcm)
                titles.append(title)
        if pcm_chunks and len(pcm_chunks) == len(chapters):
            silence = np.zeros((int(0.30 * 48000), 2), dtype=np.float32)
            combined = []
            markers = []
            curr_s = 0
            for i, pcm in enumerate(pcm_chunks):
                markers.append(curr_s)
                combined.append(pcm)
                curr_s += len(pcm)
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
                global_player.wait()
                return

    sapi_pcm = synth_sapi_pcm(clean_text)
    if len(sapi_pcm) > 0:
        global_player.play_pcm(
            sapi_pcm,
            chapter_markers=[0],
            chapter_titles=[chapters[0][0] if chapters else "Overview"],
            on_start=on_start,
            on_level=on_level,
            on_finish=on_finish
        )
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
    return global_player.is_playing

def is_paused() -> bool:
    """Returns True if speech is currently paused."""
    return global_player.is_paused

def is_speech_active() -> bool:
    """Returns True if speech is either playing or paused."""
    return global_player.is_active

def get_speech_player() -> SpeechPlayer:
    """Returns the underlying SpeechPlayer instance."""
    return global_player

def speak(
    text: str, 
    voice: str = DEFAULT_VOICE, 
    rate: str = "+0%", 
    pitch: str = "+0Hz",
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
