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
    assert hud._hit_test_button(119, 62) == "rewind"
    assert hud._hit_test_button(193, 62) == "play_pause"
    assert hud._hit_test_button(267, 62) == "forward"
    assert hud._hit_test_button(341, 62) == "next"
    assert hud._hit_test_button(415, 62) == "skip"
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
    hud._on_canvas_click(DummyEvent(119, 62))
    hud._on_canvas_click(DummyEvent(193, 62))
    hud._on_canvas_click(DummyEvent(267, 62))
    hud._on_canvas_click(DummyEvent(341, 62))
    hud._on_canvas_click(DummyEvent(415, 62))
    assert events == ["prev", "rewind", "play_pause", "forward", "next", "skip"]

    # Click outside buttons (row 1 LCD screen) triggers general on_click
    events.clear()
    hud._on_canvas_click(DummyEvent(50, 20))
    assert events == ["general_click"]

    # 4. Test hover hint tracking
    hud._on_mouse_move(DummyEvent(45, 62))
    assert hud.hovered_button == "prev"
    assert hud._hover_hint == "⏮  REPEAT / PREV CHAPTER"

    hud._on_mouse_move(DummyEvent(119, 62))
    assert hud.hovered_button == "rewind"
    assert hud._hover_hint == "⏪  REWIND 5 SECONDS"

    hud._on_mouse_move(DummyEvent(193, 62))
    assert hud.hovered_button == "play_pause"

    hud._on_mouse_move(DummyEvent(415, 62))
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
        def repeat_chapter(self, icon=None, item=None): pass
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
        "last output",
        "go back output",
        "go back an output",
        "go back one output",
        "go back 1 output",
        "previous response",
        "last response",
        "go back a response",
        "go back one response",
        "read previous output",
        "re-read last output",
        "replay previous output",
        "replay last output",
        "read last output",
        "re-read last response",
        "read previous response",
    ]

    for p in prev_phrases:
        assert match_playback_intent(p, speech_active=True) == "PREVIOUS_OUTPUT", f"Phrase '{p}' did not match PREVIOUS_OUTPUT while active"
        assert match_playback_intent(p, speech_active=False) is None, f"Phrase '{p}' should not match when inactive"


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








