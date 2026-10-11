"""
Anti Speech Playback Engine with Seekable Buffer, Real-time RMS telemetry,
Pause/Resume, and 5s/10s Rewind support.
"""
import time
import threading
from typing import Optional, Callable, Any
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

class _CallbackStop(Exception):
    pass

CallbackStop = getattr(sd, 'CallbackStop', _CallbackStop) if sd else _CallbackStop

class SpeechPlayer:
    """
    Hardware-matched 48kHz audio player supporting instant pause, resume,
    interactive rewind (back up 5s/10s), fast-forward (5s), and chapter navigation.
    """
    def __init__(self, samplerate: int = 48000):
        self.samplerate = samplerate
        self.audio_data: Optional[np.ndarray] = None
        self.current_idx: int = 0
        self._is_playing: bool = False
        self._is_paused: bool = False
        self._stream: Optional[Any] = None
        self._lock = threading.RLock()

        # Telemetry & lifecycle callbacks
        self.on_level_callback: Optional[Callable[[float], None]] = None
        self.on_finish_callback: Optional[Callable[[], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None

        # Chapter navigation markers (sample offsets) and titles
        self.chapter_markers: list[int] = [0]
        self.chapter_titles: list[str] = ["Overview"]

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if not self._is_playing or self._is_paused:
                outdata.fill(0)
                return

            if self.audio_data is None:
                outdata.fill(0)
                raise CallbackStop()

            remaining = len(self.audio_data) - self.current_idx
            if remaining <= 0:
                outdata.fill(0)
                raise CallbackStop()

            chunk_len = min(frames, remaining)
            outdata[:chunk_len] = self.audio_data[self.current_idx:self.current_idx + chunk_len]
            if chunk_len < frames:
                outdata[chunk_len:].fill(0)

            self.current_idx += chunk_len

        # Calculate live audio RMS for the Waveform HUD
        rms = float(np.sqrt(np.mean(outdata[:chunk_len] ** 2)))
        # Normalize RMS (typically 0.01 to 0.40) to a 0.0 - 1.0 range
        normalized = min(1.0, max(0.0, rms * 3.5))
        if self.on_level_callback:
            try:
                self.on_level_callback(normalized)
            except Exception:
                pass

        if remaining <= chunk_len:
            raise CallbackStop()

    def play_pcm(
        self,
        audio_data: np.ndarray,
        chapter_markers: Optional[list[int]] = None,
        chapter_titles: Optional[list[str]] = None,
        on_start: Optional[Callable[[], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
        on_finish: Optional[Callable[[], None]] = None
    ):
        """Start playing a PCM float32 audio buffer from the beginning with optional chapter markers."""
        self.stop()
        with self._lock:
            self.audio_data = audio_data
            self.current_idx = 0
            self._is_playing = True
            self._is_paused = False
            self.on_level_callback = on_level
            self.on_finish_callback = on_finish

            # Setup chapter markers (always includes at least index 0)
            if chapter_markers and len(chapter_markers) > 0:
                clean_markers = sorted([max(0, min(len(audio_data), int(m))) for m in chapter_markers])
                if clean_markers[0] != 0:
                    clean_markers.insert(0, 0)
                self.chapter_markers = clean_markers
            else:
                self.chapter_markers = [0]

            if chapter_titles and len(chapter_titles) == len(self.chapter_markers):
                self.chapter_titles = list(chapter_titles)
            else:
                self.chapter_titles = [f"Chapter {i+1}" for i in range(len(self.chapter_markers))]

        if on_start:
            try:
                on_start()
            except Exception:
                pass

        if self.on_state_change:
            try:
                self.on_state_change("playing")
            except Exception:
                pass

        def _finished():
            with self._lock:
                self._is_playing = False
                self._is_paused = False
            if self.on_finish_callback:
                try:
                    self.on_finish_callback()
                except Exception:
                    pass
            if self.on_state_change:
                try:
                    self.on_state_change("finished")
                except Exception:
                    pass

        if sd is not None:
            channels = 2 if audio_data.ndim == 2 else 1
            self._stream = sd.OutputStream(
                samplerate=self.samplerate,
                channels=channels,
                dtype='float32',
                callback=self._callback,
                finished_callback=_finished
            )
            self._stream.start()

    def pause(self) -> bool:
        """Pause playback while holding current playback position."""
        with self._lock:
            if self._is_playing and not self._is_paused:
                self._is_paused = True
                if self.on_state_change:
                    try:
                        self.on_state_change("paused")
                    except Exception:
                        pass
                return True
        return False

    def resume(self) -> bool:
        """Resume playback from the exact paused position."""
        with self._lock:
            if self._is_playing and self._is_paused:
                self._is_paused = False
                if self.on_state_change:
                    try:
                        self.on_state_change("playing")
                    except Exception:
                        pass
                return True
        return False

    def toggle_pause(self) -> bool:
        """Toggle between pause and resume states."""
        with self._lock:
            if not self._is_playing:
                return False
            if self._is_paused:
                self._is_paused = False
                new_state = "playing"
            else:
                self._is_paused = True
                new_state = "paused"

        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception:
                pass
        return self._is_paused

    def rewind(self, seconds: float = 10.0) -> float:
        """
        Rewinds playback backward by the specified number of seconds (default 10s).
        Returns the new playback position in seconds.
        """
        with self._lock:
            if self.audio_data is None:
                return 0.0
            delta_samples = int(seconds * self.samplerate)
            self.current_idx = max(0, self.current_idx - delta_samples)
            new_pos = self.current_idx / self.samplerate

        if self.on_state_change:
            try:
                self.on_state_change("rewound")
            except Exception:
                pass
        return new_pos

    def fast_forward(self, seconds: float = 5.0) -> float:
        """
        Skips playback forward by the specified number of seconds (default 5s).
        Returns the new playback position in seconds.
        """
        with self._lock:
            if self.audio_data is None:
                return 0.0
            delta_samples = int(seconds * self.samplerate)
            self.current_idx = min(len(self.audio_data), self.current_idx + delta_samples)
            new_pos = self.current_idx / self.samplerate

        if self.on_state_change:
            try:
                self.on_state_change("forwarded")
            except Exception:
                pass
        return new_pos

    @property
    def current_chapter_index(self) -> int:
        """Returns 0-based index of the currently playing chapter."""
        with self._lock:
            idx = self.current_idx
            curr = 0
            for i, marker in enumerate(self.chapter_markers):
                if idx >= marker:
                    curr = i
                else:
                    break
            return curr

    @property
    def total_chapters(self) -> int:
        """Total number of chapters in the current speech buffer."""
        return len(self.chapter_markers)

    @property
    def current_chapter_title(self) -> str:
        """Title/label of the currently active chapter."""
        idx = self.current_chapter_index
        if 0 <= idx < len(self.chapter_titles):
            return self.chapter_titles[idx]
        return f"Chapter {idx + 1}"

    def skip_to_next_chapter(self) -> Optional[int]:
        """
        Jumps playback to the beginning of the next chapter.
        If already on the last chapter or single chapter, advances within audio without stopping.
        Returns the new 0-based chapter index, or None if not playing.
        """
        with self._lock:
            if not self._is_playing or self.audio_data is None:
                return None
            curr = self.current_chapter_index
            if curr + 1 < len(self.chapter_markers):
                target_chapter = curr + 1
                self.current_idx = self.chapter_markers[target_chapter]
            else:
                if len(self.chapter_markers) <= 1:
                    delta_samples = int(10.0 * self.samplerate)
                    self.current_idx = min(len(self.audio_data) - int(0.5 * self.samplerate), self.current_idx + delta_samples)
                    self.current_idx = max(0, self.current_idx)
                    target_chapter = curr
                else:
                    self.current_idx = len(self.audio_data)
                    target_chapter = curr

        if self.on_state_change:
            try:
                self.on_state_change("chapter_skipped")
            except Exception:
                pass
        return target_chapter

    def repeat_last_chapter(self) -> Optional[int]:
        """
        If playback has progressed more than 2 seconds into the current chapter,
        restarts the current chapter from its beginning (repeating it).
        If within the first 2 seconds, jumps to the beginning of the previous chapter.
        Returns the new 0-based chapter index, or None if not playing.
        """
        with self._lock:
            if not self._is_playing or self.audio_data is None:
                return None
            curr = self.current_chapter_index
            curr_marker = self.chapter_markers[curr]
            samples_into_chapter = self.current_idx - curr_marker
            threshold_samples = int(2.0 * self.samplerate)

            if samples_into_chapter > threshold_samples or curr == 0:
                self.current_idx = curr_marker
                target_chapter = curr
            else:
                target_chapter = curr - 1
                self.current_idx = self.chapter_markers[target_chapter]

        if self.on_state_change:
            try:
                self.on_state_change("chapter_repeated")
            except Exception:
                pass
        return target_chapter

    def stop(self):
        """Completely stop playback and close stream."""
        with self._lock:
            self._is_playing = False
            self._is_paused = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self.on_state_change:
            try:
                self.on_state_change("stopped")
            except Exception:
                pass

    def wait(self):
        """Wait until playback has completed."""
        while self._is_playing:
            time.sleep(0.04)

    @property
    def is_playing(self) -> bool:
        """Returns True if audio is actively playing sound (not paused)."""
        return self._is_playing and not self._is_paused

    @property
    def is_paused(self) -> bool:
        """Returns True if an audio stream is loaded and currently paused."""
        return self._is_playing and self._is_paused

    @property
    def is_active(self) -> bool:
        """Returns True if audio is either playing or paused."""
        return self._is_playing

    @property
    def position_seconds(self) -> float:
        """Current playback position in seconds."""
        return self.current_idx / self.samplerate

    @property
    def duration_seconds(self) -> float:
        """Total duration of current audio in seconds."""
        if self.audio_data is None:
            return 0.0
        return len(self.audio_data) / self.samplerate

# Global singleton player
global_player = SpeechPlayer()
