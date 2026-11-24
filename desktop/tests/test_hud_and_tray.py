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

def test_waveform_hud_chat_tag_isolation():
    """Verify HUD LCD display isolates bracketed chat name and drops overflow chapter/queue text."""
    hud = WaveformHud(position="bottom_right")
    hud.set_status("[Open Source] Ch 1/3: Intro • Q:2", state="speaking")
    assert hud.status_text == "[Open Source] Ch 1/3: Intro • Q:2"

    # Simulate LCD text formatting
    display_label = hud.status_text
    if display_label.startswith("[") and "]" in display_label:
        end_b = display_label.find("]")
        display_label = display_label[:end_b + 1]
    assert display_label == "[Open Source]"

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

    monkeypatch.setattr(tts_module, "get_kokoro", lambda: None)
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

def test_capture_highlighted_text_no_selection_returns_none(monkeypatch):
    """Verify capture_highlighted_text returns None and restores prior clipboard when no text is selected."""
    from desktop.audio.read_aloud import capture_highlighted_text
    import pyperclip

    # Prior clipboard had stale text, copy simulation fails to change sentinel
    clipboard_state = {"content": "stale_old_slide_text"}
    def fake_paste():
        return clipboard_state["content"]
    def fake_copy(t):
        clipboard_state["content"] = t

    monkeypatch.setattr(pyperclip, "paste", fake_paste)
    monkeypatch.setattr(pyperclip, "copy", fake_copy)

    # When no new text is selected, capture_highlighted_text returns None and restores prior clipboard
    res = capture_highlighted_text(target_hwnd=None)
    assert res is None
    assert clipboard_state["content"] == "stale_old_slide_text"

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

    monkeypatch.setattr(tts_module, "get_kokoro", lambda: None)
    monkeypatch.setattr(tts_module, "_synth_one", failing_synth_one)
    monkeypatch.setattr(tts_module, "synth_sapi_pcm", mock_sapi_pcm)
    monkeypatch.setattr(tts_module, "global_player", MockPlayer())

    test_text = "This is a test prompt that should seamlessly play through SAPI."
    asyncio.run(tts_module.speak_async(test_text))

    assert len(sapi_called) >= 1
    assert len(played_pcm) == 1
    assert played_pcm[0].shape == (24000, 2)

def test_kokoro_tiered_synthesis_and_chapter_alignment(monkeypatch):
    """Verify that speak_async prioritizes Kokoro local neural TTS with chapter alignment."""
    import asyncio
    import numpy as np
    import desktop.audio.tts as tts_module

    text = (
        "## Setup\nFirst step here.\n\n"
        "## Run\nSecond step here."
    )

    kokoro_calls = []
    def mock_synth_kokoro(t, voice=None, speed=1.0):
        kokoro_calls.append(t)
        return np.ones((24000, 2), dtype=np.float32) * 0.4

    played_pcm = []
    played_kwargs = {}
    class MockPlayer:
        def play_pcm(self, audio_f32, chapter_markers=None, chapter_titles=None, **kwargs):
            played_pcm.append(audio_f32)
            played_kwargs["markers"] = chapter_markers
            played_kwargs["titles"] = chapter_titles
        def wait(self):
            pass

    class DummyKokoro:
        def get_voices(self):
            return ["af_heart"]

    monkeypatch.setattr(tts_module, "get_kokoro", lambda: DummyKokoro())
    monkeypatch.setattr(tts_module, "synth_kokoro_pcm", mock_synth_kokoro)
    monkeypatch.setattr(tts_module, "global_player", MockPlayer())

    asyncio.run(tts_module.speak_async(text))

    assert len(kokoro_calls) == 2
    assert len(played_pcm) == 1
    assert played_kwargs["titles"] == ["Setup", "Run"]
    assert len(played_kwargs["markers"]) == 2

def test_speech_queue_item_chat_tag_extraction():
    """Verify human chat title resolution and clean empty fallback (no cryptic hex)."""
    from desktop.app import SpeechQueueItem

    # Path with active database entry (resolves 'Open Source')
    p_win = r"C:\Users\test\.gemini\antigravity\brain\32caa6ee-c05c-409c-bf5b-a4db56b32632\.system_generated\logs\transcript.jsonl"
    item1 = SpeechQueueItem(text="Hello", filepath=p_win, step_index=10)
    assert item1.chat_tag in ("Open Source", "")

    # Non-existent ID -> cleanly falls back to empty string (no cryptic hex hash)
    p_nix = "/home/user/.gemini/antigravity/brain/00000000-0000-0000-0000-000000000000/.system_generated/logs/transcript.jsonl"
    item2 = SpeechQueueItem(text="World", filepath=p_nix, step_index=15)
    assert item2.chat_tag == ""

    # Missing or unrecognized path -> empty string
    item3 = SpeechQueueItem(text="Standalone", filepath=None)
    assert item3.chat_tag == ""

    item4 = SpeechQueueItem(text="Other", filepath=r"C:\workspace\file.txt")
    assert item4.chat_tag == ""

def test_speech_player_streaming_append_pcm():
    """Verify SpeechPlayer streaming playback, dynamic append_pcm, and marker updates."""
    import numpy as np
    from desktop.audio.player import SpeechPlayer

    player = SpeechPlayer(samplerate=48000)
    sr = 48000
    pcm1 = np.ones((2 * sr, 2), dtype=np.float32) * 0.5  # 2s audio
    pcm2 = np.ones((3 * sr, 2), dtype=np.float32) * 0.3  # 3s audio

    # Play initial chapter with stream_complete=False
    player.play_pcm(pcm1, chapter_markers=[0], chapter_titles=["Chapter 1"], stream_complete=False)
    player._is_playing = True
    player._is_paused = False

    assert player.total_chapters == 1
    assert player._stream_complete is False
    assert player.current_chapter_title == "Chapter 1"

    # Append Chapter 2 dynamically
    player.append_pcm(pcm2, chapter_title="Chapter 2", pause_sec=0.25)
    assert player.total_chapters == 2
    assert player.chapter_titles == ["Chapter 1", "Chapter 2"]
    # Check that new marker is placed after 2s + 0.25s silence
    expected_marker = int((2.0 + 0.25) * sr)
    assert player.chapter_markers[1] == expected_marker

    # Mark stream complete
    player.set_stream_complete(True)
    assert player._stream_complete is True

    player.stop()
    assert player._stream_complete is True

def test_match_playback_intent_skip_output():
    """Verify SKIP_OUTPUT intent recognition for fast response skipping."""
    from desktop.app import match_playback_intent

    skip_phrases = [
        "skip output",
        "next output",
        "skip response",
        "next response",
        "skip to next output",
        "skip to next response",
    ]

    for phrase in skip_phrases:
        # Must match when speech is active
        assert match_playback_intent(phrase, speech_active=True) == "SKIP_OUTPUT", f"Phrase '{phrase}' should match SKIP_OUTPUT"
        # Must return None when speech is inactive
        assert match_playback_intent(phrase, speech_active=False) is None, f"Phrase '{phrase}' should be gated when inactive"

def test_hud_right_click_and_double_click_callbacks():
    """Verify HUD right-click and double-click callbacks trigger the skip output callback."""
    from desktop.ui.hud import WaveformHud

    hud = WaveformHud(position="bottom_right")
    right_clicks = []
    double_clicks = []

    hud.on_right_click = lambda: right_clicks.append(True)
    hud.on_double_click = lambda: double_clicks.append(True)

    assert hud._on_canvas_right_click() == "break"
    assert len(right_clicks) == 1

    assert hud._on_canvas_double_click() == "break"
    assert len(double_clicks) == 1

    # If double-click is not set, it should fall back to on_right_click
    hud.on_double_click = None
    assert hud._on_canvas_double_click() == "break"
    assert len(right_clicks) == 2

def test_skip_next_chapter_right_click_workflow(monkeypatch):
    """Verify skip_next_chapter advances chapters, unpauses, and cascades to skip_current_output when queue is waiting."""
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem

    # Dummy assistant state
    class DummyAssistant:
        def __init__(self):
            self.speech_queue = []
            self.current_speech_item = SpeechQueueItem("Test", filepath=r"C:\test\32caa6ee-0000\log.jsonl")
            self.hud_enabled = True
            self.hud = type("DummyHud", (), {"set_status": lambda *a, **k: None})()
            self.skipped_output = False

        def skip_current_output(self, icon=None, item=None):
            self.skipped_output = True

    asst = DummyAssistant()

    # 1. When speech is inactive -> does nothing
    monkeypatch.setattr(app_module, "is_speech_active", lambda: False)
    app_module.AntiTrayApp.skip_next_chapter(asst)
    assert asst.skipped_output is False

    # 2. When speech is active and chapter 1 of 3
    chapter_state = [1, 3, "Overview"]
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)
    monkeypatch.setattr(app_module, "get_chapter_info", lambda: tuple(chapter_state))
    monkeypatch.setattr(app_module, "is_paused", lambda: True)
    resumed = []
    monkeypatch.setattr(app_module, "resume_speech", lambda: resumed.append(True))
    skipped_ch = []
    monkeypatch.setattr(app_module, "skip_to_next_chapter", lambda: skipped_ch.append(True))
    monkeypatch.setattr(app_module, "play_chime", lambda rising=True: None)

    app_module.AntiTrayApp.skip_next_chapter(asst)
    assert len(skipped_ch) == 1
    assert len(resumed) == 1
    assert asst.skipped_output is False

    # 3. When on final chapter (3 of 3) and queue is NOT empty -> cascades to skip_current_output
    chapter_state[0] = 3
    asst.speech_queue.append(SpeechQueueItem("Next speech item"))
    app_module.AntiTrayApp.skip_next_chapter(asst)
    assert asst.skipped_output is True

def test_hud_themes_and_speed_control():
    """Verify Waveform HUD theme palette switching and global speech speed configuration."""
    from desktop.ui.hud import WaveformHud, THEME_PALETTES
    from desktop.audio.tts import set_speech_speed, get_speech_speed

    hud = WaveformHud(theme="cyberpunk")
    assert hud.theme == "cyberpunk"

    # Switch across all supported themes
    for t in ("matrix", "sunset", "violet", "ice"):
        hud.set_theme(t)
        assert hud.theme == t
        assert t in THEME_PALETTES

    # Invalid theme should be ignored
    hud.set_theme("non_existent_theme")
    assert hud.theme == "ice"

    # Speech speed settings
    set_speech_speed(1.25)
    assert abs(get_speech_speed() - 1.25) < 0.001
    set_speech_speed(0.1)  # clamped to 0.5
    assert abs(get_speech_speed() - 0.5) < 0.001
    set_speech_speed(3.0)  # clamped to 2.5
    assert abs(get_speech_speed() - 2.5) < 0.001
    set_speech_speed(1.0)  # reset to default
    assert abs(get_speech_speed() - 1.0) < 0.001

def test_tray_header_text_states(monkeypatch):
    """Verify dynamic tray header text updates across muted, speaking, paused, and active states."""
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem

    class DummyApp:
        def __init__(self):
            self.muted = False
            self.current_speech_item = None

    app = DummyApp()

    # 1. Active & Listening
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    hdr = app_module.AntiTrayApp._get_tray_header_text(app)
    assert "Active & Listening" in hdr
    assert "🟢" in hdr

    # 2. Speaking with chat tag
    app.current_speech_item = SpeechQueueItem("Hello")
    app.current_speech_item.chat_tag = "Security Audit"
    monkeypatch.setattr(app_module, "is_speaking", lambda: True)
    hdr_spk = app_module.AntiTrayApp._get_tray_header_text(app)
    assert "Speaking [Security Audit]" in hdr_spk
    assert "🔊" in hdr_spk

    # 3. Paused
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)
    monkeypatch.setattr(app_module, "is_paused", lambda: True)
    hdr_pause = app_module.AntiTrayApp._get_tray_header_text(app)
    assert "Speech Paused" in hdr_pause
    assert "⏸️" in hdr_pause

    # 4. Muted takes priority over other states
    app.muted = True
    hdr_muted = app_module.AntiTrayApp._get_tray_header_text(app)
    assert "Muted" in hdr_muted
    assert "🔴" in hdr_muted

