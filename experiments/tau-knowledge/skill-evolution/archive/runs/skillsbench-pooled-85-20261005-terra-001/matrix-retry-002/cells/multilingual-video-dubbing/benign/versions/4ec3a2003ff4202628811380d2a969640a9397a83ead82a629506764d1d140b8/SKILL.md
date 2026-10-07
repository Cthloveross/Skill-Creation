---
name: timed-multilingual-video-dubbing
description: Create target-reference-script speech WAVs, a synchronized 48 kHz mono dubbed MP4 retaining an input video's visuals, and an input-grounded delivery report.
---

# Timed multilingual video dubbing

Use this Skill when given an input video, a timing-only `segments.srt`, source transcript SRT, approved target-language reference-script SRT, and a two-letter target-language code. Synthesize the approved reference text; do not independently translate the source transcript.

The executable writes these artifacts directly to the requested output root (default `/outputs`):

- `/outputs/tts_segments/seg_0.wav` and one `seg_N.wav` per later timing cue
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Requirements and assumptions

Python 3, `ffmpeg`, and `ffprobe` are required. `espeak-ng` or `espeak` is used when installed as an offline speech engine. If neither is available, the program creates a non-silent local fallback so that it never silently substitutes an empty audio track; install an appropriate target-language TTS engine for production-quality voice rendering.

All three SRT files must have matching cue counts. The timing file supplies windows only, while source and reference SRT files supply report text and target TTS text respectively. Every timing window must have positive duration and fit within the input video.

## Run

`scripts/dub.py` reads one JSON object from stdin and emits one JSON result on stdout.

```sh
printf '%s\n' '{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en"
}' | python3 scripts/dub.py
```

All shown values are defaults. A successful response has this schema:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

On invalid inputs or an unavailable required media tool, the script emits `{"ok":false,"error":"..."}` and exits nonzero. That is not a completed delivery.

## Method

1. Parse cue timing from `segments.srt`, then pair source and reference text by cue index.
2. Synthesize each approved target cue. Render a 48,000 Hz mono PCM WAV for each window. Longer speech is rate-adjusted; shorter speech is padded with silence.
3. Delay every window WAV by its exact start time in samples, mix on a silent source-duration timeline, and normalize the program toward -23 LUFS.
4. Mux the generated mono 48 kHz AAC audio with `-c:v copy`, retaining the original video stream without video re-encoding. Measure final MP4 loudness using FFmpeg `ebur128`; if necessary apply a correction based on the encoded MP4 measurement and mux again.
5. Probe final media and write the JSON report. `placed_start_sec` equals the requested cue start, and `drift_sec` is computed as `placed_end_sec - window_end_sec`.

The report always uses `en` for `source_language`, copies the exact code from `target_language.txt`, records actual container durations, and reports loudness measured from the final MP4 audio.
