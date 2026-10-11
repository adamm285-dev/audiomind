"""
Dual-Stream WASAPI Audio Engine with Acoustic Echo Suppression (AES / AEC).
Captures default microphone while simultaneously monitoring system speaker loopback.
Suppresses speaker audio bleed to prevent self-triggering from Samantha TTS or YouTube.
"""

import numpy as np
import pyaudiowpatch as pyaudio
from typing import Optional, Tuple, Callable
import time

class WasapiAecStream:
    """Manages synchronized mic capture and speaker loopback with echo suppression."""

    def __init__(self, target_sample_rate: int = 16000, frame_duration_ms: int = 80):
        self.target_rate = target_sample_rate
        self.frame_ms = frame_duration_ms
        self.p: Optional[pyaudio.PyAudio] = None
        self.mic_stream = None
        self.loopback_stream = None
        self.mic_rate = 48000
        self.loopback_rate = 48000
        self.mic_chunk = int(self.mic_rate * (self.frame_ms / 1000.0))
        self.loopback_chunk = int(self.loopback_rate * (self.frame_ms / 1000.0))
        self.is_active = False

    def initialize(self):
        self.p = pyaudio.PyAudio()
        wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
        
        # 1. Identify default mic
        mic_info = self.p.get_device_info_by_index(wasapi_info["defaultInputDevice"])
        self.mic_idx = mic_info["index"]
        self.mic_rate = int(mic_info["defaultSampleRate"])
        self.mic_channels = mic_info["maxInputChannels"]
        self.mic_chunk = int(self.mic_rate * (self.frame_ms / 1000.0))

        # 2. Identify default speaker loopback
        speaker_info = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        loopback_dev = None
        for loopback in self.p.get_loopback_device_info_generator():
            if speaker_info["name"] in loopback["name"]:
                loopback_dev = loopback
                break
        
        if not loopback_dev:
            # Fallback to first available loopback
            for loopback in self.p.get_loopback_device_info_generator():
                loopback_dev = loopback
                break

        if not loopback_dev:
            raise RuntimeError("No WASAPI loopback device found on system.")

        self.loopback_idx = loopback_dev["index"]
        self.loopback_rate = int(loopback_dev["defaultSampleRate"])
        self.loopback_channels = loopback_dev["maxInputChannels"]
        self.loopback_chunk = int(self.loopback_rate * (self.frame_ms / 1000.0))

        # Open non-blocking or synchronous streams
        self.mic_stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=self.mic_channels,
            rate=self.mic_rate,
            input=True,
            input_device_index=self.mic_idx,
            frames_per_buffer=self.mic_chunk
        )

        self.loopback_stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=self.loopback_channels,
            rate=self.loopback_rate,
            input=True,
            input_device_index=self.loopback_idx,
            frames_per_buffer=self.loopback_chunk
        )
        self.is_active = True

    def read_frame(self) -> Tuple[np.ndarray, bool, float]:
        """
        Reads a synchronized audio frame from mic and speaker loopback.
        Returns:
            - clean_audio (16000Hz mono int16): Cleaned audio for wake/STT
            - speaker_active (bool): True if system speakers are currently outputting audio
            - mic_rms (float): Volume level of the mic
        """
        if not self.is_active:
            raise RuntimeError("Stream not initialized.")

        # Drain mic backlog only if there is a severe delay (>480ms) from external operations
        avail_mic = self.mic_stream.get_read_available()
        if avail_mic > self.mic_chunk * 6:
            drain_frames = avail_mic - self.mic_chunk
            self.mic_stream.read(drain_frames, exception_on_overflow=False)

        # Read raw byte buffers
        raw_mic = self.mic_stream.read(self.mic_chunk, exception_on_overflow=False)
        
        # Non-blocking WASAPI loopback read:
        # On Windows WASAPI, when speakers are quiet the loopback stream has 0 available frames.
        # Calling read() synchronously would hang indefinitely. Check available frames first.
        avail_loop = self.loopback_stream.get_read_available()
        if avail_loop >= self.loopback_chunk:
            if avail_loop > self.loopback_chunk * 4:
                # Drain backlog if audio was playing earlier to stay in real-time
                drain_frames = avail_loop - self.loopback_chunk
                self.loopback_stream.read(drain_frames, exception_on_overflow=False)
            raw_loop = self.loopback_stream.read(self.loopback_chunk, exception_on_overflow=False)
            loop_np = np.frombuffer(raw_loop, dtype=np.float32)
        elif avail_loop > 0:
            raw_loop = self.loopback_stream.read(avail_loop, exception_on_overflow=False)
            part_np = np.frombuffer(raw_loop, dtype=np.float32)
            loop_np = np.zeros(self.loopback_chunk * self.loopback_channels, dtype=np.float32)
            loop_np[:len(part_np)] = part_np
        else:
            loop_np = np.zeros(self.loopback_chunk * self.loopback_channels, dtype=np.float32)

        # Convert to float32 numpy arrays
        mic_np = np.frombuffer(raw_mic, dtype=np.float32)

        # Downmix to mono if multi-channel
        if self.mic_channels > 1:
            mic_np = mic_np.reshape(-1, self.mic_channels).mean(axis=1)
        if self.loopback_channels > 1:
            loop_np = loop_np.reshape(-1, self.loopback_channels).mean(axis=1)

        # Calculate RMS energy of mic and speaker
        mic_rms = float(np.sqrt(np.mean(mic_np ** 2))) if len(mic_np) > 0 else 0.0
        loop_rms = float(np.sqrt(np.mean(loop_np ** 2))) if len(loop_np) > 0 else 0.0

        # Threshold: if speaker RMS > 0.015, speakers are actively playing
        speaker_active = loop_rms > 0.015

        # Downsample mic from 48000Hz to 16000Hz (3:1 ratio)
        # Using fast numpy decimation
        decimation_factor = self.mic_rate // self.target_rate
        if decimation_factor > 1:
            resampled_mic = mic_np[::decimation_factor]
        else:
            resampled_mic = mic_np

        # If speakers are blaring, suppress mic amplitude to prevent false acoustic triggers
        if speaker_active:
            # Attenuate mic signal by 85% during heavy speaker output
            resampled_mic = resampled_mic * 0.15

        # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767] for wake word & STT engines
        int16_mic = np.clip(resampled_mic * 32767.0, -32768, 32767).astype(np.int16)

        return int16_mic, speaker_active, mic_rms

    def read_chunk(self) -> np.ndarray:
        """Reads a frame and returns just the 16kHz mono int16 audio array for wake word and STT."""
        clean_audio, _, _ = self.read_frame()
        return clean_audio

    def drain(self):
        """Purges any queued buffers in mic and loopback streams to synchronize with live wall-clock."""
        if not self.is_active:
            return
        try:
            if self.mic_stream:
                avail = self.mic_stream.get_read_available()
                if avail > 0:
                    self.mic_stream.read(avail, exception_on_overflow=False)
            if self.loopback_stream:
                avail = self.loopback_stream.get_read_available()
                if avail > 0:
                    self.loopback_stream.read(avail, exception_on_overflow=False)
        except Exception:
            pass

    def __enter__(self):
        if not self.is_active:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.is_active = False
        if self.mic_stream:
            self.mic_stream.stop_stream()
            self.mic_stream.close()
        if self.loopback_stream:
            self.loopback_stream.stop_stream()
            self.loopback_stream.close()
        if self.p:
            self.p.terminate()