def test_voice_profiles_and_switching():
    """Verify curated voice profiles and dynamic voice switching in tts module."""
    from desktop.audio.tts import VOICE_PROFILES, set_default_voice, get_default_voice

    assert "af_heart" in VOICE_PROFILES.values()
    assert "am_adam" in VOICE_PROFILES.values()
    assert "bf_emma" in VOICE_PROFILES.values()
    assert "bm_george" in VOICE_PROFILES.values()

    set_default_voice("am_adam")
    assert get_default_voice() == "am_adam"

    set_default_voice("heart")
    assert get_default_voice() == "af_heart"


def test_waveform_hud_cd_player_transport_controls():
    """Verify CD-player transport controls hit-testing, individual button callbacks, and expansion states."""
    from desktop.ui.hud import WaveformHud

    hud = WaveformHud(position="bottom_right")
    assert hud.height == 38
    assert hud.width == 480

    # 1. Verify expansion logic
    hud.state = "idle"
    hud.is_hovered = False
    hud._check_expansion()
    assert hud.height == 38

    hud.state = "speaking"
    hud._check_expansion()
    assert hud.height == 84

    hud.state = "paused"
    hud._check_expansion()
    assert hud.height == 84

    hud.state = "listening"
    hud.is_hovered = True
    hud._check_expansion()
    assert hud.height == 84

    hud.is_hovered = False
    hud._check_expansion()
    assert hud.height == 38

    # 2. Test button hit testing when expanded (height = 84, width = 480)
    hud.height = 84
    assert hud._hit_test_button(45, 62) == "prev"
    assert hud._hit_test_button(98, 62) == "rewind"
    assert hud._hit_test_button(150, 62) == "play_pause"
    assert hud._hit_test_button(203, 62) == "forward"
    assert hud._hit_test_button(256, 62) == "next"
    assert hud._hit_test_button(310, 62) == "skip"
    # Row 1 or outside bounds returns None
    assert hud._hit_test_button(50, 20) is None
    assert hud._hit_test_button(45, 40) is None

    # In compact mode (height = 38), hit testing always returns None
    hud.height = 38
    assert hud._hit_test_button(39, 62) is None

    # 3. Test transport button callbacks
    hud.height = 84
    events = []
    hud.on_prev_chapter = lambda: events.append("prev")
    hud.on_rewind_5 = lambda: events.append("rewind")
    hud.on_play_pause = lambda: events.append("play_pause")
    hud.on_forward_5 = lambda: events.append("forward")
    hud.on_next_chapter = lambda: events.append("next")
    hud.on_skip_output = lambda: events.append("skip")
    hud.on_click = lambda: events.append("general_click")

    class DummyEvent:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    # Click each of the 6 buttons
    hud._on_canvas_click(DummyEvent(45, 62))
    hud._on_canvas_click(DummyEvent(98, 62))
    hud._on_canvas_click(DummyEvent(150, 62))
    hud._on_canvas_click(DummyEvent(203, 62))
    hud._on_canvas_click(DummyEvent(256, 62))
    hud._on_canvas_click(DummyEvent(310, 62))
    assert events == ["prev", "rewind", "play_pause", "forward", "next", "skip"]

    # Click outside buttons (row 1 LCD screen) triggers general on_click
    events.clear()
    hud._on_canvas_click(DummyEvent(50, 20))
    assert events == ["general_click"]

    # 4. Test hover hint tracking
    hud._on_mouse_move(DummyEvent(45, 62))
    assert hud.hovered_button == "prev"
    assert hud._hover_hint == "⏮  REPEAT / PREV CHAPTER"

    hud._on_mouse_move(DummyEvent(98, 62))
    assert hud.hovered_button == "rewind"
    assert hud._hover_hint == "⏪  REWIND 5 SECONDS"

    hud._on_mouse_move(DummyEvent(150, 62))
    assert hud.hovered_button == "play_pause"

    hud._on_mouse_move(DummyEvent(310, 62))
    assert hud.hovered_button == "skip"
    assert hud._hover_hint == "⏹  SKIP CURRENT OUTPUT"

    hud._on_mouse_move(DummyEvent(50, 20))
    assert hud.hovered_button is None
    assert hud._hover_hint is None


def test_tray_menu_settings_submenu(monkeypatch):
    """Verify tray menu structure has a dedicated Settings submenu with all expected controls."""
    import desktop.app as app_module

    class DummyTrayApp:
        def __init__(self):
            self.auto_submit = True
            self.auto_read = True
            self.muted = False
            self.speech_speed = 1.0
            self.hud_enabled = True
            self.remote_poll_enabled = False
            self.speech_queue = []
            self.output_history = []
            self.last_spoken_summary = ""
            self.hud = type("DummyHud", (), {"theme": "cyberpunk", "position": "bottom_right"})()
            self.current_speech_item = None
            self.running = True

        def _get_tray_header_text(self, item=None):
            return "🟢  AudioMind: Active & Listening"
        def show_status_toast(self, icon=None, item=None): pass
        def toggle_auto_submit(self, icon=None, item=None): pass
        def toggle_auto_read(self, icon=None, item=None): pass
        def toggle_speech_pause(self, icon=None, item=None): pass
        def forward_speech_5(self, icon=None, item=None): pass
        def rewind_speech_5(self, icon=None, item=None): pass
        def skip_next_chapter(self, icon=None, item=None): pass
        def skip_current_output(self, icon=None, item=None): pass
        def repeat_curr_chapter(self, icon=None, item=None): pass
        def repeat_chapter(self, icon=None, item=None): pass
        def repeat_current_output(self, icon=None, item=None): pass
        def go_back_output(self, icon=None, item=None): pass
        def interrupt_speech(self, icon=None, item=None): pass
        def replay_last_response(self, icon=None, item=None): pass
        def read_highlighted_text(self, icon=None, item=None): pass
        def set_voice_model(self, v_id, v_name): pass
        def set_hud_theme(self, theme): pass
        def set_speech_speed(self, speed): pass
        def toggle_mute(self, icon=None, item=None): pass
        def toggle_hud(self, icon=None, item=None): pass
        def toggle_hud_dock(self, icon=None, item=None): pass
        def toggle_remote_listener(self, icon=None, item=None): pass
        def test_greeting(self, icon=None, item=None): pass
        def open_firewall_audit(self, icon=None, item=None): pass
        def exit_app(self, icon=None, item=None): pass

    app = DummyTrayApp()
    app_module.AntiTrayApp._setup_tray(app)

    assert app.tray_icon is not None
    root_menu = app.tray_icon.menu

    import pystray

    # Verify root items
    def get_text(it):
        return it.text(it) if callable(it.text) else str(it.text)

    root_texts = [get_text(item) for item in root_menu.items if item != pystray.Menu.SEPARATOR]
    assert any("Settings" in t for t in root_texts), f"Settings submenu not found in root menu: {root_texts}"
    assert any("Voice Selection" in t for t in root_texts)
    assert any("Exit AudioMind" in t for t in root_texts)

    # Find the Settings item
    settings_item = next(item for item in root_menu.items if item != pystray.Menu.SEPARATOR and "Settings" in get_text(item))
    assert settings_item.submenu is not None

    # Inspect items inside Settings submenu
    settings_texts = [get_text(sub) for sub in settings_item.submenu.items if sub != pystray.Menu.SEPARATOR]
    assert any("HUD Color Theme" in t for t in settings_texts)
    assert any("Speech Speed" in t for t in settings_texts)
    assert any("Mute Microphone" in t for t in settings_texts)
    assert any("Desktop Waveform HUD" in t for t in settings_texts)
    assert any("Dock Waveform" in t for t in settings_texts)
    assert any("Remote Assistant Dispatch Listener" in t for t in settings_texts)
    assert any("Test Voice Greeting" in t for t in settings_texts)
    assert any("Open Firewall State" in t for t in settings_texts)


def test_match_playback_intent_previous_output():
    """Verify voice intent matcher recognizes PREVIOUS_OUTPUT phrases when active and gates when inactive."""
    from desktop.app import match_playback_intent

    prev_phrases = [
        "previous output",
        "go back output",
        "go back an output",
        "go back one output",
        "go back 1 output",
        "previous response",
        "go back a response",
        "go back one response",
        "read previous output",
        "replay previous output",
        "read previous response",
    ]

    for p in prev_phrases:
        assert match_playback_intent(p, speech_active=True) == "PREVIOUS_OUTPUT", f"Phrase '{p}' did not match PREVIOUS_OUTPUT while active"
        assert match_playback_intent(p, speech_active=False) is None, f"Phrase '{p}' should not match when inactive"


def test_match_playback_intent_repeat_output_and_current_chapter():
    """Verify voice intent matcher recognizes REPEAT_OUTPUT and REPEAT_CURRENT_CHAPTER phrases."""
    from desktop.app import match_playback_intent

    repeat_output_phrases = [
        "repeat output",
        "repeat current output",
        "repeat last output",
        "replay output",
        "replay current output",
        "replay last output",
        "re-read output",
        "re-read current output",
        "re-read last output",
        "read output again",
        "read last output again",
        "repeat response",
        "repeat current response",
        "repeat last response",
        "play last output again",
    ]
    for p in repeat_output_phrases:
        assert match_playback_intent(p, speech_active=True) == "REPEAT_OUTPUT", f"Phrase '{p}' did not match REPEAT_OUTPUT"
        assert match_playback_intent(p, speech_active=False) is None

    repeat_ch_phrases = [
        "repeat current chapter",
        "replay current chapter",
        "restart current chapter",
        "repeat this chapter",
        "replay this chapter",
        "restart this chapter",
    ]
    for p in repeat_ch_phrases:
        assert match_playback_intent(p, speech_active=True) == "REPEAT_CURRENT_CHAPTER", f"Phrase '{p}' did not match REPEAT_CURRENT_CHAPTER while active"
        assert match_playback_intent(p, speech_active=False) is None


def test_paused_speech_auto_advances_on_new_response(monkeypatch):
    """Verify that when a new assistant response arrives while speech is paused, AudioMind stops paused audio to auto-advance."""
    import collections
    import threading
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem

    class DummyApp:
        def __init__(self):
            self.last_spoken_summary = ""
            self.auto_read = True
            self.output_history = []
            self.history_cursor = -1
            self.speech_queue = collections.deque()
            self._speak_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self.hud_enabled = True
            self.hud = type("DummyHud", (), {"set_status": lambda *a, **k: None})()
            self.current_speech_item = None

    app = DummyApp()
    stopped_calls = []
    monkeypatch.setattr(app_module, "is_paused", lambda: True)
    monkeypatch.setattr(app_module, "stop_speech", lambda: stopped_calls.append(True))
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)

    app_module.AntiTrayApp._on_assistant_response(app, "First response after user paused prior audio", filepath="file1.jsonl", step_index=1)

    assert len(stopped_calls) == 1, "stop_speech() should be called when new response arrives while paused"
    assert len(app.speech_queue) == 1
    assert app.speech_queue[0].text == "First response after user paused prior audio"
    assert len(app.output_history) == 1
    assert app.history_cursor == 0


def test_output_history_multi_step_back_navigation(monkeypatch):
    """Verify multi-step back navigation (1, 2, 3+ outputs) through output_history ring buffer."""
    import collections
    import threading
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem

    class DummyApp:
        def __init__(self):
            self.last_spoken_summary = ""
            self.auto_read = True
            self.output_history = []
            self.history_cursor = -1
            self.speech_queue = collections.deque()
            self._speak_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self.hud_enabled = True
            self.hud_statuses = []
            self.hud = type("DummyHud", (), {
                "set_status": lambda s, st, state="": s.hud_statuses.append((st, state)),
                "show": lambda s, state="", status="": s.hud_statuses.append((status, state)),
                "hud_statuses": []
            })()
            self.current_speech_item = None

    app = DummyApp()
    stopped = []
    chimes = []
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)
    monkeypatch.setattr(app_module, "stop_speech", lambda: stopped.append(True))
    monkeypatch.setattr(app_module, "play_chime", lambda rising=False: chimes.append(rising))
    monkeypatch.setattr(SpeechQueueItem, "_extract_chat_tag", lambda self, fp: os.path.basename(os.path.dirname(fp)) if fp else "")

    # Feed 4 distinct responses
    for i in range(1, 5):
        app_module.AntiTrayApp._on_assistant_response(
            app, f"Response {i}", filepath=f"C:\\chat_{i}\\log.jsonl", step_index=i
        )

    assert len(app.output_history) == 4
    assert app.history_cursor == 3
    # Clear speech queue so we can observe go_back_output actions
    app.speech_queue.clear()

    # Step back 1 time -> should queue Response 3
    app_module.AntiTrayApp.go_back_output(app)
    assert app.history_cursor == 2
    assert len(app.speech_queue) == 1
    assert app.speech_queue[0].text == "Response 3"
    assert app.speech_queue[0].chat_tag == "chat_3"

    # Step back 2 times -> should queue Response 2
    app_module.AntiTrayApp.go_back_output(app)
    assert app.history_cursor == 1
    assert len(app.speech_queue) == 2
    assert app.speech_queue[0].text == "Response 2"
    assert app.speech_queue[0].chat_tag == "chat_2"

    # Step back 3 times -> should queue Response 1
    app_module.AntiTrayApp.go_back_output(app)
    assert app.history_cursor == 0
    assert len(app.speech_queue) == 3
    assert app.speech_queue[0].text == "Response 1"
    assert app.speech_queue[0].chat_tag == "chat_1"

    # Step back again past oldest output -> clamps at 0 without error
    app_module.AntiTrayApp.go_back_output(app)
    assert app.history_cursor == 0
    assert app.speech_queue[0].text == "Response 1"

    # Verify ring buffer maximum capacity of 20
    for i in range(10, 35):
        app_module.AntiTrayApp._on_assistant_response(
            app, f"Response {i}", filepath="chat\\log.jsonl", step_index=i
        )
    assert len(app.output_history) == 20


