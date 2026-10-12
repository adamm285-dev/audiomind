"""
Unit test for Waveform HUD visibility transitions and system tray animated icon generator.
"""
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import math
import pytest
from desktop.app import create_tray_icon_image
from desktop.ui.hud import WaveformHud

def test_tray_icon_all_states_and_pulses():
    """Verify that tray icon renders correctly across all states and pulse phases without errors."""
    states = ["listening", "user_speaking", "processing", "thinking", "anti_speaking", "muted"]
    pulses = [0.0, 0.25, 0.5, 0.75, 1.0]

    for state in states:
        for p in pulses:
            img = create_tray_icon_image(state=state, pulse=p)
            assert img is not None
            assert img.size == (64, 64)
            assert img.mode == "RGBA"

def test_waveform_hud_visibility_and_status_logic():
    """Verify HUD state transitions, auto-visibility on active states, and audio levels."""
    hud = WaveformHud(position="bottom_right")
    
    # Initially hidden
    assert hud.visible is False
    assert hud.state == "idle"

    # Calling show() activates visibility
    hud.show(state="listening", status="Anti • Listening")
    assert hud.visible is True
    assert hud.state == "listening"
    assert hud.status_text == "Anti • Listening"

    # Audio level updates
    hud.update_audio_level(0.75)
    assert abs(hud.audio_level - 0.75) < 0.001

    # Calling hide() deactivates visibility
    hud.hide()
    assert hud.visible is False

    # Calling set_status() with an active state ("speaking") automatically makes it visible
    hud.set_status("Anti • Speaking", state="speaking")
    assert hud.visible is True
    assert hud.state == "speaking"

    # Reset with hide()
    hud.hide()
    assert hud.visible is False

    # Calling set_status() with "processing" automatically makes it visible
    hud.set_status("Anti • Thinking", state="processing")
    assert hud.visible is True
    assert hud.state == "processing"

def test_waveform_hud_click_callback():
    """Verify HUD on_click callback is invoked on canvas click."""
    hud = WaveformHud(position="bottom_right")
    clicked = []
    hud.on_click = lambda: clicked.append(True)
    assert hud._on_canvas_click() == "break"
    assert len(clicked) == 1

def test_extract_chapters_from_text():
    """Verify chapter extraction across markdown headings, numbered items, and paragraphs."""
    from desktop.audio.tts import extract_chapters_from_text

    # 1. Markdown headings
    heading_text = (
        "## Setup & Prerequisites\nFirst install the dependencies.\n\n"
        "## Execution\nRun the main daemon script.\n\n"
        "## Verification\nRun all test suites to confirm."
    )
    ch = extract_chapters_from_text(heading_text)
    assert len(ch) == 3
    assert ch[0][0] == "Setup & Prerequisites"
    assert "First install" in ch[0][1]
    assert ch[1][0] == "Execution"
    assert ch[2][0] == "Verification"

    # 2. Numbered items
    numbered_text = (
        "1. First step is cloning the repository.\n"
        "2. Second step is setting up the environment variables.\n"
        "3. Third step is running the test suite."
    )
    ch_num = extract_chapters_from_text(numbered_text)
    assert len(ch_num) == 3
    assert "First step" in ch_num[0][0]
    assert "Second step" in ch_num[1][0]
    assert "Third step" in ch_num[2][0]

    # 3. Short plain text fallback
    plain_text = "This is a brief single sentence response."
    ch_plain = extract_chapters_from_text(plain_text)
    assert len(ch_plain) == 1
    assert ch_plain[0][0] == "Overview"
    assert ch_plain[0][1] == plain_text

