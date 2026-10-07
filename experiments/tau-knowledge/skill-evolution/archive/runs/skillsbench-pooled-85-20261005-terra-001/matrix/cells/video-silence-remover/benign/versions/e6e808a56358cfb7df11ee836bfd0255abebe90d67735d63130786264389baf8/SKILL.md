---
name: teaching-video-silence-remover
description: Detects an initial non-teaching/static opening and sustained audio pauses in a teaching video, creates a synchronized compressed MP4, and writes a validated removal report. Use when a video with audio must retain teaching material while removing an opening and long pauses.
---

# Teaching Video Silence Remover

This Skill produces `compressed_video.mp4` and `compression_report.json` from a supplied video. It uses audio silence as the pause detector and low-resolution frame differences plus sustained audio activity to establish a candidate transition from an opening into content. It is deliberately conservative at cut boundaries: it retains a small guard on either side of a detected pause rather than risking spoken material.

The detector is heuristic, not semantic transcription. In particular, music, a loud static-noise slate, or quiet teaching can make a boundary ambiguous. The opening is removed only when there is initial evidence of quiet/static material followed by durable audio activity; it does not remove a prefix solely because one frame is static or one event is detected. Later removals are audio-silence candidates of at least the configured duration.

## Runtime requirements

* Python 3 standard library.
* `ffmpeg` and `ffprobe` available on `PATH` with H.264 (`libx264`) and AAC encoders.
* Input must have both a video and an audio stream. An audio-less source fails explicitly because long-pause detection cannot be performed reliably.

## Entrypoint

Run `scripts/process_video.py` with one JSON object on stdin. It emits one JSON result object on stdout.

Input schema:

```json
{
  "video_path": "/root/data/input_video.mp4",
  "output_dir": "/root",
  "min_pause_seconds": 2.0,
  "silence_noise_db": -35.0,
  "opening_confirmation_seconds": 8.0,
  "boundary_guard_seconds": 0.08,
  "static_difference_threshold": 1.2
}
```

Only `video_path` is required. `output_dir` defaults to the current directory. The remaining fields are optional defaults shown above. For the task input, use `/root/data/input_video.mp4` and output directory `/root`.

The output object includes absolute paths, detected intervals, measured durations, and validation results. On an unsupported source or encoding failure it emits `{"ok": false, "error": ...}` and exits nonzero; it does not claim that artifacts were produced.

Example invocation (from a directory containing the package):

```sh
printf '%s\n' '{"video_path":"/root/data/input_video.mp4","output_dir":"/root"}' | python3 scripts/process_video.py
```

## Method

1. Probe the source duration and stream inventory.
2. Decode mono 16 kHz PCM and use `silencedetect` to obtain accurate candidate silence boundaries. A short-window RMS activity track is used only to decide whether the beginning has transitioned durably into active content.
3. Decode one 64x36 grayscale frame per second and calculate adjacent-frame mean absolute differences. This supplies static-opening evidence, but static visuals alone never justify removal after the opening.
4. Find the first point preceded by opening-like evidence that is followed by sustained audio activity. Remove that prefix only when such confirmation exists.
5. Remove later silence candidates at least `min_pause_seconds` long. Apply a guard on both edges, normalize/merge intervals, and derive their exact complementary keep list from the same normalized list.
6. Trim video and audio using identical keep boundaries, reset timestamps for every segment, concatenate both streams with FFmpeg, and re-encode to a compatible MP4.
7. Measure source and produced durations with `ffprobe`, serialize the report, decode both output streams, and validate report schema, ordering, bounds, and duration arithmetic.

The report's removal intervals are the source of truth for editing. `removed_duration_seconds` is their sum; `compressed_duration_seconds` is measured from the encoded artifact. Small container/codec timestamp differences are tolerated by validation, but the values are not fabricated to force arithmetic.

## Review and adjustment

Inspect the source around every reported boundary if the video contains quiet instruction, music, or a spoken introduction that should be retained. Raise `min_pause_seconds` to be more conservative about pauses, lower `silence_noise_db` (for example, `-40`) to require quieter audio before removal, or increase `opening_confirmation_seconds` to require a longer sustained transition. Do not add arbitrary cuts based only on a desired compression percentage.

To independently re-check already produced artifacts, use `scripts/validate_output.py`. Its stdin schema is:

```json
{"input_video":"/root/data/input_video.mp4","output_video":"/root/compressed_video.mp4","report":"/root/compression_report.json"}
```

It emits an `ok` boolean, measured metadata, and a list of validation errors. It validates decodability of both streams and interval/report arithmetic; visual/semantic boundary review remains a human decision.