def test_forward_and_rewind_player_playback():
    """Verify SpeechPlayer.fast_forward advances current_idx by exact sample count and clamps safely."""
    from desktop.audio.player import SpeechPlayer
    import numpy as np

    player = SpeechPlayer(samplerate=48000)
    # 10 seconds of audio = 480,000 samples
    dummy_audio = np.zeros((480000, 2), dtype=np.float32)
    player.play_pcm(dummy_audio)

    assert player.current_idx == 0
    assert player.position_seconds == 0.0
    assert player.duration_seconds == 10.0

    # Forward 5 seconds -> advances to 240,000 samples (5.0s)
    pos = player.fast_forward(5.0)
    assert pos == 5.0
    assert player.current_idx == 240000

    # Rewind 2 seconds -> rewinds to 144,000 samples (3.0s)
    pos = player.rewind(2.0)
    assert pos == 3.0
    assert player.current_idx == 144000

    # Forward 5 seconds again -> 384,000 samples (8.0s)
    pos = player.fast_forward(5.0)
    assert pos == 8.0
    assert player.current_idx == 384000

    # Forward 5 seconds past end -> clamps at duration (480,000 samples, 10.0s)
    pos = player.fast_forward(5.0)
    assert pos == 10.0
    assert player.current_idx == 480000

    player.stop()


def test_hud_flash_action_precedence_over_hover():
    """Verify that flash_action toast supersedes hover hints so clicking gives immediate visual confirmation."""
    from desktop.ui.hud import WaveformHud
    import time

    hud = WaveformHud()
    hud._hover_hint = "⏩  FORWARD 5 SECONDS"
    hud.status_text = "[Test Chat] • Speaking"

    # Before flashing, hover hint is displayed
    with hud._lock:
        now = time.time()
        toast_active = bool(hud._action_toast and now < hud._action_toast_until)
    assert not toast_active

    # Trigger action toast
    hud.flash_action("⏩  Forward +5s  (0:05 / 0:10)", duration_sec=1.5)

    with hud._lock:
        now = time.time()
        toast_active = bool(hud._action_toast and now < hud._action_toast_until)
        assert toast_active
        assert hud._action_toast == "⏩  Forward +5s  (0:05 / 0:10)"


def test_forward_speech_5_app_method(monkeypatch):
    """Verify AntiTrayApp.forward_speech_5 triggers player skip, flashes toast, and updates HUD."""
    import desktop.app as app_module

    class DummyApp:
        def __init__(self):
            self.hud_enabled = True
            self.hud_collapsed = False
            self.speech_queue = []
            self.current_speech_item = type("Item", (), {"chat_tag": "TestChat"})()
            self._last_read_app = ""
            self.flashed_toast = None
            self.hud_status = None

            class MockHud:
                def __init__(self, outer):
                    self.outer = outer
                def flash_action(self, toast, duration_sec=1.4):
                    self.outer.flashed_toast = toast
                def set_status(self, text, state="speaking"):
                    self.outer.hud_status = (text, state)

            self.hud = MockHud(self)

        def _format_status_with_chat(self, text):
            return f"[{self.current_speech_item.chat_tag}] • {text}"

        def skip_current_output(self): pass

    app = DummyApp()

    # Mock player position and duration
    class MockPlayer:
        position_seconds = 2.0
        duration_seconds = 20.0
    monkeypatch.setattr(app_module, "get_speech_player", lambda: MockPlayer())
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)
    monkeypatch.setattr(app_module, "is_speaking", lambda: True)
    monkeypatch.setattr(app_module, "fast_forward_speech", lambda sec: 7.0)

    chimes_played = []
    monkeypatch.setattr(app_module, "play_seek_chime", lambda forward=True: chimes_played.append(forward))

    app_module.AntiTrayApp.forward_speech_5(app)

    assert chimes_played == [True]
    assert app.flashed_toast == "⏩  Forward +5s  (0:07 / 0:20)"
    assert app.hud_status[0] == "[TestChat] • Forward +5s (0:07)"


def test_highlighted_text_not_interrupted_by_assistant_response(monkeypatch):
    """Verify that an incoming assistant response does NOT interrupt or truncate active highlighted text reading."""
    import threading
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem

    stopped = []
    monkeypatch.setattr(app_module, "stop_speech", lambda: stopped.append(True))
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    monkeypatch.setattr(app_module, "get_chapter_info", lambda: (1, 1, "Selection"))

    class DummyApp:
        def __init__(self):
            self.auto_read = True
            self.speech_queue = []
            self.output_history = []
            self.history_cursor = -1
            self.current_speech_item = SpeechQueueItem("Highlighted clip", chat_tag="Chrome Selection")
            self._last_read_app = "Chrome"
            self.is_reading_highlight = True
            self.hud_enabled = True
            self.hud_collapsed = False
            self.hud_status = None
            self._speak_lock = threading.Lock()

            class MockHud:
                def __init__(self, outer):
                    self.outer = outer
                def set_status(self, text, state="speaking"):
                    self.outer.hud_status = (text, state)

            self.hud = MockHud(self)

    app = DummyApp()

    # When an assistant response arrives while is_reading_highlight is True and speech is active
    app_module.AntiTrayApp._on_assistant_response(app, "Assistant reply content", filepath=r"C:\test\log.jsonl", step_index=2)

    # 1. Active speech MUST NOT be stopped
    assert len(stopped) == 0, "stop_speech() was unexpectedly called while reading highlighted text!"

    # 2. Assistant response MUST be queued behind the highlighted text
    assert len(app.speech_queue) == 1
    assert app.speech_queue[0].text == "Assistant reply content"

    # 3. HUD status reflects queued item without preempting highlighted text
    assert "• Q:1" in app.hud_status[0]


def test_skip_next_chapter_on_final_chapter_does_not_abort_playback(monkeypatch):
    """Verify that skip_next_chapter on the final chapter preserves audio and does not abruptly terminate playback."""
    import desktop.app as app_module
    import numpy as np
    from desktop.audio.player import SpeechPlayer

    # 1. Test underlying SpeechPlayer: 3 chapters, on chapter 3 (index 2)
    player = SpeechPlayer(samplerate=48000)
    sr = 48000
    pcm = np.zeros((30 * sr, 2), dtype=np.float32)
    player.play_pcm(pcm, chapter_markers=[0, 10 * sr, 20 * sr], chapter_titles=["Ch 1", "Ch 2", "Ch 3"])
    player.current_idx = 21 * sr  # playing in Chapter 3
    player._is_playing = True
    player._is_paused = False

    assert player.current_chapter_index == 2
    assert player.total_chapters == 3

    # Skipping on final chapter should NOT set current_idx = len(audio_data) (which kills audio)
    player.skip_to_next_chapter()
    assert player.is_active is True
    assert player.current_idx < len(player.audio_data)
    player.stop()

    # 2. Test AntiTrayApp UI coordination:
    class DummyApp:
        def __init__(self):
            self.hud_enabled = True
            self.hud_collapsed = False
            self.speech_queue = []
            self.current_speech_item = type("Item", (), {"chat_tag": "TestChat"})()
            self._last_read_app = ""
            self.flashed_toast = None
            self.skipped_output = False

            class MockHud:
                def __init__(self, outer):
                    self.outer = outer
                def flash_action(self, toast, duration_sec=1.4):
                    self.outer.flashed_toast = toast
                def set_status(self, text, state="speaking"): pass

            self.hud = MockHud(self)

        def skip_current_output(self, icon=None, item=None):
            self.skipped_output = True

    app = DummyApp()
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)
    monkeypatch.setattr(app_module, "get_chapter_info", lambda: (3, 3, "Final Section"))

    # When no outputs queued: does not skip output, informs user on HUD
    app_module.AntiTrayApp.skip_next_chapter(app)
    assert app.skipped_output is False
    assert app.flashed_toast == "ℹ️  Final Chapter (3/3)"

    # When outputs ARE queued: advances to next output
    app.speech_queue.append("queued_item")
    app_module.AntiTrayApp.skip_next_chapter(app)
    assert app.skipped_output is True


def test_enhanced_extract_chapters_bullet_bold_and_horizontal_rules():
    """Verify that extract_chapters_from_text segments bold bullet lists, horizontal rules, and numbered lists."""
    from desktop.audio.tts import extract_chapters_from_text

    # 1. Bold bullet points (* **Topic**: or - **Topic**:)
    text_bullets = (
        "* **Architecture Overview**: Here is how the system is laid out.\n\n"
        "* **Transport Engine**: Detailed explanation of the audio pipeline.\n\n"
        "* **Verification**: Automated test results and validation."
    )
    chs_b = extract_chapters_from_text(text_bullets)
    assert len(chs_b) == 3
    assert [c[0] for c in chs_b] == ["Architecture Overview", "Transport Engine", "Verification"]

    # 2. Horizontal rule dividers (---)
    text_hr = (
        "This is the opening summary section with important context.\n\n"
        "---\n\n"
        "This is the second section after the horizontal rule with deep dive details."
    )
    chs_hr = extract_chapters_from_text(text_hr)
    assert len(chs_hr) >= 2

    # 3. Numbered lists with titles
    text_num = (
        "1. **Initial Assessment**: Evaluating system state.\n\n"
        "2. **Implementation**: Applying code mutations.\n\n"
        "3. **Verification**: Running test gates."
    )
    chs_num = extract_chapters_from_text(text_num)
    assert len(chs_num) == 3
    assert [c[0] for c in chs_num] == ["Initial Assessment", "Implementation", "Verification"]


def test_capture_highlighted_text_preserves_raw_markdown_structure(monkeypatch):
    """Verify capture_highlighted_text returns raw text so chapter parsing can segment headings."""
    from desktop.audio.read_aloud import capture_highlighted_text
    from desktop.audio.tts import extract_chapters_from_text
    import pyperclip

    sample_md = (
        "# First Section\nOverview of the captured documentation.\n\n"
        "# Second Section\nDetailed code snippets and parameters."
    )
    monkeypatch.setattr(pyperclip, "paste", lambda: sample_md)
    monkeypatch.setattr(pyperclip, "copy", lambda text: None)

    res = capture_highlighted_text(target_hwnd=None)
    assert res == sample_md

    # When passed to chapter extraction, 2 distinct chapters are extracted
    chapters = extract_chapters_from_text(res)
    assert len(chapters) == 2
    assert chapters[0][0] == "First Section"
    assert chapters[1][0] == "Second Section"


