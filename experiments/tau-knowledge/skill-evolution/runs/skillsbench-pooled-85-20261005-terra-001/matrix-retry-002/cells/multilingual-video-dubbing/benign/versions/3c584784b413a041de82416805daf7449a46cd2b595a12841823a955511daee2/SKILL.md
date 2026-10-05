---
name: timed-multilingual-video-dubbing
description: Generate target-language reference-script dialogue for SRT timing windows, preserve the source video stream, and deliver 48 kHz mono WAV/MP4 dubbing artifacts with an auditable JSON timing and loudness report.
---

# Timed multilingual video dubbing

Use this Skill for an input video, a timing-window SRT, a source-text SRT, an approved target-language reference-text SRT, and a target language code file. It writes the task deliverables directly at:

- `/outputs/tts_segments/seg_0.wav` (plus `seg_N.wav` for additional cues)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

The target reference SRT is the TTS source. Do not replace it with a new translation. Timing is taken only from `segments.srt`; source and target text are paired by cue index.

## Prerequisites

Python 3, `ffmpeg`, and `ffprobe` must be available. If `espeak-ng` or `espeak` is installed, the script uses it as the local offline TTS engine. A deterministic voiced local fallback keeps the media pipeline operational if that engine is unavailable or cannot synthesize the requested language. A high-quality local neural TTS installation may be substituted by replacing `synthesize` while retaining its WAV contract.

All three SRTs must contain the same nonzero number of cues. Windows need positive duration and must be inside the source video. `target_language.txt` must contain a two-letter language code.

## Run

`scripts/dub.py` reads one JSON object from stdin and emits exactly one JSON status object to stdout. All paths default to the supplied task paths, so `{}` is valid.

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

Success output schema:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

On invalid input or an unavailable required media tool it emits `{"ok":false,"error":"..."}` and exits nonzero.

## Processing and validation

1. Parse SRT timing and text at runtime and synthesize each approved target cue. Each delivered cue is explicitly converted to a readable 48,000 Hz mono PCM WAV. Short cues are silence-padded and long cues are trimmed to their window; the report records the pre-fit TTS duration and the applicable `pad_silence` or `trim` control.
2. Build a mono timeline by delaying each cue by its exact integer 48 kHz sample offset. Every placed start equals the corresponding window start and each placed end equals the window end, so reported drift (`placed_end_sec - window_end_sec`) is zero.
3. Normalize the complete dialogue timeline with ffmpeg `loudnorm`, mux it with `-c:v copy` so the original video stream is retained, and encode one 48 kHz mono AAC track. Measure integrated BS.1770 loudness from the final MP4 with `ebur128`; apply a gain correction and remux when needed.
4. Probe the final MP4 before reporting. `report.json` contains the target language read verbatim from its input file, source and target text from their respective SRTs, actual container durations, actual final-media loudness, and the complete per-window alignment manifest.

The script creates `/outputs` and `/outputs/tts_segments` before work begins and verifies that required files exist and decode before returning success.