def test_speech_player_fast_forward_and_chapter_navigation():
    """Verify SpeechPlayer 5-second fast forward and sample-accurate chapter navigation."""
    import numpy as np
    from desktop.audio.player import SpeechPlayer

    player = SpeechPlayer(samplerate=48000)
    # 15 seconds of stereo float32 silence: 720,000 frames
    sr = 48000
    pcm = np.zeros((15 * sr, 2), dtype=np.float32)

    # 3 chapters: Chapter 1 at 0s, Chapter 2 at 5s (240000), Chapter 3 at 10s (480000)
    markers = [0, 5 * sr, 10 * sr]
    titles = ["Introduction", "Deep Dive", "Conclusion"]

    events = []
    player.on_state_change = lambda st: events.append(st)

    player.play_pcm(pcm, chapter_markers=markers, chapter_titles=titles)
    # Prevent background audio stream in headless tests:
    player._is_playing = True
    player._is_paused = False

    assert player.total_chapters == 3
    assert player.current_chapter_index == 0
    assert player.current_chapter_title == "Introduction"

    # Fast forward 5.0 seconds
    pos = player.fast_forward(5.0)
    assert abs(pos - 5.0) < 0.01
    assert "forwarded" in events
    assert player.current_chapter_index == 1
    assert player.current_chapter_title == "Deep Dive"

    # Skip to next chapter (jumps from Ch 2 to Ch 3 at 10.0s)
    events.clear()
    next_idx = player.skip_to_next_chapter()
    assert next_idx == 2
    assert player.current_chapter_index == 2
    assert player.current_chapter_title == "Conclusion"
    assert "chapter_skipped" in events

    # Repeat last chapter: currently at 10.0s (0.0s into Ch 3 <= 2s threshold) -> jumps to Ch 2 (5.0s)
    events.clear()
    rep_idx = player.repeat_last_chapter()
    assert rep_idx == 1
    assert player.current_chapter_index == 1
    assert player.current_idx == 5 * sr
    assert "chapter_repeated" in events

    # Move forward 3.0s into Chapter 2 (total 8.0s)
    player.fast_forward(3.0)
    assert player.current_chapter_index == 1
    assert player.current_idx == 8 * sr

    # Repeat last chapter: 3.0s into chapter (> 2.0s threshold) -> restarts current chapter (Ch 2 at 5.0s)
    events.clear()
    rep_idx2 = player.repeat_last_chapter()
    assert rep_idx2 == 1
    assert player.current_idx == 5 * sr
    assert "chapter_repeated" in events

    player.stop()

def test_match_playback_intent_table_driven():
    """Verify playback intent matching with collision immunity and inactive speech gating."""
    from desktop.app import match_playback_intent

    # 1. Collision phrases that must NEVER match, regardless of speech state
    collision_phrases = [
        "set up port forwarding",
        "this fix is straightforward",
        "add a next section to the README",
        "continue with the refactor",
        "back up the database",
        "add a pause button",
        "write the resume parser",
        "forward",
        "fast forward",
        "forward 5",
        "forward 5 seconds",
    ]

    for phrase in collision_phrases:
        assert match_playback_intent(phrase, speech_active=True) is None, f"Phrase '{phrase}' matched unexpectedly while active"
        assert match_playback_intent(phrase, speech_active=False) is None, f"Phrase '{phrase}' matched unexpectedly while inactive"

    # 2. When speech is inactive (False), even legitimate commands must return None
    legit_commands = [
        ("pause", "PAUSE"),
        ("pause speech", "PAUSE"),
        ("hold on", "PAUSE"),
        ("resume", "RESUME"),
        ("continue", "RESUME"),
        ("unpause", "RESUME"),
        ("rewind", "REWIND_5"),
        ("go back", "REWIND_5"),
        ("back up 5", "REWIND_5"),
        ("next chapter", "NEXT_CHAPTER"),
        ("skip chapter", "NEXT_CHAPTER"),
        ("repeat chapter", "REPEAT_CHAPTER"),
        ("previous chapter", "REPEAT_CHAPTER"),
        ("stop", "STOP"),
        ("stop talking", "STOP"),
        ("cancel", "STOP"),
    ]

    for phrase, _ in legit_commands:
        assert match_playback_intent(phrase, speech_active=False) is None, f"Command '{phrase}' should return None when speech is inactive"

    # 3. When speech is active (True), legitimate commands match their expected intent
    for phrase, expected_intent in legit_commands:
        assert match_playback_intent(phrase, speech_active=True) == expected_intent, f"Command '{phrase}' did not match {expected_intent}"