def test_truncate_for_audio_summary_preserves_full_content_and_chapters():
    """Verify that 1400-3500 word responses are NOT truncated to 100-word snippets and preserve full chapter structure."""
    from desktop.audio.read_aloud import truncate_for_audio_summary
    from desktop.audio.tts import extract_chapters_from_text

    # Construct a 1,600-word multi-chapter response (similar to a full technical summary)
    sec1 = "## 1. Executive Summary\n" + ("This is an important introductory finding about the system architecture. " * 40)
    sec2 = "\n\n## 2. Deep Dive Analysis\n" + ("Here we examine the empirical benchmark metrics and latency distributions across runs. " * 55)
    sec3 = "\n\n## 3. Final Recommendations\n" + ("We recommend deploying the updated streaming pipeline and strict wake-word confirmation gate. " * 40)
    full_response = sec1 + sec2 + sec3

    word_count = len(full_response.split())
    assert word_count > 1400

    # Must preserve 100% of a 1,600-word summary without dropping sentences or headings
    result = truncate_for_audio_summary(full_response)
    assert result == full_response
    assert len(result.split()) == word_count

    chapters = extract_chapters_from_text(result)
    assert len(chapters) == 3
    assert "Executive Summary" in chapters[0][0]
    assert "Deep Dive Analysis" in chapters[1][0]
    assert "Final Recommendations" in chapters[2][0]


def test_streaming_subchunk_synthesis_prevents_chapter_starvation(monkeypatch):
    """
    Verify that when Chapter 1 is short and Chapter 2 is very long (>200 words),
    speak_async splits chapters into ~45-word streaming sub-chunks and appends them
    with new_chapter=False for intra-chapter sub-chunks so Chapter 1 never starves waiting for Chapter 2.
    """
    import asyncio
    import numpy as np
    from desktop.audio.player import SpeechPlayer
    import desktop.audio.tts as tts_module

    ch1 = "## Short Intro\nWelcome to the brief overview."
    ch2_sentences = ["Sentence number {} explains the detailed technical benchmark results clearly.".format(i) for i in range(1, 25)]
    ch2 = "## Long Analysis\n" + " ".join(ch2_sentences)
    full_text = f"{ch1}\n\n{ch2}"

    sub_chunks_ch2 = tts_module.split_text_for_streaming(ch2, max_words_per_chunk=45)
    assert len(sub_chunks_ch2) >= 4, "Long chapter must be split into multiple streaming sub-chunks"

    player = SpeechPlayer(samplerate=48000)
    append_calls = []
    orig_append = player.append_pcm

    def spy_append(pcm_chunk, chapter_title="", pause_sec=0.25, new_chapter=True):
        append_calls.append((chapter_title, pause_sec, new_chapter, len(pcm_chunk)))
        return orig_append(pcm_chunk, chapter_title=chapter_title, pause_sec=pause_sec, new_chapter=new_chapter)

    monkeypatch.setattr(player, "append_pcm", spy_append)
    monkeypatch.setattr(player, "wait", lambda: None)

    class DummyKokoro:
        def get_voices(self):
            return ["af_heart"]

    monkeypatch.setattr(tts_module, "get_kokoro", lambda: DummyKokoro())
    monkeypatch.setattr(tts_module, "synth_kokoro_pcm", lambda t, voice=None, speed=1.0: np.ones((12000, 2), dtype=np.float32) * 0.2)
    monkeypatch.setattr(tts_module, "global_player", player)

    asyncio.run(tts_module.speak_async(full_text))

    # Exactly 2 chapters in total should be registered in player markers, despite multiple streaming sub-chunks!
    assert len(player.chapter_markers) == 2
    assert player.chapter_titles == ["Short Intro", "Long Analysis"]
    # First append of Chapter 2 must have new_chapter=True, subsequent sub-chunks of Chapter 2 must have new_chapter=False
    assert append_calls[0][2] is True
    assert any(c[2] is False for c in append_calls[1:])
    player.stop()


def test_wakeword_sensitivity_strict_defaults_and_menu():
    """Verify wakeword_threshold defaults to 0.85 with 2-frame patience and can be configured via set_wakeword_sensitivity."""
    import desktop.app as app_module

    class DummyApp:
        def __init__(self):
            self.wakeword_threshold = 0.85
            self.wakeword_patience = 2
            self.wakeword_min_rms = 0.008
            self.hud_enabled = False
            self.model = type("DummyModel", (), {"reset": lambda self: None})()

    app = DummyApp()
    app_module.AntiTrayApp.set_wakeword_sensitivity(app, 0.92, 2, "Ultra-Strict")
    assert app.wakeword_threshold == 0.92
    assert app.wakeword_patience == 2

    app_module.AntiTrayApp.set_wakeword_sensitivity(app, 0.85, 2, "Strict")
    assert app.wakeword_threshold == 0.85
    assert app.wakeword_patience == 2


def test_pause_hold_window_preserves_recent_pause_and_advances_after_expiry(monkeypatch):
    """
    Verify Pause Hold Awareness (default 2 minutes / 120s):
    1. If speech was paused < 120s ago when a new response arrives, it does NOT interrupt or call stop_speech();
       the new response is queued cleanly behind the paused audio.
    2. If speech is still paused when the 120s window expires, _check_pause_hold_expiry() automatically advances.
    3. If speech has already been paused >= 120s when a new response arrives, _on_assistant_response advances immediately.
    """
    import collections
    import threading
    import time as time_mod
    import desktop.app as app_module

    class DummyApp:
        def __init__(self):
            self.last_spoken_summary = ""
            self.auto_read = True
            self.output_history = []
            self.history_cursor = -1
            self.speech_queue = collections.deque()
            self._speak_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self.hud_enabled = True
            self.hud_collapsed = False
            self.hud_statuses = []
            self.hud = type("DummyHud", (), {
                "set_status": lambda s, st, state="": self.hud_statuses.append((st, state)),
                "show": lambda s, state="", status="": self.hud_statuses.append((status, state)),
            })()
            self.current_speech_item = None
            self.pause_hold_seconds = 120.0
            self.paused_at = None
            self._capturing_voice_command = False
            self.is_reading_highlight = False
            self.muted_sessions = {}
            self.known_sessions = {}

        def _format_status_with_chat(self, action: str, extra: str = "") -> str:
            return app_module.AntiTrayApp._format_status_with_chat(self, action, extra)

        def is_session_muted(self, **kwargs) -> bool:
            return app_module.AntiTrayApp.is_session_muted(self, **kwargs)

    app = DummyApp()
    stopped_calls = []
    monkeypatch.setattr(app_module, "is_paused", lambda: True)
    monkeypatch.setattr(app_module, "stop_speech", lambda: stopped_calls.append(True))
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)

    # Case 1: User paused only 15 seconds ago (< 120s default grace window)
    app.paused_at = time_mod.time() - 15.0
    app_module.AntiTrayApp._on_assistant_response(
        app, "Response arriving while recently paused", filepath=r"C:\Users\u\.gemini\antigravity\brain\uuid-1\transcript.jsonl", step_index=2
    )
    assert len(stopped_calls) == 0, "Should NOT stop paused speech when paused for only 15s (< 120s hold window)"
    assert len(app.speech_queue) == 1

    # Background timer check at 45s (< 120s) should still hold
    app.paused_at = time_mod.time() - 45.0
    assert app_module.AntiTrayApp._check_pause_hold_expiry(app) is False
    assert len(stopped_calls) == 0

    # Case 2: Background timer reaches 121s (>= 120s) while item is waiting in queue -> auto-advances!
    app.paused_at = time_mod.time() - 121.0
    assert app_module.AntiTrayApp._check_pause_hold_expiry(app) is True
    assert len(stopped_calls) == 1
    assert app.paused_at is None

    # Case 3: New response arrives when already paused for 130s (>= 120s) -> immediate advance
    app.paused_at = time_mod.time() - 130.0
    app_module.AntiTrayApp._on_assistant_response(
        app, "Response arriving after 130s pause", filepath=r"C:\Users\u\.gemini\antigravity\brain\uuid-1\transcript.jsonl", step_index=3
    )
    assert len(stopped_calls) == 2, "Should immediately stop paused speech when paused >= 120s"


def test_per_session_mute_durations_queue_purge_and_isolation(monkeypatch):
    """
    Verify Per-Session Muting (5m, 10m, 25m, Unmute):
    - Muting a noisy benchmark session suppresses future responses from that session.
    - Purges any already-queued responses from that session and skips current speech if that session is speaking.
    - Allows responses from OTHER unmuted sessions to play normally!
    - Automatically unmutes once the timer expires or when unmute_all_sessions is called.
    """
    import collections
    import threading
    import time as time_mod
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem, match_playback_intent

    # 1. Verify voice intents for 5, 10, 25 minute session mute & unmute
    assert match_playback_intent("mute this session", speech_active=True) == "MUTE_SESSION_10"
    assert match_playback_intent("mute session for 5 minutes", speech_active=True) == "MUTE_SESSION_5"
    assert match_playback_intent("mute this for five minutes", speech_active=False) == "MUTE_SESSION_5"
    assert match_playback_intent("mute session for 10 minutes", speech_active=True) == "MUTE_SESSION_10"
    assert match_playback_intent("mute session for 25 minutes", speech_active=True) == "MUTE_SESSION_25"
    assert match_playback_intent("mute for twenty-five minutes", speech_active=False) == "MUTE_SESSION_25"
    assert match_playback_intent("unmute session", speech_active=False) == "UNMUTE_SESSIONS"
    assert match_playback_intent("unmute all sessions", speech_active=True) == "UNMUTE_SESSIONS"

    monkeypatch.setattr(SpeechQueueItem, "_extract_chat_tag", lambda self, fp: "Benchmark Chat" if (fp and "bench-uuid" in fp) else ("Main Feature" if (fp and "main-uuid" in fp) else "General"))

    class DummyApp:
        def __init__(self):
            self.last_spoken_summary = ""
            self.auto_read = True
            self.output_history = []
            self.history_cursor = -1
            self.speech_queue = collections.deque()
            self._speak_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self.hud_enabled = False
            self.hud_collapsed = False
            self.current_speech_item = None
            self.pause_hold_seconds = 120.0
            self.paused_at = None
            self.muted_sessions = {}
            self.known_sessions = {}
            self.skipped_count = 0

        def _resolve_target_session(self, session_key=None, chat_tag=None):
            return app_module.AntiTrayApp._resolve_target_session(self, session_key=session_key, chat_tag=chat_tag)

        def is_session_muted(self, **kwargs):
            return app_module.AntiTrayApp.is_session_muted(self, **kwargs)

        def get_active_muted_sessions(self):
            return app_module.AntiTrayApp.get_active_muted_sessions(self)

        def skip_current_output(self):
            self.skipped_count += 1

    app = DummyApp()
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    monkeypatch.setattr(app_module, "is_speaking", lambda: True)
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)

    bench_fp = r"C:\Users\u\.gemini\antigravity\brain\bench-uuid-123\.system_generated\logs\transcript.jsonl"
    main_fp = r"C:\Users\u\.gemini\antigravity\brain\main-uuid-456\.system_generated\logs\transcript.jsonl"

    # Queue 2 benchmark outputs and 1 main feature output, with benchmark currently playing
    app_module.AntiTrayApp._on_assistant_response(app, "Benchmark iteration 1", filepath=bench_fp, step_index=1)
    app_module.AntiTrayApp._on_assistant_response(app, "Benchmark iteration 2", filepath=bench_fp, step_index=2)
    app_module.AntiTrayApp._on_assistant_response(app, "Important main session answer", filepath=main_fp, step_index=1)
    assert len(app.speech_queue) == 3

    app.current_speech_item = app.speech_queue.popleft()  # Benchmark iteration 1 is now playing

    # User mutes the active session (Benchmark Chat) for 10 minutes
    app_module.AntiTrayApp.mute_session(app, duration_minutes=10.0)

    # Must have skipped currently playing Benchmark iteration 1 AND purged Benchmark iteration 2 from the queue!
    assert app.skipped_count == 1
    assert len(app.speech_queue) == 1
    assert app.speech_queue[0].text == "Important main session answer"
    assert app.is_session_muted(filepath=bench_fp) is True
    assert app.is_session_muted(filepath=main_fp) is False

    # Subsequent benchmark iterations arrive -> completely ignored!
    app_module.AntiTrayApp._on_assistant_response(app, "Benchmark iteration 3", filepath=bench_fp, step_index=3)
    assert len(app.speech_queue) == 1

    # Another response from Main Feature session arrives -> queued normally!
    app_module.AntiTrayApp._on_assistant_response(app, "Second main session answer", filepath=main_fp, step_index=2)
    assert len(app.speech_queue) == 2

    # Simulate timer expiry -> session automatically unmutes
    app.muted_sessions["bench-uuid-123"]["until"] = time_mod.time() - 1.0
    assert app.is_session_muted(filepath=bench_fp) is False
    app_module.AntiTrayApp._on_assistant_response(app, "Benchmark final summary after mute expired", filepath=bench_fp, step_index=4)
    assert len(app.speech_queue) == 3


