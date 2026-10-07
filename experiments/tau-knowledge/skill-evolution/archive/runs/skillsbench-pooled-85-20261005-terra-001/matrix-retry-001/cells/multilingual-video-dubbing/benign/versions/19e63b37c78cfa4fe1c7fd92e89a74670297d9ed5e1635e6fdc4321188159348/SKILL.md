---
name: resilient-multilingual-video-dubbing
description: Create a target-language dubbed MP4 from an input video, placement-window SRT, source SRT, target reference SRT, and target-language code. Produces 48 kHz mono segment WAVs, preserves original video frames, normalizes delivered audio near -23 LUFS, and writes a grounded report.json.
---

# Resilient multilingual video dubbing

Use this Skill when the task supplies an MP4, `segments.srt` timing windows, source dialogue SRT, reference target-language SRT, and a target-language code. The reference target SRT is the synthesis script: do not independently translate the source text and do not use the original-language audio as the dub.

`scripts/run_dubbing.py` is the end-to-end entrypoint. It creates every required output before reporting success:

* `OUTPUT_DIR/tts_segments/seg_0.wav` and one additional numbered WAV for each additional segment;
* `OUTPUT_DIR/dubbed.mp4`;
* `OUTPUT_DIR/report.json`.

The default supplied-task paths are `/root/input.mp4`, `/root/segments.srt`, `/root/source_text.srt`, `/root/reference_target_text.srt`, `/root/target_language.txt`, and `/outputs`.

## Runtime requirements

* `ffmpeg` and `ffprobe` must be available on `PATH`.
* For preferred neural synthesis, install Kokoro with its language dependencies plus `numpy` and `soundfile`. The package selects a Kokoro language pipeline and voice from the requested target language.
* If Kokoro is unavailable or cannot initialize, the synthesizer attempts an installed `espeak-ng` or `espeak` target-language voice. This keeps a constrained/offline runtime deliverable rather than silently omitting the required media. The returned JSON identifies the actual synthesis backend. For production human-quality delivery, install and use the neural Kokoro path.

All three SRT files must have corresponding ordered cues. Timing cues may have empty text, but source and reference target dialogue cues must contain text. Windows must be positive and within the input video duration.

## Run

Scripts read one JSON object from standard input and emit one JSON object to standard output. From the directory containing this package:

```bash
printf '%s' '{
  "video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "source_language": "en",
  "output_dir": "/outputs"
}' | python3 scripts/run_dubbing.py
```

A successful response contains `dubbed`, `report`, `segment_dir`, `measured_lufs`, and `synthesis_backend`. If it returns an `error`, do not write a fabricated report: resolve the stated missing tool, malformed input, or unsupported language, then rerun.

Validate delivered files, not merely report declarations:

```bash
printf '%s' '{
  "video": "/outputs/dubbed.mp4",
  "report": "/outputs/report.json",
  "segment_dir": "/outputs/tts_segments"
}' | python3 scripts/validate_delivery.py
```

## Method

1. Read the language code from `target_language.txt` and read dialogue verbatim from `reference_target_text.srt`.
2. Synthesize one target-language waveform per target cue. Kokoro is attempted first with the requested language pipeline; the fallback always synthesizes the reference text rather than source audio.
3. Explicitly convert each waveform to 48 kHz mono. Anchor it at its timing-window start and use tempo adjustment followed by exact trim/padding to the window duration. Each report entry therefore has `duration_control: "rate_adjust"`, zero nominal drift, and a `placed_start_sec` equal to its SRT window start.
4. Apply two-pass `loudnorm` targeting -23 LUFS to each delivered WAV. Build a complete silent timeline with delayed segments, normalize that final mix independently, and mux it with `-c:v copy`; video packets and visual frames are not re-encoded.
5. Measure integrated BS.1770 loudness from the delivered MP4 audio stream and use that actual measurement in `report.json`. Report text, timing windows, input duration, output duration, and drift are derived from supplied files and produced media.

## Script interfaces

### `scripts/run_dubbing.py`

Input fields: `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language` (default `en`), `output_dir` (default `/outputs`), optional `voice`, and optional positive `speed`.

It synthesizes reference target text, builds media deliverables, and returns output paths, target language, synthesis backend, and measured delivered-video LUFS.

### `scripts/synthesize_speech.py`

Input: `{"text_srt":"PATH","language":"ja","output_dir":"PATH","voice":"OPTIONAL","speed":1.0}`.

It writes `raw_0.wav`, `raw_1.wav`, and so on. Output includes `raw_wavs`, `language`, `voice`, and `backend`.

### `scripts/build_dub.py`

Input requires `video`, `segments_srt`, `source_srt`, `target_srt`, `source_language`, `target_language`, `output_dir`, and either `raw_wavs` or `raw_wav_dir`. It writes the segment WAVs, MP4, and report and returns their paths with a final MP4 loudness measurement.

### `scripts/validate_delivery.py`

Input: `{"video":"PATH","report":"PATH","segment_dir":"PATH","lufs_tolerance":1.0}`. It verifies output existence, report structure, 48 kHz mono streams, duration/timing constraints, and measured final-video loudness.