def test_chapter_synthesis_index_alignment_and_spoken_notice(monkeypatch):
    """
    Verify parallel chapter synthesis concurrency, strict index alignment,
    and spoken notice insertion when chapter 2 of 4 fails.
    """
    import asyncio
    import numpy as np
    import desktop.audio.tts as tts_module

    # 4 distinct chapters
    text = (
        "## Introduction\nWelcome to the first chapter.\n\n"
        "## Architecture\nHere is the detailed architecture.\n\n"
        "## Implementation\nStep by step guide to coding.\n\n"
        "## Summary\nFinal thoughts and recap."
    )

    chapters = tts_module.extract_chapters_from_text(text)
    assert len(chapters) == 4
    expected_titles = [c[0] for c in chapters]
    assert expected_titles == ["Introduction", "Architecture", "Implementation", "Summary"]

    synth_calls = []

    # Fake synthesis function:
    # Fails when asked for Chapter 2 text ("Architecture" body)
    # Succeeds on Chapter 1, 3, 4, and succeeds on the spoken notice "Part 2 could not be read."
    async def mock_synth_one(c_text, voice=tts_module.DEFAULT_VOICE, rate="+0%", pitch="+0Hz"):
        synth_calls.append(c_text)
        if "detailed architecture" in c_text:
            # Chapter 2 fails
            return b""
        elif "Part 2 could not be read" in c_text:
            # Notice succeeds
            return b"NOTICE_AUDIO_DATA"
        else:
            return f"AUDIO_FOR_{c_text[:10]}".encode("utf-8")

    # Mock decode_mp3_to_pcm to produce dummy float32 arrays
    def mock_decode(mp3_data):
        if mp3_data == b"NOTICE_AUDIO_DATA":
            # 1 second of notice audio (48000 frames)
            return np.ones((48000, 2), dtype=np.float32) * 0.5
        elif mp3_data:
            # 2 seconds of normal chapter audio (96000 frames)
            return np.ones((96000, 2), dtype=np.float32)
        return np.empty((0, 2), dtype=np.float32)

    played_pcm = []
    played_kwargs = {}

    class MockPlayer:
        def play_pcm(self, audio_f32, chapter_markers=None, chapter_titles=None, **kwargs):
            played_pcm.append(audio_f32)
            played_kwargs["markers"] = chapter_markers
            played_kwargs["titles"] = chapter_titles
        def wait(self):
            pass

    monkeypatch.setattr(tts_module, "_synth_one", mock_synth_one)
    monkeypatch.setattr(tts_module, "decode_mp3_to_pcm", mock_decode)
    monkeypatch.setattr(tts_module, "global_player", MockPlayer())

    asyncio.run(tts_module.speak_async(text))

    # Assert 4 chapters were played with strict index alignment
    assert len(played_pcm) == 1
    assert played_kwargs["titles"] == expected_titles
    assert len(played_kwargs["markers"]) == 4

    # Assert notice for chapter 2 was synthesized
    assert any("Part 2 could not be read" in call for call in synth_calls)

def test_single_chapter_skip_does_not_abort_playback():
    """Verify that skip_to_next_chapter does NOT abruptly terminate audio when only 1 chapter exists."""
    import numpy as np
    from desktop.audio.player import SpeechPlayer

    player = SpeechPlayer(samplerate=48000)
    sr = 48000
    pcm = np.zeros((30 * sr, 2), dtype=np.float32)

    player.play_pcm(pcm, chapter_markers=[0], chapter_titles=["Single Chapter"])
    player._is_playing = True
    player._is_paused = False

    assert player.total_chapters == 1
    assert player.current_idx == 0

    # Skipping next chapter on a single-chapter stream advances forward without terminating
    player.skip_to_next_chapter()
    assert player.is_active is True
    assert player.current_idx > 0
    assert player.current_idx < len(pcm)

    player.stop()

