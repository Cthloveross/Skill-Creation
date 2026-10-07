---
name: tutorial-video-chapter-indexer
description: Create a validated JSON chapter index for a tutorial video when an ordered, exact chapter-title list and required video metadata are supplied. Use it for audio/transcript-grounded temporal alignment, especially software tutorials with short transition chapters.
---

# Tutorial Video Chapter Indexer

## Purpose

Produce the requested chapter-index artifact from a local video, preserving every supplied title exactly and locating each chapter at the beginning of its sustained topical instruction. The final artifact is JSON with `video_info` and `chapters`.

This Skill does not assume chapter titles are spoken verbatim. It uses ASR and targeted audio review as evidence, while enforcing the output schema mechanically.

## Inputs required at execution time

- Video path (for example, a supplied `.mp4`).
- Exact video title and duration required by the task.
- Ordered chapter titles copied exactly from the task request.
- Required output JSON path.

Do not infer or normalize titles. Do not place task-specific titles or timestamps in this Skill.

## Workflow

1. **Read supplied metadata and inspect the media.**
   - Read any supplied information file and use `ffprobe` to confirm duration and streams when useful.
   - Treat the task's stated output duration as authoritative if it differs slightly from container metadata.

2. **Extract suitable audio.**
   Run the packaged extractor, which creates a 16 kHz mono PCM WAV:
   ```sh
   python3 scripts/extract_audio.py <<'JSON'
   {"video_path":"/path/to/video.mp4","audio_path":"/tmp/tutorial.wav"}
   JSON
   ```
   It emits a JSON status object. Stop and diagnose a non-`ok` result rather than continuing with an absent or empty audio file.

3. **Create a timestamped transcript.**
   Use an available timestamp-capable ASR implementation, preferably Whisper or faster-whisper, on the extracted WAV. Request segment timestamps and save a normalized transcript JSON file of this shape:
   ```json
   {
     "segments": [
       {"start": 0.0, "end": 4.2, "text": "spoken words"}
     ]
   }
   ```
   A typical Whisper CLI invocation, where installed, is:
   ```sh
   whisper /tmp/tutorial.wav --model small --language en --task transcribe --output_format json --output_dir /tmp/asr
   ```
   If the chosen ASR output uses the common Whisper `segments` format, it already has the required fields. If no timestamp-capable ASR is available, install/use an allowed ASR tool or perform timestamped review; do not fabricate a transcript.

4. **Align titles in chronological order.**
   Build a working table containing title, candidate start time, nearby transcript text, and confidence. For each title:
   - Search semantically, using title concepts, synonyms, Blender terminology, and discourse cues such as “now,” “next,” or an explicit introduction.
   - Select the point at which the instructor begins actively teaching or demonstrating the topic, not an earlier preview or casual reference.
   - Listen to short clips around uncertain candidates. ASR segment starts are timing guides, not guaranteed topic boundaries.
   - Review boundaries globally from first to last; chapter times must be strictly increasing.
   - Preserve short independent moments (for example saving, a break, resume, or an orientation note) even if they occupy only seconds.

   Use the first chapter at `0` as required. For ambiguous transitions, choose the best transcript/audio-supported onset between the preceding and following selected boundaries rather than distributing times uniformly.

5. **Build the artifact.**
   Create an alignment input JSON with the exact titles and selected numeric times, then invoke the builder:
   ```sh
   python3 scripts/build_index.py <<'JSON'
   {
     "output_path": "/required/output.json",
     "video_title": "title required by the task",
     "duration_seconds": 1234,
     "chapters": [
       {"time": 0, "title": "exact first supplied title"},
       {"time": 12.5, "title": "exact second supplied title"}
     ]
   }
   JSON
   ```
   The builder writes the index and emits JSON describing success or validation errors. It rejects invalid input rather than silently changing titles or timestamps.

6. **Validate the actual output file before finishing.**
   Supply the independent expected title list and task constraints to the validator:
   ```sh
   python3 scripts/validate_index.py <<'JSON'
   {
     "index_path": "/required/output.json",
     "expected_titles": ["copy every task title here in order"],
     "expected_video_title": "title required by the task",
     "duration_seconds": 1234
   }
   JSON
   ```
   A successful result is `{"ok": true, ...}`. Correct all reported errors and rerun validation. Also sample-listen to each uncertain boundary and ensure the completed output remains at the task-required path.

## Output contract

The produced JSON must contain:

- `video_info.title`: the supplied required title, as a string.
- `video_info.duration_seconds`: the supplied required duration, numeric.
- `chapters`: exactly one object per supplied title, in supplied order.
- Each chapter object has numeric `time` and exact `title`.

The first time must be `0`; every later time must be strictly greater than its predecessor and lie within `[0, duration_seconds]`.

## Failure handling

- Missing video, unreadable media, unavailable `ffmpeg`, or failed ASR means alignment evidence is incomplete; report and resolve that prerequisite rather than producing guessed timestamps.
- A transcript may be noisy. Use playback and contextual topic transitions to resolve it; do not depend on literal title matches alone.
- If validation fails due to count, title, type, range, or ordering, edit the alignment input and rebuild. Never hand-edit titles into approximate variants.
