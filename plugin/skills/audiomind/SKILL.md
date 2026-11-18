---
name: audiomind
description: Use AudioMind's voice HUD and TTS tools to speak concise status updates aloud, check desktop harness status, and format multi-section replies cleanly for hands-free listening.
---

# AudioMind Voice Assistant Skill

Use this skill when the user is working hands-free with **AudioMind** or asks you to speak updates aloud through the desktop audio engine.

## Guidelines
1. **Use Markdown Headings for Chapters**: AudioMind automatically splits replies into navigable chapters based on `##` / `###` headings. Keep headings short and descriptive (e.g., `### Root Cause`, `### Next Steps`).
2. **Keep Spoken Notifications Concise**: When calling `audiomind_speak`, keep the message to 1-2 natural sentences without raw stack traces, file paths, or ASCII tables.
3. **Check Status Before Speaking**: Call `audiomind_status` if you need to verify whether the AudioMind desktop tray app is running.
