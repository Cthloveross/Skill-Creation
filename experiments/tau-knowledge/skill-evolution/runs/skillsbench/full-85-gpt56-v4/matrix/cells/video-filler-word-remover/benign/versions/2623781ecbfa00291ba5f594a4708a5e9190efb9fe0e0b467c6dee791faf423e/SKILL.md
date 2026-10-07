---
name: video-filler-word-remover
description: Detect a declared vocabulary of filler words and adjacent multi-word filler phrases from word-timestamped English ASR, write timestamp annotations, and create a chronologically concatenated video of the detected utterances. Use for videos with audio and video streams when word-level timestamps—not merely ASR segments—can be obtained.
---

# Filler-word annotation and clip extraction

This Skill produces the two requested deliverables from a video:

- an annotations JSON array whose objects are `{ "word": string, "timestamp": number }`; and
- a re-encoded MP4 containing the detected filler utterances in source order.

It treats the requested vocabulary as the operational definition of a filler. In particular, common words such as `like`, `so`, and `well` are matched when the ASR recognizes them. If a stricter discourse-context definition is required, inspect the transcript and supply a reviewed word-timestamp list to the script rather than pretending segment timestamps are word timestamps.

## Prerequisites

The runtime needs `ffmpeg` and `ffprobe`, and one word-timestamp ASR backend:

1. Preferred: Python package `faster-whisper` (CPU-compatible; model downloads require network access or a pre-populated model cache).
2. Fallback: the Python package `openai-whisper`/`whisper` with a version supporting `word_timestamps=True`.

For a new environment, install the preferred backend before running, for example `python -m pip install faster-whisper`. Do not use an ASR backend that returns only segment-level timestamps: assigning a segment start to all words is invalid for this task.

The default model is `small.en`. On constrained CPU systems `base.en` is a reasonable explicit tradeoff; use a larger model only when resources permit. Preserve the ASR model and configuration used for a production annotation so detections can be audited.

## Run

Run the packaged entrypoint from the Skill directory. It accepts exactly one JSON object on standard input and emits a JSON execution report on standard output. Diagnostics go to standard error.

```sh
python3 scripts/run_filler_removal.py <<'JSON'
{
  "input_video": "/root/input.mp4",
  "annotations_path": "/root/annotations.json",
  "output_video": "/root/output.mp4",
  "backend": "auto",
  "model": "small.en",
  "language": "en",
  "clip_padding_seconds": 0.12
}
JSON
```

Input fields:

- `input_video` (required unless `words` is supplied): source video path.
- `annotations_path` and `output_video` (required): destinations. Parent directories must already exist.
- `backend`: `auto`, `faster-whisper`, or `whisper` (default `auto`).
- `model`: ASR model identifier (default `small.en`).
- `language`: language passed to ASR, default `en`; use `null` for ASR auto-detection where supported.
- `clip_padding_seconds`: nonnegative context added before and after each recognized utterance, default `0.12`.
- `max_phrase_gap_seconds`: maximum gap between adjacent words of a multi-word phrase, default `1.5`.
- `fillers`: optional replacement list of filler strings. The default is the vocabulary requested by this task.
- `words`: optional externally produced, genuine word-timestamp evidence. Each item must have `word` (or `token`), `start`, and `end` numeric seconds. When supplied, ASR is skipped. This is useful after a human-reviewed or specialized aligner run.

The script first extracts 16 kHz mono 16-bit PCM audio, obtains word-level ASR timing, normalizes only for matching, and retains raw timing. It matches longest adjacent phrases first, so a matched phrase is not also emitted as a partial overlapping match. A phrase timestamp is the first word's start; its clip ends at the final word's end. Annotations remain individual detections even when padding makes neighboring media clips overlap. Such clip intervals are merged before encoding to avoid duplicate material.

The entrypoint refuses to fabricate a video when no fillers are found, when timing is missing, or when the source lacks an audio or video stream. It writes `[]` to the annotation path in the no-detection case and exits nonzero; this makes the absence of a stitchable clip set explicit.

## Validation

On success the script validates that:

- the written JSON is an array with only the requested normalized filler strings, finite nonnegative timestamps, and chronological ordering;
- clip bounds were clamped to the actual source duration and merged intervals are ordered and non-overlapping;
- FFmpeg successfully decoded the resulting MP4;
- the output has both audio and video streams and a finite positive duration.

The clips are trimmed from the same serialized interval list for both audio and video, reset to zero-based timestamps per segment, concatenated, and re-encoded (rather than stream-copied) for frame-accurate short cuts. For sensitive production work, additionally audition every join and compare decoded audio around joins with reconstruction from the saved interval list; codec priming and frame quantization can make duration-only checks insufficient.