def test_extract_visible_blocks_preserves_verbatim_chat_tokens():
    """Verify visible block extraction keeps Ctrl+F verbatim tokens and splits around hidden blocks."""
    from desktop.audio.read_aloud import extract_visible_blocks_from_markdown

    md = (
        "## Overview\n"
        "**Anti** uses `split_text_for_streaming()` inside [tts.py](file:///h:/repo/desktop/audio/tts.py#L10-L20) "
        "for \\$100 savings.\n\n"
        "```python\nx = 1 + 2\n```\n\n"
        "Then visit https://example.com/docs or compute $x + y$ before continuing."
    )

    blocks = extract_visible_blocks_from_markdown(md)
    joined = "\n".join(blocks)

    assert "Anti" in joined
    assert "Ante" not in joined
    assert "split_text_for_streaming()" in joined
    assert "$100" in joined
    assert "tts.py" in joined
    assert "https://example.com/docs" not in joined
    assert "x = 1 + 2" not in joined
    assert "x + y" not in joined

    # Words across code blocks and URLs must stay in distinct blocks
    assert any("Anti uses split_text_for_streaming() inside tts.py for $100 savings." == b for b in blocks)
    assert any("Then visit" == b for b in blocks)
    assert any("or compute" == b for b in blocks)
    assert any("before continuing." == b for b in blocks)


def test_speech_player_sample_accurate_phrase_locator_and_seek_sync():
    """Verify SpeechPlayer tracks sample-accurate verbatim Ctrl+F phrases across chapters and seeks."""
    import numpy as np
    from desktop.audio.player import SpeechPlayer
    from desktop.audio.read_aloud import align_subchunks_to_visible_blocks

    sr = 48000
    player = SpeechPlayer(samplerate=sr)

    ch1_md = "## Setup\nFirst install the local audio dependencies and verify your microphone input."
    ch2_md = "## Execution\nNext launch the background daemon and watch incoming conversation turns."

    ch1_blocks = ["Setup", "First install the local audio dependencies and verify your microphone input."]
    ch2_blocks = ["Execution", "Next launch the background daemon and watch incoming conversation turns."]

    ch1_aligned = align_subchunks_to_visible_blocks(
        ["First install the local audio dependencies and verify your microphone input."],
        ch1_blocks,
    )
    ch2_aligned = align_subchunks_to_visible_blocks(
        ["Next launch the background daemon and watch incoming conversation turns."],
        ch2_blocks,
    )

    pcm1 = np.ones((5 * sr, 2), dtype=np.float32) * 0.2
    pcm2 = np.ones((5 * sr, 2), dtype=np.float32) * 0.2

    player.play_pcm(pcm1, chapter_markers=[0], chapter_titles=["Setup", "Execution"], stream_complete=False)
    player._is_playing = True
    player._is_paused = False
    player.register_segment_tokens(ch1_aligned[0], start_sample=0, end_sample=len(pcm1), chapter_title="Setup")

    player.append_pcm(pcm2, chapter_title="Execution", pause_sec=0.25, new_chapter=True)
    player.register_segment_tokens(ch2_aligned[0], chapter_title="Execution")
    player.set_stream_complete(True)

    # Start of Chapter 1: skips 1-word heading "Setup" and picks prose substring
    loc_start = player.get_locator_at_sample(sample_idx=0, target_words=6)
    assert loc_start is not None
    assert loc_start["chapter"] == 1
    assert loc_start["total_chapters"] == 2
    assert loc_start["phrase"] in ch1_blocks[1]
    assert 4 <= len(loc_start["phrase"].split()) <= 6

    # Middle of Chapter 1
    loc_mid = player.get_locator_at_sample(sample_idx=int(2.5 * sr), target_words=6)
    assert loc_mid is not None
    assert loc_mid["phrase"] in ch1_blocks[1]

    # Fast-forward into Chapter 2
    player.fast_forward(6.0)
    loc_ch2 = player.get_locator_at_sample(target_words=6)
    assert loc_ch2 is not None
    assert loc_ch2["chapter"] == 2
    assert loc_ch2["chapter_title"] == "Execution"
    assert loc_ch2["phrase"] in ch2_blocks[1]
    assert loc_ch2["progress_pct"] >= 50

    # Rewind 5.0s back into Chapter 1
    player.rewind(5.0)
    loc_rew = player.get_locator_at_sample(target_words=6)
    assert loc_rew is not None
    assert loc_rew["chapter"] == 1
    assert loc_rew["phrase"] in ch1_blocks[1]

    player.stop()


def test_hud_locate_button_hit_test_hover_progress_and_transport_non_regression():
    """Verify HUD Locate [⌖] button hit-testing, hover hints, progress clamping, and existing button safety."""
    from desktop.ui.hud import WaveformHud

    hud = WaveformHud(position="bottom_right")

    # Expanded mode (height = 84)
    hud.height = 84
    assert hud._hit_test_locate(430, 25) is True
    assert hud._hit_test_collapse(455, 25) is True
    assert hud._hit_test_locate(50, 20) is False
    assert hud._hit_test_collapse(50, 20) is False

    # Compact mode (height = 38)
    hud.height = 38
    assert hud._hit_test_locate(430, 18) is True
    assert hud._hit_test_collapse(455, 18) is True
    assert hud._hit_test_locate(50, 20) is False

    class DummyEvent:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    # Click Locate button
    hud.height = 84
    located = []
    hud.on_locate = lambda: located.append(True)
    assert hud._on_canvas_click(DummyEvent(430, 25)) == "break"
    assert located == [True]

    # Hover Locate button
    hud._on_mouse_move(DummyEvent(430, 25))
    assert hud.hovered_button == "locate"
    assert hud._hover_hint == "🎯  FIND PHRASE IN CHAT (Ctrl+Alt+F)"

    # Progress clamping
    hud.set_progress(1.5)
    assert hud.playback_progress == 1.0
    hud.set_progress(-0.2)
    assert hud.playback_progress == 0.0
    hud.set_progress(0.42)
    assert abs(hud.playback_progress - 0.42) < 1e-6


def test_locate_in_chat_copies_verbatim_phrase_and_voice_intent(monkeypatch):
    """Verify LOCATE_IN_CHAT voice intent, clipboard copy, HUD toast, and output_history fallback."""
    import desktop.app as app_module
    from desktop.app import SpeechQueueItem, match_playback_intent

    assert match_playback_intent("find in chat", True) == "LOCATE_IN_CHAT"
    assert match_playback_intent("where are you reading", True) == "LOCATE_IN_CHAT"
    assert match_playback_intent("find in chat", False) is None
    assert match_playback_intent("find the bug in chat.py", True) is None

    copied = []
    monkeypatch.setattr(app_module, "set_clipboard_text", lambda txt: copied.append(txt))
    monkeypatch.setattr(app_module, "play_seek_chime", lambda forward=True: None)

    class DummyHud:
        def __init__(self):
            self.toasts = []
            self.shown = []
        def flash_action(self, toast, duration_sec=1.4):
            self.toasts.append(toast)
        def show(self, state="idle", status="", subtitle=""):
            self.shown.append((state, status))

    class DummyApp:
        def __init__(self):
            self.hud_enabled = True
            self.hud_collapsed = False
            self.hud = DummyHud()
            self.current_speech_item = None
            self.output_history = [SpeechQueueItem("First turn text")]
            self.history_cursor = 0
            self.last_spoken_summary = ""
            self.speech_queue = []

        def _hide_hud_after_delay(self, delay=1.0):
            pass

    app = DummyApp()

    # 1. Active playback locator hit
    monkeypatch.setattr(app_module, "is_speech_active", lambda: True)
    monkeypatch.setattr(
        app_module,
        "get_current_locator_info",
        lambda target_words=6: {
            "phrase": "verify your microphone input",
            "active_word": "microphone",
            "chapter": 2,
            "total_chapters": 4,
            "chapter_title": "Setup",
            "progress_pct": 42,
            "position_seconds": 12.5,
        },
    )
    res_active = app_module.AntiTrayApp.locate_in_chat(app)
    assert res_active == "verify your microphone input"
    assert copied[-1] == "verify your microphone input"
    assert len(app.hud.toasts) == 1
    assert "Ch 2/4 42%" in app.hud.toasts[0]

    # 2. Fallback to output_history when playback just ended
    monkeypatch.setattr(app_module, "is_speech_active", lambda: False)
    app.output_history = [SpeechQueueItem("## Summary\nAll unit tests passed without any regression today.")]
    app.history_cursor = 0
    res_fb = app_module.AntiTrayApp.locate_in_chat(app)
    assert res_fb == "All unit tests passed without any"
    assert copied[-1] == "All unit tests passed without any"


def test_filter_verification_report_skips_verification_keeps_summary_and_closing():
    """Verify Verification Report headings/bold headers are skipped while summary and trailing questions are kept."""
    from desktop.audio.read_aloud import filter_verification_report_for_speech

    sample = (
        "### Summary of Changes\n"
        "- Updated [`desktop/app.py`](file:///repo/desktop/app.py) to add section filtering.\n"
        "- Updated [`desktop/audio/read_aloud.py`](file:///repo/desktop/audio/read_aloud.py) with Markdown parser.\n\n"
        "### Verification Results\n"
        "- `pytest desktop/tests/ tests/ -q`: **80 passed** in 4.1s.\n"
        "```bash\n"
        "$ pytest relay/test_relay.py -q\n"
        "7 passed in 0.9s\n"
        "```\n"
        "All changes are uncommitted in your working tree; would you like me to commit them now?"
    )
    filtered = filter_verification_report_for_speech(sample)
    assert "Summary of Changes" in filtered
    assert "desktop/app.py" in filtered
    assert "Verification Results" not in filtered
    assert "pytest" not in filtered
    assert "7 passed" not in filtered
    assert "would you like me to commit them now?" in filtered
    # Must be idempotent
    assert filter_verification_report_for_speech(filtered) == filtered

    variants = [
        "### Verification Report\n- All checks green.\n\nReady for your next command?",
        "### 3. `sdcs check` Final Verification Receipt\n- `sdcs verify --topology`: exit 0.\n\nLet me know if you want to push.",
        "### Observed Verification Results (Post-Final Edit)\n- 85/85 passing.\n\nShall I open a pull request?",
        "## Implementation\nAdded helper function.\n\n**Offline & Anti-Bias Verification (Ran After Final Edits):**\n- Fixture replay passed.\n\nNext step: try it live?",
        "## Implementation\nAdded helper function.\n\n5. **Independent Full-Suite and Gate Verification**:\n  - Desktop suite passed.\n  - Relay suite passed.\n\n## Next Steps\nTest voice playback.",
    ]
    for v in variants:
        out = filter_verification_report_for_speech(v)
        assert "All checks green" not in out
        assert "sdcs verify --topology" not in out
        assert "85/85 passing" not in out
        assert "Fixture replay passed" not in out
        assert "Desktop suite passed" not in out
        assert out != ""
        assert (
            "Ready for your next command?" in out
            or "Let me know if you want to push." in out
            or "Shall I open a pull request?" in out
            or "Next step: try it live?" in out
            or "Test voice playback." in out
        )


