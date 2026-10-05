---
name: video-filler-word-remover
description: Detect a declared vocabulary of filler words and phrases in a video using genuine word-level ASR timestamps, write the required annotations JSON, and concatenate precise re-encoded video clips for each detection. Use when an input video and an explicit filler vocabulary must produce timestamp annotations and a filler-only video.
---

# Video filler-word detection and clip assembly

This skill produces `/root/annotations.json` and `/root/output.mp4` from a video such as `/root/input.mp4`. It keeps recognition, lexical detection, and media rendering separate so that timestamps retain their provenance.

## Prerequisites

- `ffmpeg` and `ffprobe` must be available.
- The video must contain both audio and video streams.
- A locally available ASR model with **word timestamps** is required. The entrypoint supports `faster-whisper` and OpenAI `whisper`; do not use a recognizer that returns only segment timestamps.
- Network is not required or assumed. Supply a local model directory/file, or a model identifier known to be present in the selected backend's cache. Before a long run, inspect the installed packages and local model caches and select a CPU-appropriate model.

`faster-whisper` is preferred on CPU because it exposes word objects directly. `whisper` is a fallback when its Python package and model are locally available. The supplied model is passed to the installed backend; the executor should not cause a download in a network-disabled runtime.

## Run

The executable entrypoint reads one JSON object from stdin and emits a JSON run report to stdout:

```json
{
  "input": "/root/input.mp4",
  "annotations": "/root/annotations.json",
  "output": "/root/output.mp4",
  "backend": "faster-whisper",
  "model": "/path/to/local/asr-model",
  "clip_padding": 0.0
}
```

Invoke `scripts/run_pipeline.py` with that object. `input`, `annotations`, and `output` default to the task paths above. `backend` may be `faster-whisper`, `whisper`, or `auto`; `auto` tries the two supported Python backends in that order. `model` is required unless the `ASR_MODEL` environment variable is set. `clip_padding` is an optional nonnegative number of seconds added on each side of a detected word interval; the default of `0.0` makes clips span the recognized word/phrase itself.

For example, an execution agent can send the JSON above to the packaged script. It must inspect the emitted report and retain the generated artifacts only when `ok` is true.

## Method

1. Probe the actual input duration and stream presence with `ffprobe`.
2. Transcribe the source media once with word timestamps enabled. Every retained token has its raw ASR text, start, and end time. Missing, non-finite, or nonpositive word timing is rejected rather than fabricated from an ASR segment boundary.
3. Normalize token text for matching by case-folding and removal of attached punctuation, while retaining the raw ASR token internally. Match the requested fillers over contiguous tokens. The detector uses a left-to-right, longest-phrase-first non-overlap policy: for example, `you know` is emitted once rather than also emitting a component match.
4. Write the task-required JSON array. Each object has exactly `word` (the canonical declared filler or phrase) and `timestamp` (the genuine start time of its first ASR word).
5. For every detection, use its first-word start through final-word end (plus optional padding), clamp to the input duration, and sort chronologically. FFmpeg decodes, trims both streams with the identical bounds, resets timestamps, concatenates, and re-encodes; it does not use keyframe-dependent stream-copy cutting.
6. Decode/probe the generated output and require finite nonnegative duration plus at least one audio and one video stream.

The current default vocabulary is the one requested by this task: `um`, `uh`, `hum`, `hmm`, `mhm`, `like`, `you know`, `i mean`, `yeah`, `so`, `kind of`, `basically`, `i guess`, `well`, and `okay`. The optional `fillers` input can replace it with an explicit list of strings for another compatible task.

## Validation and failures

The entrypoint validates word timing, serialized annotation schema, bounds, ordering, the output streams, and output duration. It emits a structured error object to stdout and exits nonzero for unavailable ASR backends/models, media without required streams, malformed ASR timing, FFmpeg failure, or zero detections. A zero-detection result still writes `[]` to the annotations path, but no filler-only video can truthfully be assembled, so the run is unsuccessful rather than inventing a clip.

Use `scripts/detect_fillers.py` only when another ASR process has already generated genuine word-level tokens. Its JSON input is `{"tokens":[{"text":"...","start":number,"end":number},...], "fillers":[...optional...]}` and its output contains the matched canonical word, timestamp, end time, and source token indexes. It is deterministic and useful for validating ASR-token ingestion independently of media rendering.
