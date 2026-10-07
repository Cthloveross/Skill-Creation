---
name: timed-multilingual-video-dubbing
description: Generate target-reference-script speech, a 48 kHz mono dubbed MP4 with preserved input visuals, and a timing/loudness delivery report from video and SRT inputs.
---

# Timed multilingual video dubbing

Use this Skill for an input video plus: a timing-only `segments.srt`, source transcript SRT, approved target-language reference-script SRT, and target language-code file. The approved reference target text is the TTS input; do not independently translate source text.

The entrypoint creates the required artifacts directly under `/outputs` by default:

- `/outputs/tts_segments/seg_0.wav` (and one WAV per later timing cue)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Runtime prerequisites

Python 3, `ffmpeg`, and `ffprobe` must be installed. `espeak-ng` or `espeak` is used when present for offline synthesis. The script has a deterministic audible fallback only when no local speech engine can render; a language-capable neural/local TTS engine should be installed for production-quality speech.

The timing, source, and reference SRTs must have the same positive number of cues. Cue windows must fit within the input video. The output root must be writable; retain `/outputs` when the task requires its mandated absolute delivery paths.

## Run

`scripts/dub.py` receives exactly one JSON object on stdin and emits one JSON object on stdout.

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

All fields shown have the displayed defaults. Success output has this schema:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

A failure emits `{"ok":false,"error":"..."}` and exits nonzero; it is not a completed delivery.

## Processing method

1. Parse timing independently from `segments.srt`; pair source and approved reference text by cue index.
2. Synthesize each reference cue, resample/downmix to 48,000 Hz mono PCM, and explicitly trim or pad it to its timing window. Speech is anchored at the exact window start; the selected `duration_control` is reported.
3. Place each cue using sample-based FFmpeg delay on a silent timeline matching the source video duration. Normalize the program toward -23 LUFS, mux it with `-c:v copy`, then measure the final encoded MP4 with `ebur128` and apply a final gain correction if required.
4. Probe delivered media and write `report.json`. The report uses source language `en`, copies the target language code exactly from its file, records actual container durations, reports final-MP4 integrated loudness, and computes drift as `placed_end_sec - window_end_sec`.

Before reporting success, the entrypoint verifies that all mandatory artifacts exist, the WAV and MP4 audio are 48 kHz mono, the output duration remains on the original timeline, and copied video metadata is preserved.