def test_filter_verification_report_preserves_closeout_sections_and_nested_closeout_bullets():
    """Verify standalone Close-Out sections AND nested Close-Out bullets inside Verification sections are preserved."""
    from desktop.audio.read_aloud import filter_verification_report_for_speech
    from desktop.audio.tts import extract_chapters_from_text

    # Case A: Separate Verification Results followed by SDCS Close-Out
    case_a = (
        "## Changes\n"
        "Refactored playback queue.\n\n"
        "## Verification Results\n"
        "- `pytest`: 85/85 passed\n"
        "- `sdcs verify --mocks`: exit 0\n\n"
        "## SDCS Close-Out\n"
        "- Pruned `state.md` under 300 tokens.\n"
        "- Logged session flight recorder."
    )
    out_a = filter_verification_report_for_speech(case_a)
    assert "Refactored playback queue." in out_a
    assert "Verification Results" not in out_a
    assert "85/85 passed" not in out_a
    assert "## SDCS Close-Out" in out_a
    assert "Pruned `state.md` under 300 tokens." in out_a
    assert "Logged session flight recorder." in out_a

    # Case B: Combined Verification & Close-Out with nested Close-Out bullet block
    case_b = (
        "## What Changed\n"
        "Added skip filter toggle.\n\n"
        "### Verification & Close-Out\n"
        "- `pytest desktop/tests/ -q`: 75 passed\n"
        "- `sdcs check`: 0 errors\n"
        "- **SDCS Close-Out Gates:**\n"
        "  - Updated `roadmap.md` with M-006.\n"
        "  - Synced `app_map.md` and `state.md`.\n\n"
        "Everything is live. Would you like to test it?"
    )
    out_b = filter_verification_report_for_speech(case_b)
    assert "Added skip filter toggle." in out_b
    assert "75 passed" not in out_b
    assert "0 errors" not in out_b
    assert "SDCS Close-Out Gates:" in out_b
    assert "Updated `roadmap.md` with M-006." in out_b
    assert "Synced `app_map.md` and `state.md`." in out_b
    assert "Would you like to test it?" in out_b

    chapters = extract_chapters_from_text(out_b)
    titles = [c[0] for c in chapters]
    assert any("Close-Out Gates" in t for t in titles), f"Expected Close-Out chapter in {titles}"

    # Case C: Inline body on Close-Out bullet should not be lost in chapter extraction
    case_c = (
        "## Overview\nBody paragraph here.\n\n"
        "## Verification Results\n"
        "- `pytest`: 10 passed\n"
        "- **SDCS Close-Out:** All 6 pillars synced cleanly.\n"
    )
    out_c = filter_verification_report_for_speech(case_c)
    assert "All 6 pillars synced cleanly." in out_c
    ch_c = extract_chapters_from_text(out_c)
    assert any("All 6 pillars synced cleanly." in body for _, body in ch_c)


def test_filter_verification_report_never_skips_narrative_or_plan_headings_or_fenced_blocks():
    """Verify narrative 'Verified' headings, design plans, code blocks, orphaned truncated fences, and full-verdict fallback."""
    from desktop.audio.read_aloud import filter_verification_report_for_speech

    narrative = (
        "### What Was Built & Verified\n"
        "We built the complete audio pipeline.\n\n"
        "### 2. Zero Leaks Verified Across All Public Surfaces\n"
        "Scanned every tracked file cleanly.\n\n"
        "### The Verification Mirage & The Fatal Self-Revert\n"
        "Root cause narrative stays intact.\n\n"
        "#### Component 3: Topology & Verification (Gate T)\n"
        "Architecture explanation stays intact.\n\n"
        "### Verification Plan (M-006)\n"
        "Future test plan stays intact.\n\n"
        "#### **Tweet 3 (The Links + Verification Receipt)**\n"
        "Social draft stays intact.\n\n"
        "1. **Account Verification Status is 100% Clear:**\n"
        "User account note stays intact.\n\n"
        "```markdown\n"
        "### Verification Results\n"
        "- Example inside fenced code block must remain intact.\n"
        "```"
    )
    out_nar = filter_verification_report_for_speech(narrative)
    assert out_nar.strip() == narrative.strip()

    # Orphaned closing fence from <truncated N bytes> must NOT mask subsequent Verification Summary
    truncated = (
        "### Summary\n"
        "Implemented feature X cleanly.\n\n"
        "```python\n"
        "<truncated 992 bytes>\n"
        "     ```\n\n"
        "### Verification Summary\n"
        "- `pytest`: 85/85 passed\n\n"
        "Let me know if you want to run anything else."
    )
    out_trunc = filter_verification_report_for_speech(truncated)
    assert "Implemented feature X cleanly." in out_trunc
    assert "85/85 passed" not in out_trunc
    assert "Let me know if you want to run anything else." in out_trunc

    # Standalone 100%-verification response falls back safely instead of returning empty string
    only_verif = "### Verification\n- 85/85 passed"
    assert filter_verification_report_for_speech(only_verif) == only_verif


def test_filter_verification_report_preserves_verbatim_locate_in_chat_alignment():
    """Verify every visible token after filtering + Close-Out promotion remains verbatim for Locate-in-Chat."""
    from desktop.audio.read_aloud import (
        align_subchunks_to_visible_blocks,
        extract_visible_blocks_from_markdown,
        filter_verification_report_for_speech,
    )

    raw_md = (
        "## Summary of Changes\n"
        "Added deterministic section filtering so verification logs do not interrupt spoken summaries.\n\n"
        "## Verification & Close-Out\n"
        "- `pytest desktop/tests/ -q`: 80 passed\n"
        "- **SDCS Close-Out:**\n"
        "  - Updated roadmap and active blackboard state cleanly.\n\n"
        "Would you like me to commit these verified updates now?"
    )
    filtered = filter_verification_report_for_speech(raw_md)

    orig_blocks = extract_visible_blocks_from_markdown(raw_md)
    filt_blocks = extract_visible_blocks_from_markdown(filtered)
    orig_joined = " ".join(orig_blocks)

    aligned = align_subchunks_to_visible_blocks(
        [
            "Added deterministic section filtering so verification logs do not interrupt spoken summaries.",
            "Updated roadmap and active blackboard state cleanly.",
            "Would you like me to commit these verified updates now?",
        ],
        filt_blocks,
    )
    for chunk_tokens in aligned:
        assert len(chunk_tokens) > 0
        phrase = " ".join(w for _, w in chunk_tokens)
        # Check sliding 5-word windows appear verbatim in original DOM visible text
        words = phrase.split()
        if len(words) >= 5:
            snippet = " ".join(words[:5])
            assert snippet in orig_joined, f"Located snippet '{snippet}' missing from original DOM text"


def test_tray_app_skip_verification_toggle_and_remote_ack_unfiltered(monkeypatch):
    """Verify AntiTrayApp filters speech by default, sends unfiltered remote ACK, and respects Settings toggle."""
    import collections
    import threading
    import pystray
    import desktop.app as app_module

    class DummyHud:
        def __init__(self):
            self.theme = "cyberpunk"
            self.position = "bottom_right"
            self.toasts = []
            self.shown = []
        def flash_action(self, toast, duration_sec=1.6):
            self.toasts.append(toast)
        def show(self, state="listening", status="", subtitle=""):
            self.shown.append((state, status))
        def set_status(self, st, state=""):
            self.shown.append((state, st))
        def hide(self):
            pass

    class DummyToggleApp:
        def __init__(self):
            self.auto_submit = True
            self.auto_read = True
            self.skip_verification_report = True
            self.muted = False
            self.speech_speed = 1.0
            self.hud_enabled = True
            self.hud_collapsed = False
            self.remote_poll_enabled = False
            self.speech_queue = collections.deque()
            self.output_history = []
            self.history_cursor = -1
            self.last_raw_response = ""
            self.last_spoken_summary = ""
            self.current_speech_item = None
            self.running = True
            self.hud = DummyHud()
            self._speak_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self.pending_remote_dispatch = {
                "id": "disp-1",
                "submitted": True,
                "matched_transcript": None,
                "matched_step_index": 0,
            }
            self.acks = []
            self.known_sessions = {}

        def _get_tray_header_text(self, item=None):
            return "🟢 AudioMind"
        def send_remote_ack(self, dispatch_id, status="EXECUTED", summary=None):
            self.acks.append((dispatch_id, status, summary))
        def show_status_toast(self, *a, **k): pass
        def toggle_auto_submit(self, *a, **k): pass
        def toggle_auto_read(self, *a, **k): pass
        def toggle_speech_pause(self, *a, **k): pass
        def forward_speech_5(self, *a, **k): pass
        def rewind_speech_5(self, *a, **k): pass
        def skip_next_chapter(self, *a, **k): pass
        def skip_current_output(self, *a, **k): pass
        def repeat_curr_chapter(self, *a, **k): pass
        def repeat_chapter(self, *a, **k): pass
        def repeat_current_output(self, *a, **k): pass
        def go_back_output(self, *a, **k): pass
        def interrupt_speech(self, *a, **k): pass
        def replay_last_response(self, *a, **k): pass
        def read_highlighted_text(self, *a, **k): pass
        def set_voice_model(self, *a, **k): pass
        def set_hud_theme(self, *a, **k): pass
        def set_speech_speed(self, *a, **k): pass
        def toggle_mute(self, *a, **k): pass
        def toggle_hud(self, *a, **k): pass
        def toggle_hud_dock(self, *a, **k): pass
        def toggle_remote_listener(self, *a, **k): pass
        def test_greeting(self, *a, **k): pass
        def open_firewall_audit(self, *a, **k): pass
        def exit_app(self, *a, **k): pass
        def _hide_hud_after_delay(self, delay=1.0): pass
        def toggle_skip_verification_report(self, _icon=None, _item=None):
            return app_module.AntiTrayApp.toggle_skip_verification_report(self, _icon, _item)

    monkeypatch.setattr(app_module, "is_speech_active", lambda: False)
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)

    app = DummyToggleApp()
    raw_reply = (
        "### Overview\nFeature implemented cleanly.\n\n"
        "### Verification Results\n- `pytest`: 85/85 passed\n\n"
        "Ready to test?"
    )

    # 1. Default skip_verification_report=True filters speech queue while sending full ACK
    app_module.AntiTrayApp._on_assistant_response(app, raw_reply, filepath="chat.jsonl", step_index=10)
    assert len(app.speech_queue) == 1
    queued_text = app.speech_queue[0].text
    assert "Feature implemented cleanly." in queued_text
    assert "85/85 passed" not in queued_text
    assert "Ready to test?" in queued_text
    assert len(app.acks) == 1
    assert "85/85 passed" in app.acks[0][2]

    # 2. Toggling OFF restores full unfiltered read-aloud
    app.toggle_skip_verification_report()
    assert app.skip_verification_report is False
    assert any("OFF" in t for t in app.hud.toasts)
    app_module.AntiTrayApp._on_assistant_response(app, raw_reply, filepath="chat.jsonl", step_index=11)
    assert "85/85 passed" in app.speech_queue[-1].text

    # 3. Tray Settings submenu exposes the Skip Verification Reports checkbox item
    app_module.AntiTrayApp._setup_tray(app)
    get_text = lambda it: it.text(it) if callable(it.text) else str(it.text)
    settings_item = next(
        it for it in app.tray_icon.menu.items
        if it != pystray.Menu.SEPARATOR and "Settings" in get_text(it)
    )
    settings_texts = [get_text(sub) for sub in settings_item.submenu.items if sub != pystray.Menu.SEPARATOR]
    assert any("Skip Verification Reports" in t for t in settings_texts)