def test_extract_chapters_clean_titles_and_continuous_text():
    """Verify chapter title link/emoji cleaning and sentence-cluster fallback for long text."""
    from desktop.audio.tts import extract_chapters_from_text

    # 1. Title with markdown link and emojis
    raw_md = (
        "## 🚀 Chapter 1: Inspecting [`README.md`](file:///path/to/readme#L10)\nFirst body section.\n\n"
        "## 🛡️ Chapter 2: Security in [`SECURITY.md`](file:///path/to/sec)\nSecond body section."
    )
    ch = extract_chapters_from_text(raw_md)
    assert len(ch) == 2
    assert "README.md" in ch[0][0]
    assert "[" not in ch[0][0]
    assert "SECURITY.md" in ch[1][0]
    assert "[" not in ch[1][0]

    # 2. Continuous text wall (> 75 words) with NO markdown headings or numbers
    wall_of_text = (
        "Antigravity is an advanced agentic coding environment developed by Google DeepMind. "
        "It supports autonomous pair programming, multi-turn reasoning, and system tray companions. "
        "Users can interact with the system via voice, keyboard shortcuts, or mobile notifications. "
        "The ambient voice assistant connects directly to active transcripts and speaks out summaries. "
        "Furthermore, developers can highlight any text across their desktop applications and have Anti read it aloud. "
        "This seamless cross-application interaction provides hands-free accessibility for code reviews, documentation reading, and debugging traces."
    )
    ch_wall = extract_chapters_from_text(wall_of_text)
    assert len(ch_wall) >= 2, f"Expected continuous text to be split into >= 2 chapters, got {len(ch_wall)}"

def test_capture_highlighted_text_fallback(monkeypatch):
    """Verify capture_highlighted_text returns cleaned string from clipboard or None."""
    from desktop.audio.read_aloud import capture_highlighted_text
    import pyperclip

    # Mock pyperclip to return sample copied text
    monkeypatch.setattr(pyperclip, "paste", lambda: "## Sample Highlighted Markdown\nHere is selected text from any window.")
    monkeypatch.setattr(pyperclip, "copy", lambda text: None)

    res = capture_highlighted_text(target_hwnd=None)
    assert res is not None
    assert "Sample Highlighted Markdown" in res
    assert "Here is selected text" in res

def test_tts_sapi_fallback_when_edge_tts_fails(monkeypatch):
    """Verify that speak_async automatically fails over to local Windows SAPI when Edge-TTS fails."""
    import asyncio
    import numpy as np
    import desktop.audio.tts as tts_module

    # Force Edge-TTS to return b""
    async def failing_synth_one(c_text, **kwargs):
        return b""

    # SAPI returns dummy 48kHz stereo PCM
    sapi_called = []
    def mock_sapi_pcm(text, samplerate=48000):
        sapi_called.append(text)
        return np.ones((24000, 2), dtype=np.float32) * 0.3

    played_pcm = []
    class MockPlayer:
        def play_pcm(self, audio_f32, chapter_markers=None, chapter_titles=None, **kwargs):
            played_pcm.append(audio_f32)
        def wait(self):
            pass

    monkeypatch.setattr(tts_module, "_synth_one", failing_synth_one)
    monkeypatch.setattr(tts_module, "synth_sapi_pcm", mock_sapi_pcm)
    monkeypatch.setattr(tts_module, "global_player", MockPlayer())

    test_text = "This is a test prompt that should seamlessly play through SAPI."
    asyncio.run(tts_module.speak_async(test_text))

    assert len(sapi_called) >= 1
    assert len(played_pcm) == 1
    assert played_pcm[0].shape == (24000, 2)



