---
name: timed-multilingual-video-dubbing
description: Synthesize approved reference-script dialogue, align it to SRT windows, preserve the input video stream, and deliver a 48 kHz mono dubbed MP4 plus an auditable JSON report.
---

# Timed multilingual video dubbing

Use this Skill with an input video, a timing-only `segments.srt`, source-transcript SRT, approved target-language reference-script SRT, and a two-letter target-language file. The approved target reference text is the TTS input; do not independently translate the source transcript.

The entrypoint creates the required deliverables at these exact paths:

- `/outputs/tts_segments/seg_0.wav` (and `seg_N.wav` for later cues)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

The supplied runtime's writable artifact mount may be `/output`. The script writes there first and publishes the same files at `/outputs`; this prevents a successful render from being lost when only `/output` is retained by the artifact collector.

## Prerequisites

Python 3, `ffmpeg`, and `ffprobe` are required. `espeak-ng` or `espeak` is used when available for local speech synthesis. It should have a voice supporting the target code. If no usable local speech engine is available, the script uses a deterministic voiced fallback so it can still produce decodable, non-silent media; production use should install a target-language-capable neural or local TTS engine.

All SRT files must have the same positive cue count. Segment windows must have positive duration and fit within the input video timeline. `target_language.txt` must contain exactly one ISO-639-1 two-letter code.

## Run

`scripts/dub.py` accepts one JSON object on stdin and emits one JSON result on stdout.

```sh
printf '%s\n' '{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "source_language": "en"
}' | python3 scripts/dub.py
```

All paths above are defaults. An optional `output_dir` selects the writable staging directory; it defaults to `/output` when that mount exists, otherwise `/outputs`. Regardless of staging location, default-contract results are published under `/outputs`.

Success output:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

Failure output is `{"ok":false,"error":"..."}` and has a nonzero exit status. It is not a completed delivery.

## Method

1. Parse timing only from `segments.srt`; pair source and approved target texts by cue index.
2. Synthesize each approved target cue, explicitly resample/downmix it to 48,000 Hz mono, and trim or pad it exactly to its window duration. Thus placed audio begins at the SRT window start and has zero end drift.
3. Build a program-length mono timeline with sample-accurate delayed cue inputs. Measure and normalize this complete dialogue timeline near -23 LUFS, mux it with `-c:v copy`, and remeasure final MP4 audio with ffmpeg `ebur128`. A measured correction pass is applied when AAC encoding changes loudness.
4. Probe the delivered MP4 before report creation. The report uses source/reference text verbatim from the supplied SRTs, the exact target-language-file code, actual container durations, final-media loudness, and `placed_end_sec - window_end_sec` drift.

The script verifies output existence, readable 48 kHz mono segment/MP4 audio, source timeline duration, and copied video metadata before declaring success.