def test_windows_startup_helpers_and_tray_toggle(monkeypatch):
    """Verify Windows startup registry helpers and tray Settings toggle without mutating real registry."""
    import sys
    import types
    import pystray
    import desktop.app as app_module

    fake_store = {}

    class FakeKey:
        def __init__(self, subkey):
            self.subkey = subkey
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        KEY_READ=1,
        KEY_SET_VALUE=2,
        REG_SZ=1,
        OpenKey=lambda root, subkey, _res, _access: FakeKey(subkey),
        CreateKeyEx=lambda root, subkey, _res, _access: FakeKey(subkey),
        QueryValueEx=lambda key, name: (
            fake_store[(key.subkey, name)], 1
        ) if (key.subkey, name) in fake_store else (_ for _ in ()).throw(FileNotFoundError()),
        SetValueEx=lambda key, name, _res, _typ, val: fake_store.__setitem__((key.subkey, name), val),
        DeleteValue=lambda key, name: fake_store.pop((key.subkey, name)) if (key.subkey, name) in fake_store else (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    cmd = app_module.get_startup_command()
    assert cmd.startswith('wscript.exe "')
    assert cmd.endswith('launch_anti_tray.vbs"')

    assert app_module.is_windows_startup_enabled() is False
    assert app_module.set_windows_startup_enabled(True) is True
    assert app_module.is_windows_startup_enabled() is True
    assert fake_store[(app_module.STARTUP_REG_KEY, app_module.STARTUP_APP_NAME)] == cmd

    assert app_module.set_windows_startup_enabled(False) is False
    assert app_module.is_windows_startup_enabled() is False

    class DummyHud:
        def __init__(self):
            self.theme = "cyberpunk"
            self.position = "bottom_right"
            self.toasts = []
        def flash_action(self, toast, duration_sec=1.6):
            self.toasts.append(toast)
        def show(self, state="listening", status="", subtitle=""):
            pass

    class DummyStartupApp:
        def __init__(self):
            self.hud_enabled = True
            self.muted = False
            self.hud = DummyHud()
            self.launch_on_startup = False
            self.auto_submit = True
            self.auto_read = True
            self.skip_verification_report = True
            self.speech_speed = 1.0
            self.remote_poll_enabled = False
            self.speech_queue = []
            self.output_history = []
            self.last_spoken_summary = ""
            self.hud_collapsed = False
        def _get_tray_header_text(self, item=None): return "AudioMind"
        def show_status_toast(self, *a, **k): pass
        def toggle_auto_submit(self, *a, **k): pass
        def toggle_auto_read(self, *a, **k): pass
        def toggle_speech_pause(self, *a, **k): pass
        def forward_speech_5(self, *a, **k): pass
        def rewind_speech_5(self, *a, **k): pass
        def skip_next_chapter(self, *a, **k): pass
        def skip_current_output(self, *a, **k): pass
        def repeat_curr_chapter(self, *a, **k): pass
        def repeat_chapter(self, *a, **k): pass
        def repeat_current_output(self, *a, **k): pass
        def go_back_output(self, *a, **k): pass
        def interrupt_speech(self, *a, **k): pass
        def read_highlighted_text(self, *a, **k): pass
        def set_voice_model(self, *a, **k): pass
        def set_hud_theme(self, *a, **k): pass
        def set_speech_speed(self, *a, **k): pass
        def toggle_mute(self, *a, **k): pass
        def toggle_hud(self, *a, **k): pass
        def toggle_hud_dock(self, *a, **k): pass
        def toggle_remote_listener(self, *a, **k): pass
        def test_greeting(self, *a, **k): pass
        def open_firewall_audit(self, *a, **k): pass
        def exit_app(self, *a, **k): pass
        def _hide_hud_after_delay(self, delay=1.0): pass
        def toggle_launch_on_startup(self, _icon=None, _item=None):
            return app_module.AntiTrayApp.toggle_launch_on_startup(self, _icon, _item)

    monkeypatch.setattr(app_module, "is_speech_active", lambda: False)
    monkeypatch.setattr(
        pystray,
        "Icon",
        lambda name, icon, title="", menu=None: types.SimpleNamespace(name=name, icon=icon, title=title, menu=menu),
    )
    app = DummyStartupApp()
    app.toggle_launch_on_startup()
    assert app.launch_on_startup is True
    assert app_module.is_windows_startup_enabled() is True
    assert any("Startup Launch: ON" in t for t in app.hud.toasts)

    app_module.AntiTrayApp._setup_tray(app)
    get_text = lambda it: it.text(it) if callable(it.text) else str(it.text)
    settings_item = next(
        it for it in app.tray_icon.menu.items
        if it != pystray.Menu.SEPARATOR and "Settings" in get_text(it)
    )
    settings_texts = [get_text(sub) for sub in settings_item.submenu.items if sub != pystray.Menu.SEPARATOR]
    assert any("Launch on Windows Startup" in t for t in settings_texts)


def test_expanded_winamp_hud_mode_and_live_reader():
    """Verify WaveformHud expanded Winamp reader mode, hit-testing, and text wrapping."""
    from desktop.ui.hud import WaveformHud

    hud = WaveformHud()
    assert hud.expanded is False
    assert hud.width == 480
    assert hud.height == 38

    # Toggle into expanded Winamp deck (+25% scale: 800x360)
    hud.toggle_expand()
    assert hud.expanded is True
    assert hud.width == 800
    assert hud.height == 360

    # Hit-test top-right expand, locate, collapse, and bottom-right speed pill
    assert hud._hit_test_expand(800 - 148, 25) is True
    assert hud._hit_test_locate(800 - 116, 25) is True
    assert hud._hit_test_collapse(800 - 84, 25) is True
    assert hud._hit_test_speed(650, 310) is True
    assert hud._hit_test_button(85, 310) == "prev"

    # Update live text & playback metadata
    hud.set_live_text(
        phrase="live reader shows context",
        context_before="This is the beginning of the response so the",
        context_after="around what AudioMind is currently speaking aloud.",
        chapter_label="Ch 2/4: Architecture",
    )
    hud.set_playback_meta(elapsed_sec=74.0, total_sec=150.0, queue_count=2, speed_label="1.15x")
    assert hud._format_mmss(74.0) == "1:14"
    assert hud._format_mmss(150.0) == "2:30"

    wrapped = hud._wrap_reader_segments(
        hud.live_context_before,
        hud.live_phrase,
        hud.live_context_after,
        max_chars=48,
        max_lines=3,
    )
    assert 1 <= len(wrapped) <= 3
    active_words = [w for line in wrapped for w, is_act in line if is_act]
    assert active_words == ["live", "reader", "shows", "context"]

    # Toggle back to compact HUD
    hud.toggle_expand()
    assert hud.expanded is False
    assert hud.width == 480
    assert hud.height == 38

    # Verify uniform UI scaling across compact pill, compact dock, and expanded deck
    hud.set_scale(1.25)
    assert hud.width == 600
    assert hud.height == 48
    hud.set_expanded(True)
    assert hud.width == 1000
    assert hud.height == 450
    assert hud._hit_test_speed(650 * 1.25, 310 * 1.25) is True
    hud.set_scale(0.75)
    assert hud.width == 600
    assert hud.height == 270
    assert hud._hit_test_button(85 * 0.75, 310 * 0.75) == "prev"

    # Verify faceplate skin finishes resolve to existing PNGs and load cleanly via _get_scaled_skin
    import os
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    hud.root = root
    try:
        for finish in ("dark", "stainless", "titanium"):
            hud.set_skin_finish(finish)
            for kind, dims in (("expanded", (800, 360)), ("mini", (480, 84)), ("pill", (480, 38))):
                fn = hud._skin_filename(kind)
                assert os.path.exists(os.path.join("desktop", "resources", "skins", fn))
                photo = hud._get_scaled_skin(fn, dims[0], dims[1])
                assert photo is not None
    finally:
        hud.root = None
        root.destroy()


def test_macos_portability_adapters(monkeypatch, tmp_path):
    """Verify macOS (darwin) adapters for startup LaunchAgent, CoreAudio stream, work area, and say TTS."""
    import os
    import sys
    import types
    import wave
    import numpy as np
    import desktop.app as app_module
    import desktop.ui.hud as hud_module
    import desktop.audio.wasapi_stream as wasapi_module
    import desktop.audio.tts as tts_module

    # 1. macOS LaunchAgent startup toggle
    plist_path = tmp_path / "com.audiomind.tray.plist"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(app_module, "MACOS_LAUNCH_AGENT_PLIST", str(plist_path))
    assert app_module.is_windows_startup_enabled() is False
    assert app_module.set_windows_startup_enabled(True) is True
    assert plist_path.exists()
    assert "com.audiomind.tray" in plist_path.read_text(encoding="utf-8")
    assert app_module.set_windows_startup_enabled(False) is False
    assert not plist_path.exists()

    # 2. macOS HUD work-area fallback
    monkeypatch.setattr(hud_module.sys, "platform", "darwin")
    area = hud_module.get_primary_work_area()
    assert len(area) == 4 and area[2] > 0 and area[3] > 0

    # 3. macOS sounddevice fallback in WasapiAecStream
    class FakeSDStream:
        def __init__(self, samplerate, channels, dtype, blocksize):
            self.blocksize = blocksize
            self.started = False
        def start(self): self.started = True
        def read(self, n): return np.zeros((n, 1), dtype=np.float32), False
        def stop(self): self.started = False
        def close(self): pass

    monkeypatch.setattr(wasapi_module.sys, "platform", "darwin")
    monkeypatch.setattr(wasapi_module, "sd", types.SimpleNamespace(InputStream=FakeSDStream))
    stream = wasapi_module.WasapiAecStream(target_sample_rate=16000, frame_duration_ms=80)
    stream.initialize()
    assert stream._use_sounddevice is True
    chunk = stream.read_chunk()
    assert chunk.dtype == np.int16 and len(chunk) == 1280
    stream.close()

    # 4. macOS say offline TTS fallback
    def fake_run(cmd, capture_output=True, timeout=15):
        out_wav = cmd[2]
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(np.zeros(480, dtype=np.int16).tobytes())
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(tts_module.sys, "platform", "darwin")
    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)
    pcm = tts_module.synth_sapi_pcm("Hello Mac")
    assert pcm.shape == (480, 2) and pcm.dtype == np.float32


def test_ollama_backend_adapter_and_mac_hotkey_labels(monkeypatch):
    """Verify Ollama local LLM backend switching, response forwarding, and macOS Cmd+Opt tray labels."""
    import io
    import json
    import sys
    import time
    import urllib.request
    import pystray
    import desktop.app as app_module

    responses = []

    class DummyApp:
        def __init__(self):
            self.agent_backend = "antigravity"
            self._ollama_history = []
            self._ollama_step = 0
            self.hud_enabled = False
            self.muted = True
            self.auto_submit = True
            self.auto_read = True
            self.speech_speed = 1.0
            self.remote_poll_enabled = False
            self.speech_queue = []
            self.output_history = []
            self.last_spoken_summary = ""
            self.hud = type("H", (), {"theme": "seiko", "position": "bottom_right", "expanded": False, "visible": False})()
        def _on_assistant_response(self, text, filepath="", step_index=0):
            responses.append((text, filepath, step_index))
        def _get_tray_header_text(self, item=None):
            return app_module.AntiTrayApp._get_tray_header_text(self, item)
        def show_status_toast(self, *a, **k): pass
        def toggle_auto_submit(self, *a, **k): pass
        def toggle_auto_read(self, *a, **k): pass
        def toggle_speech_pause(self, *a, **k): pass
        def forward_speech_5(self, *a, **k): pass
        def rewind_speech_5(self, *a, **k): pass
        def skip_next_chapter(self, *a, **k): pass
        def skip_current_output(self, *a, **k): pass
        def repeat_curr_chapter(self, *a, **k): pass
        def repeat_chapter(self, *a, **k): pass
        def repeat_current_output(self, *a, **k): pass
        def go_back_output(self, *a, **k): pass
        def interrupt_speech(self, *a, **k): pass
        def read_highlighted_text(self, *a, **k): pass
        def set_voice_model(self, *a, **k): pass
        def set_hud_theme(self, *a, **k): pass
        def set_speech_speed(self, *a, **k): pass
        def toggle_mute(self, *a, **k): pass
        def toggle_hud(self, *a, **k): pass
        def toggle_hud_dock(self, *a, **k): pass
        def toggle_remote_listener(self, *a, **k): pass
        def test_greeting(self, *a, **k): pass
        def open_firewall_audit(self, *a, **k): pass
        def exit_app(self, *a, **k): pass

    def fake_urlopen(req_or_url, timeout=10):
        url = req_or_url.full_url if hasattr(req_or_url, "full_url") else str(req_or_url)
        if url.endswith("/api/tags"):
            body = json.dumps({"models": [{"name": "gemma4:latest"}]}).encode("utf-8")
        else:
            body = json.dumps({"message": {"content": "Hello from local Ollama!"}}).encode("utf-8")
        return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    app = DummyApp()
    app_module.AntiTrayApp.set_agent_backend(app, "ollama", "Ollama Local")
    assert app.agent_backend == "ollama"

    assert app_module.AntiTrayApp._submit_to_ollama(app, "Test prompt") is True
    deadline = time.time() + 2.0
    while not responses and time.time() < deadline:
        time.sleep(0.02)
    assert responses == [("Hello from local Ollama!", "ollama", 1)]

    # Verify Cmd+Opt labels on macOS
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "Cmd+Opt+M" in app._get_tray_header_text()
    monkeypatch.setattr(
        pystray,
        "Icon",
        lambda name, icon, title="", menu=None: type("I", (), {"name": name, "icon": icon, "title": title, "menu": menu})(),
    )
    app_module.AntiTrayApp._setup_tray(app)
    get_text = lambda it: it.text(it) if callable(it.text) else str(it.text)
    root_texts = [get_text(it) for it in app.tray_icon.menu.items if it != pystray.Menu.SEPARATOR]
    assert any("Cmd+Opt+R" in t for t in root_texts)
    assert any("Cmd+Opt+F" in t for t in root_texts)


