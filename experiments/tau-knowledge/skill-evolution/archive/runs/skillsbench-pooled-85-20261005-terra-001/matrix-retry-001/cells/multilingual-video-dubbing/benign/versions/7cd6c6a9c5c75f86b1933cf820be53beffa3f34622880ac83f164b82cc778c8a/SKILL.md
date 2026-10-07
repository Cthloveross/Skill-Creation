---
name: reliable-multilingual-video-dubbing
description: Create a target-language 48 kHz mono dubbed WAV, a video-frame-preserving MP4, and a measurement-grounded JSON alignment report from an input MP4 and corresponding SRT files.
---

# Reliable multilingual video dubbing

Use this Skill when supplied with an MP4, placement-window SRT, source-script SRT, reference target-script SRT, and a target language code. It creates all requested artifacts at the required paths:

- `/outputs/tts_segments/seg_0.wav` (and `seg_N.wav` for subsequent cues),
- `/outputs/dubbed.mp4`, and
- `/outputs/report.json`.

The target SRT is the synthesis script. Its cue text is retained verbatim (apart from SRT line joining) in the report; do not independently translate the source script.

## Prerequisites

The runtime needs `ffmpeg` and `ffprobe`. A local speech backend is used in this order:

- `kokoro` only when explicitly requested and locally provisioned;
- `espeak-ng` or `espeak` for the default offline backend;
- an audible FFmpeg fallback if the selected local speech executable cannot synthesize the requested language.

For production human-quality speech, provision a local target-language neural backend and run with `"backend":"kokoro"`. The fallback exists only so an unavailable optional TTS installation cannot prevent delivery of required media artifacts.

## Run

All scripts accept one JSON object on standard input and emit one JSON object on standard output. From the package directory, use task-standard paths:

```bash
printf '%s' '{}' | python3 scripts/run_dubbing.py
```

An explicit invocation is:

```bash
printf '%s' '{"video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","backend":"espeak"}' | python3 scripts/run_dubbing.py
```

`run_dubbing.py` reads the target language code at runtime, validates all input files, synthesizes each reference cue, fits each WAV to its placement window, writes all output artifacts, and fails nonzero with JSON error output if it cannot produce a valid delivery.

## Pipeline

1. Parse the three SRT files. `segments.srt` controls timing; source and reference SRTs control corresponding report text.
2. Synthesize reference-target dialogue, resample/downmix it to 48 kHz mono, and apply `rate_adjust` plus trimming/padding so the delivered segment duration equals its window duration.
3. Normalize every delivered segment and the full delayed dialogue timeline toward -23 LUFS using FFmpeg `loudnorm`.
4. Delay each segment by exactly its window start, mux the resulting audio with `-c:v copy`, and encode only the replacement MP4 audio as 48 kHz mono AAC.
5. Probe the delivered files and measure integrated LUFS from the final MP4 audio. Report actual media durations and this measured loudness.

Each report entry is start-anchored at the placement window, has `duration_control: "rate_adjust"`, and reports drift as `placed_end_sec - window_end_sec` (zero for the fitted timeline). The implementation rejects empty, malformed, unmatched, or out-of-video placement inputs rather than issuing an ungrounded manifest.

## Script interfaces

- `scripts/run_dubbing.py`: end-to-end entrypoint. Optional JSON fields are `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language`, `output_dir`, `backend`, `voice`, and positive `speed`.
- `scripts/synthesize_speech.py`: JSON fields `text_srt`, `language`, `output_dir`; optional `backend`, `voice`, `speed`. Returns raw WAV paths and the actual backend.
- `scripts/build_dub.py`: JSON fields `video`, `segments_srt`, `source_srt`, `target_srt`, `source_language`, `target_language`, `output_dir`, and `raw_wavs`. Writes the final artifacts.
- `scripts/validate_delivery.py`: checks artifacts, report consistency, format, timing, visual-frame preservation, and delivered loudness. Run after delivery with `printf '%s' '{}' | python3 scripts/validate_delivery.py`.
