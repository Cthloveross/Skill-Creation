---
name: teaching-video-silence-remover
description: Removes a validated non-teaching opening and sustained audio pauses from an audiovisual teaching video, producing a synchronized MP4 and JSON removal report. Use when source-time removal intervals must accurately describe the resulting audio and video timeline.
---

# Teaching Video Silence Remover

This Skill creates `compressed_video.mp4` and `compression_report.json`. It detects an initial static/quiet opening using both low-resolution visual change and sustained later audio activity, then detects later long audio-silence candidates. It retains guards at pause edges to avoid clipping speech.

The serialized `segments_removed` list is the editing source of truth. The script normalizes and serializes removal intervals, reloads those exact values, derives their complementary keep intervals, and applies those same source-time boundaries to both streams.

## Requirements

- Python 3 standard library.
- `ffmpeg` and `ffprobe` on `PATH`.
- FFmpeg H.264 (`libx264`) and AAC encoders.
- An input containing both audio and video streams.

## Run

The entrypoint accepts one JSON object on stdin and emits a JSON result on stdout:

```sh
printf '%s\n' '{"video_path":"/root/data/input_video.mp4","output_dir":"/root"}' \
  | python3 scripts/process_video.py
```

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

Only `video_path` is required. `output_dir` defaults to the current directory. All optional numeric fields shown are defaults.

## Editing and synchronization method

1. Probe and validate the source streams.
2. Decode an audio activity track, run FFmpeg `silencedetect`, and sample grayscale video frames for static-opening evidence.
3. Determine a durable opening onset only when opening-like prefix evidence is followed by sustained activity. Detect later silence candidates at or above `min_pause_seconds`.
4. Normalize intervals, serialize them at six-decimal source-time precision, reload the serialization, and derive the keep list from it.
5. Trim every video keep segment and every audio keep segment with identical boundaries and reset each segment timestamp.
6. **Concatenate video and audio independently** (`concat` video-only and audio-only filter chains), then mux the two results. This prevents FFmpeg's combined A/V concat behavior from padding audio to slightly longer video segment boundaries and accumulating audio timeline drift across edits.
7. Re-probe and fully decode the result, validate report arithmetic, and compare decoded retained audio excerpts with the source at report-implied source/output times. The process fails rather than publishing a report/media pair whose waveform timeline does not agree.

Opening and pause detection are heuristic. Review ambiguous quiet teaching, music, or spoken introductions before using detected cuts in a high-stakes workflow. Do not force cuts merely to achieve a desired compression percentage.

## Validate an existing result

```sh
printf '%s\n' '{"input_video":"/root/data/input_video.mp4","output_video":"/root/compressed_video.mp4","report":"/root/compression_report.json"}' \
  | python3 scripts/validate_output.py
```

The validator checks stream presence, full decodability, report schema and arithmetic, and retained-audio correspondence to the report timeline. It emits an object with `ok`, measured durations, and any errors, and exits nonzero when invalid.