def test_is_read_highlight_command_matches_natural_variants():
    """Verify natural read-highlight voice variants match without hijacking normal coding prompts."""
    from desktop.app import is_read_highlight_command

    assert is_read_highlight_command("read the highlighted script on the screen") is True
    assert is_read_highlight_command("read the highlighted text") is True
    assert is_read_highlight_command("please read highlighted code to me") is True
    assert is_read_highlight_command("read what's highlighted") is True
    assert is_read_highlight_command("read this") is True

    # Normal coding prompts mentioning 'highlighted' should still pass through to chat
    assert is_read_highlight_command("read the file and fix why highlighted text is broken") is False
    assert is_read_highlight_command("explain how the highlighted function works in app.py") is False


def test_speech_queue_worker_survives_tray_icon_error(monkeypatch):
    """Verify set_tray_state and _speech_queue_worker survive WinError 1402 tray icon races and keep draining queue."""
    import collections
    import threading
    import time
    import desktop.app as app_module

    spoken = []

    class BrokenIcon:
        title = ""
        @property
        def icon(self):
            return None
        @icon.setter
        def icon(self, _val):
            raise OSError(1402, "Invalid cursor handle.")

    class DummyHud:
        visible = False
        def set_progress(self, _p): pass
        def set_status(self, *a, **k): pass
        def show(self, *a, **k): pass
        def hide(self): pass

    class DummyQueueApp:
        def __init__(self):
            self.running = True
            self.muted = False
            self.hud_enabled = True
            self.hud_collapsed = False
            self.is_reading_highlight = False
            self.speech_queue = collections.deque([
                app_module.SpeechQueueItem(text="First queued message", chat_tag="ChatA"),
                app_module.SpeechQueueItem(text="Second queued message", chat_tag="ChatB"),
            ])
            self._speak_lock = threading.Lock()
            self._tray_lock = threading.Lock()
            self._speech_worker_event = threading.Event()
            self._speech_worker_event.set()
            self.current_speech_item = None
            self.hud = DummyHud()
            self.tray_icon = BrokenIcon()
            self.current_state = "listening"
            self.paused_at = None
        def set_tray_state(self, state, title):
            return app_module.AntiTrayApp.set_tray_state(self, state, title)
        def _format_status_with_chat(self, action, extra=""):
            return action

    def fake_speak(text, on_start=None, on_level=None):
        if on_start:
            on_start()
        spoken.append(text)
        if len(spoken) >= 2:
            app.running = False
            app._speech_worker_event.set()

    monkeypatch.setattr(app_module, "speak", fake_speak)
    monkeypatch.setattr(app_module, "is_speaking", lambda: False)
    monkeypatch.setattr(app_module, "is_paused", lambda: False)
    monkeypatch.setattr(app_module, "get_chapter_info", lambda: (1, 1, "Overview"))

    app = DummyQueueApp()
    # Direct set_tray_state should swallow OSError 1402 cleanly
    app.set_tray_state("listening", "AudioMind")

    t = threading.Thread(target=app_module.AntiTrayApp._speech_queue_worker, args=(app,), daemon=True)
    t.start()
    t.join(timeout=3.0)

    assert spoken == ["First queued message", "Second queued message"]


def test_hud_scale_defers_skin_cache_clear_to_tk_thread():
    import threading
    from unittest.mock import MagicMock
    from desktop.ui.hud import WaveformHud

    hud = WaveformHud.__new__(WaveformHud)
    hud._lock = threading.Lock()
    hud._skin_cache = {"cached_key": object()}
    hud._skin_cache_dirty = False
    hud._scale = 1.0
    hud._skin_finish = "dark"
    hud._expanded = False
    hud.root = MagicMock()

    hud.set_scale(1.5)
    assert hud._skin_cache_dirty is True
    assert "cached_key" in hud._skin_cache
    hud.root.after.assert_called()

    hud._skin_cache_dirty = False
    hud.root.after.reset_mock()

    hud.set_skin_finish("stainless")
    assert hud._skin_cache_dirty is True
    assert "cached_key" in hud._skin_cache






def test_player_locator_includes_context_and_duration():
    """Verify get_locator_at_sample returns context_before, context_after, and duration_seconds."""
    import numpy as np
    from desktop.audio.player import SpeechPlayer

    player = SpeechPlayer(samplerate=1000)
    samples = np.zeros((2000, 2), dtype=np.float32)
    text = (
        "First sentence gives background context before the target phrase "
        "and then continues with additional words afterward for reading."
    )
    player.audio_data = samples
    tokens = [(0, w) for w in text.split()]
    player.register_segment_tokens(tokens, start_sample=0, end_sample=2000, chapter_title="Overview")

    info = player.get_locator_at_sample(sample_idx=1000, target_words=4)
    assert info is not None
    assert info["phrase"]
    assert info["context_before"]
    assert info["context_after"]
    assert info["duration_seconds"] == 2.0


def test_is_subagent_handoff_report():
    from desktop.audio.read_aloud import is_subagent_handoff_report

    # Main conversation is never suppressed even if it mentions images/videos/send_message
    assert is_subagent_handoff_report(
        "Image generated and delivered via send_message to caller.",
        is_subagent_transcript=False,
        used_send_message=True,
    ) is False

    # Subagent that used send_message is suppressed
    assert is_subagent_handoff_report(
        "Completed the task.",
        is_subagent_transcript=True,
        used_send_message=True,
    ) is True

    # Subagent media/caller handoff text is suppressed even without tool_calls flag
    assert is_subagent_handoff_report(
        "Image generated and sent to parent agent: C:\\tmp\\render.png",
        is_subagent_transcript=True,
        used_send_message=False,
    ) is True
    assert is_subagent_handoff_report(
        "Sent the final video clip to the caller.",
        is_subagent_transcript=True,
        used_send_message=False,
    ) is True

    # Non-handoff subagent text without send_message is not suppressed
    assert is_subagent_handoff_report(
        "Found three matching files in the workspace.",
        is_subagent_transcript=True,
        used_send_message=False,
    ) is False


def test_transcript_watcher_skips_subagent_handoff_reports(tmp_path):
    import json
    import time
    from desktop.audio.read_aloud import TranscriptWatcher

    sub_dir = tmp_path / "sub-1" / ".system_generated" / "logs"
    sub_dir.mkdir(parents=True)
    sub_file = sub_dir / "transcript.jsonl"
    sub_file.write_text(
        json.dumps({"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "status": "DONE", "content": "Subagent task"}) + "\n",
        encoding="utf-8",
    )

    main_dir = tmp_path / "main-1" / ".system_generated" / "logs"
    main_dir.mkdir(parents=True)
    main_file = main_dir / "transcript.jsonl"
    main_file.write_text(
        json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "content": "Make a video"}) + "\n",
        encoding="utf-8",
    )

    received = []
    watcher = TranscriptWatcher(
        on_new_response=lambda text, fp, idx: received.append((text, fp, idx)),
        skip_subagent_reports=True,
    )
    watcher.get_candidate_transcripts = lambda: [str(sub_file), str(main_file)]
    watcher.start()
    try:
        with open(sub_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [{"name": "send_message"}],
                "content": "",
            }) + "\n")
            f.write(json.dumps({
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [],
                "content": "Image generated and delivered via `send_message` to `main-1`.",
            }) + "\n")
        with open(main_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [],
                "content": "I finished generating your image and video.",
            }) + "\n")

        deadline = time.time() + 3.0
        while time.time() < deadline and len(received) < 1:
            time.sleep(0.05)
        time.sleep(0.2)
    finally:
        watcher.stop()

    assert [r[0] for r in received] == ["I finished generating your image and video."]


def test_toggle_skip_subagent_reports_syncs_watcher():
    import desktop.app as app_module

    class _DummyWatcher:
        def __init__(self):
            self.skip_subagent_reports = True

    app = app_module.AntiTrayApp.__new__(app_module.AntiTrayApp)
    app.skip_subagent_reports = True
    app.transcript_watcher = _DummyWatcher()
    app.hud_enabled = False

    app.toggle_skip_subagent_reports()
    assert app.skip_subagent_reports is False
    assert app.transcript_watcher.skip_subagent_reports is False

    app.toggle_skip_subagent_reports()
    assert app.skip_subagent_reports is True
    assert app.transcript_watcher.skip_subagent_reports is True


def test_parse_steelseries_anc_button_packet():
    from desktop.audio.headset_button import parse_steelseries_anc_button_packet

    anc_on = bytes.fromhex("07 bd 02" + " 00" * 61)
    anc_off = bytes.fromhex("07 bd 00" + " 00" * 61)
    vol_wheel = bytes.fromhex("07 25 28" + " 00" * 61)
    bt_media = bytes.fromhex("07 bb 01" + " 00" * 61)

    assert parse_steelseries_anc_button_packet(anc_on) == 2
    assert parse_steelseries_anc_button_packet(anc_off) == 0
    assert parse_steelseries_anc_button_packet(vol_wheel) is None
    assert parse_steelseries_anc_button_packet(bt_media) is None
    assert parse_steelseries_anc_button_packet(b"\x07\xbd") is None


def test_headset_button_listener_triggers_and_debounces():
    from desktop.audio.headset_button import HeadsetButtonListener

    toggles = []
    listener = HeadsetButtonListener(on_toggle_pause=lambda: toggles.append("toggle"), debounce_sec=0.35)

    anc_on = bytes.fromhex("07 bd 02" + " 00" * 61)
    anc_off = bytes.fromhex("07 bd 00" + " 00" * 61)
    vol_wheel = bytes.fromhex("07 25 28" + " 00" * 61)

    assert listener.handle_packet(vol_wheel, now=1.0) is False
    assert listener.handle_packet(anc_on, now=1.0) is True
    # Duplicate same-state packet ignored
    assert listener.handle_packet(anc_on, now=2.0) is False
    # Within debounce window ignored
    assert listener.handle_packet(anc_off, now=1.1) is False
    # Valid transition after debounce triggers pause/resume
    assert listener.handle_packet(anc_off, now=1.5) is True
    assert listener.handle_packet(anc_on, now=2.0) is True
    assert len(toggles) == 3


def test_toggle_headset_button_controls_listener():
    import desktop.app as app_module

    class _DummyListener:
        def __init__(self):
            self.started = 0
            self.stopped = 0

        def start(self):
            self.started += 1
            return True

        def stop(self):
            self.stopped += 1

    app = app_module.AntiTrayApp.__new__(app_module.AntiTrayApp)
    app.headset_button_enabled = True
    app.headset_button_listener = _DummyListener()
    app.hud_enabled = False

    app.toggle_headset_button()
    assert app.headset_button_enabled is False
    assert app.headset_button_listener.stopped == 1

    app.toggle_headset_button()
    assert app.headset_button_enabled is True
    assert app.headset_button_listener.started == 1


def test_headset_button_double_press_triggers_record_without_pause():
    import time
    from desktop.audio.headset_button import HeadsetButtonListener

    events = []
    listener = HeadsetButtonListener(
        on_toggle_pause=lambda: events.append("pause"),
        on_double_press=lambda: events.append("record"),
        debounce_sec=0.05,
        double_press_window_sec=0.15,
    )

    anc_on = bytes.fromhex("07 bd 02" + " 00" * 61)
    anc_off = bytes.fromhex("07 bd 00" + " 00" * 61)

    # Double-press (two transitions within double_press_window_sec) -> fires record, not pause
    listener.handle_packet(anc_on, now=1.0)
    listener.handle_packet(anc_off, now=1.1)
    time.sleep(0.20)
    assert events == ["record"]

    # Single press -> waits window then fires pause
    listener.handle_packet(anc_on, now=2.0)
    time.sleep(0.20)
    assert events == ["record", "pause"]
    listener.stop()


def test_trigger_voice_command_sets_manual_event():
    import threading
    import desktop.app as app_module

    app = app_module.AntiTrayApp.__new__(app_module.AntiTrayApp)
    app._manual_voice_trigger = threading.Event()
    assert app._manual_voice_trigger.is_set() is False
    app.trigger_voice_command()
    assert app._manual_voice_trigger.is_set() is True
    assert hasattr(app_module.AntiTrayApp, "toggle_speech_pause")
    assert hasattr(app_module.AntiTrayApp, "trigger_voice_command")















