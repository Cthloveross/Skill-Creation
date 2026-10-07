---
name: video-tutorial-indexer
description: >-
  Build a chapter index JSON for a tutorial video by transcribing its audio with
  Whisper and aligning a KNOWN, ordered list of chapter titles to timestamps in
  the transcript. Use when you are given a video file plus the exact chapter
  titles (and a target output JSON schema with video_info.title/duration_seconds
  and a chapters array of {time, title}) and must emit strictly increasing
  timestamps that mark where each chapter's topic first begins. The chapter list,
  video path, title, duration and output path are task inputs read at runtime --
  nothing about a specific video is hardcoded here.
---

# Video Tutorial Chapter Indexer

## What this Skill does

Given a video and a fixed ordered list of chapter titles, it:
1. extracts 16 kHz mono WAV audio with ffmpeg,
2. transcribes it to timestamped segments with Whisper (faster-whisper preferred,
   openai-whisper fallback), caching the transcript,
3. aligns each chapter title to a transcript position using fuzzy keyword/semantic
   matching under a global monotonic (strictly increasing) ordering constraint,
4. writes the output JSON and validates every structural invariant.

The method treats a recognized phrase as *evidence* of a topic, and uses a global
alignment (not independent per-title best match) so the final timeline is
strictly increasing, starts at 0, and stays within the video duration.

## Inputs the executor must supply at runtime

Read the actual task prompt and any VIDEO_INFO.md. Do NOT copy the sample values
below -- they are illustrative. Build a config JSON like:

```json
{
  "video": "/root/tutorial_video.mp4",
  "output": "/root/tutorial_index.json",
  "video_info": {"title": "<exact title from the task>", "duration_seconds": 1382},
  "chapters": ["<title 1 verbatim>", "<title 2 verbatim>", "..."],
  "transcript_cache": "/root/transcript.json",
  "model": "small"
}
```

- `chapters` must reproduce every title **character-for-character** (apostrophes,
  capitalization, punctuation like `Great job!`). The script echoes them unchanged.
- `duration_seconds` and `title` come from the task's required schema.
- `model` defaults to `small`; `base` is faster but noisier.

## How to run it (end to end)

```bash
cd /app/environment/skills/current
# 1. Measure the real duration if the task gives one, trust the task value for schema.
ffprobe -v error -show_entries format=duration -of csv=p=0 /root/tutorial_video.mp4

# 2. Produce the index (does extraction + transcription + alignment + validation).
cat > /tmp/cfg.json <<'JSON'
{ ... fill with the runtime config described above ... }
JSON
python scripts/build_index.py < /tmp/cfg.json
```

`build_index.py` prints a JSON report on stdout:
`{"status": "...", "output_path": "...", "chapters": [...], "validation": {"ok": bool, "errors": [...]}, "warnings": [...]}`
and writes the output file. If `validation.ok` is false, inspect `errors` and fix
the config (usually a title mismatch or a duration out of range) and rerun.

### Running stages separately (useful for debugging)

- `python scripts/transcribe.py` with stdin
  `{"video":"...","wav":"/tmp/a.wav","model":"small","out":"/root/transcript.json"}`
  emits `{"segments":[{"start":..,"end":..,"text":".."}],"backend":".."}`.
- `python scripts/align.py` with stdin
  `{"transcript":[...segments...],"chapters":[...],"duration":1382}` emits
  `{"chapters":[{"time":..,"title":".."}],"warnings":[...]}`.
- `python scripts/validate.py` with stdin
  `{"output_path":"/root/tutorial_index.json","chapters":[...expected titles...],"duration":1382}`
  emits `{"ok":bool,"errors":[...]}`.

## Alignment method (why it is robust)

- **Keyword/fuzzy matching, not substring search.** Each chapter title is reduced
  to content words (stopwords removed); each transcript window (a segment plus a
  short lookahead) is scored by the mean best fuzzy ratio of chapter words against
  window words. This tolerates ASR errors and paraphrasing.
- **Global monotonic DP.** A dynamic program assigns increasing segment indices to
  the chapters so the chosen timeline is non-decreasing; a repair pass forces
  **strictly** increasing integer timestamps, sets the first chapter to 0, and
  clamps everything to `[0, duration)`. This enforces the ordering constraint
  globally rather than per title.
- **Mild positional prior.** A small bonus favors spreading chapters across the
  timeline (introductions short, core procedures long), used only to break ties so
  short/vague titles (e.g. `Break`, `Save`) do not collapse onto neighbors.

See `references/alignment-notes.md` for the archetype/duration cues and the
"sustained discussion marks the true start" rule the scoring is built around.

## Failure handling

- If no Whisper backend is importable, `transcribe.py` tries `pip install
  faster-whisper` (then `openai-whisper`) when the network is allowed; if that
  also fails it reports an error. Alignment cannot be grounded without a
  transcript, so resolve transcription first rather than emitting arbitrary times.
- If the transcript has fewer segments than chapters, alignment falls back to
  evidence-anchored even spacing and records a warning.
- `validate.py` is the final gate: it reproduces the schema invariants from the
  task (29 vs supplied count, exact titles, numeric times, strict monotonicity,
  first=0, within duration). Treat a non-empty `errors` list as a failure to fix.

Do not hardcode timestamps or titles into the scripts; always read them from the
runtime task inputs.
