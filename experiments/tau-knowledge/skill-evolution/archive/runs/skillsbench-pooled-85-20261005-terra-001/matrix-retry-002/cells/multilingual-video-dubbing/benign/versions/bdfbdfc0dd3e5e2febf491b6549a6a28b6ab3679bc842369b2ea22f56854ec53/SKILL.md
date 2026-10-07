---
name: timed-multilingual-video-dubbing
description: Create target-reference-script speech, a 48 kHz mono dubbed MP4 retaining the original video stream, and an input-grounded timing and loudness report.
---

# Timed multilingual video dubbing

Use this Skill for an input video, timing-only `segments.srt`, source-transcript SRT, approved target-language reference-script SRT, and a two-letter target-language file. The approved reference target script is the TTS input; do not translate the source transcript independently.

The entrypoint writes the required deliverables directly under `/outputs` by default:

- `/outputs/tts_segments/seg_0.wav` (and one WAV for every additional cue)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Prerequisites

The runtime needs Python 3, `ffmpeg`, and `ffprobe`. For intelligible local synthesis, install `espeak-ng` or `espeak` with a voice for the requested target language. If neither is available or it cannot render the requested voice, the script creates a deterministic audible fallback so media delivery can still complete; production delivery should use a language-capable neural or local TTS engine.

All three SRT files must have matching positive cue counts. Cue windows must have positive duration and lie on the input-video timeline. The target-language file must contain an ISO-639-1 two-letter code.

## Run

`scripts/dub.py` reads one JSON object from stdin and emits one JSON object to stdout.

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

All displayed fields are defaults. On success the output schema is:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

On failure it emits `{"ok":false,"error":"..."}` and exits nonzero. A failure response is not a completed delivery.

## Method and validation

1. Parse timing from `segments.srt` independently and pair source/reference text by cue index.
2. Synthesize the reference text, resample and downmix it to 48,000 Hz mono, then trim or pad each cue to its window. Each cue therefore starts exactly at the window start and has zero end drift.
3. Delay each cue by an integer number of 48 kHz samples on a silent program-length timeline. Normalize the mixed dialogue toward -23 LUFS, mux with `-c:v copy`, and measure BS.1770/EBU-R128 integrated loudness from the final MP4. If AAC encoding shifts it, apply a measured gain correction and remux.
4. Probe final media before writing the report. The report copies source and target scripts from the supplied SRTs, reads the target code exactly from its file, reports delivered durations and final-media loudness, and calculates drift as `placed_end_sec - window_end_sec`.

The entrypoint verifies the mandatory output paths, readable 48 kHz mono WAV/MP4 audio, source-timeline duration, and key copied-video metadata before returning success. If a runtime exposes its writable artifact mount as `/output`, the script creates `/outputs` as a compatibility link when necessary, while retaining the mandated `/outputs/...` delivery paths.
