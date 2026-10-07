---
name: video-silence-remover
description: Analyze a teaching video for a static/noisy opening and sustained audio pauses, render synchronized A/V removal cuts, and write compressed_video.mp4 plus a validated compression_report.json.
---

# Video Silence Remover

Use this Skill when a teaching recording needs its unnecessary opening and long pauses removed while preserving instructional content. It uses the actual input media at runtime; it does not assume a fixed duration, opening length, or removal percentage.

## Requirements and assumptions

- `ffmpeg`, `ffprobe`, and Python 3 are available.
- The input has both an audio and a video stream. Precise cuts are rendered by re-encoding rather than unsafe stream-copy cutting.
- Audio quietness is only a candidate signal. The automatic opening rule is deliberately conservative: it requires an initially static prefix and a sustained visual transition; opening noise or an isolated voice does not end the prefix. Long quiet intervals are removed only after that inferred onset.
- If review establishes exact boundaries, pass them as `remove_intervals`; this is preferable for ambiguous material and bypasses automatic classification.

## Run

From the desired workspace, invoke the packaged script with JSON on standard input:

```sh
python3 /app/environment/skills/current/scripts/remove_silence.py <<'JSON'
{"input":"/root/data/input_video.mp4","output_dir":"/root"}
JSON
```

The script writes:

- `compressed_video.mp4`
- `compression_report.json`
- `removal_diagnostics.json`, a reviewable record of inferred thresholds, onset, candidates, and final intervals.

Its stdout is a JSON object containing the same output paths and final report.

### JSON input schema

```json
{
  "input": "/absolute/or/relative/input.mp4",
  "output_dir": "/directory/for/results",
  "min_pause_seconds": 2.0,
  "silence_threshold_db": -35.0,
  "remove_intervals": [{"start": 0.0, "end": 12.5}]
}
```

Only `input` and `output_dir` are required. `min_pause_seconds` must be positive. If `silence_threshold_db` is omitted, a conservative threshold is estimated from decoded audio and recorded in diagnostics. `remove_intervals`, when supplied, must be a chronologically sortable list of source-time intervals and is normalized, clamped, and used as the single source of truth.

## Method

1. Probe source duration and require decodable audio and video streams.
2. Decode low-rate mono audio to estimate a quiet threshold and sample low-resolution video to recognize a static leading prefix. Infer opening onset from a sustained visual departure after that prefix; audio activity alone cannot end a static/noisy opening.
3. Run FFmpeg `silencedetect` using the selected threshold. Retain only quiet runs at least the requested duration and only those after program onset. Merge overlapping/touching removals; do not cut ambiguous short events.
4. Serialize normalized source intervals. Derive the complementary keep intervals from those exact intervals.
5. Apply matching `trim`/`atrim` bounds, reset timestamps, concatenate synchronized pairs, and re-encode one MP4.
6. Re-probe the rendered file, check streams and duration arithmetic, then write the report. The report’s duration fields come from actual media probes; its segment list contains ordered, non-overlapping source intervals.

Review `removal_diagnostics.json` if the opening contains meaningful speech, music, animation, or an atypical noise floor. In such cases rerun with reviewed `remove_intervals`; do not force a target compression percentage.
