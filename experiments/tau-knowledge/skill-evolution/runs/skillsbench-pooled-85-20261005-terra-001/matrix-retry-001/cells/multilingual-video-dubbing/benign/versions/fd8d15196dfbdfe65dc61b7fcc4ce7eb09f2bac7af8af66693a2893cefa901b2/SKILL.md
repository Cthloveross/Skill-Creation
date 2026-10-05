---
name: reliable-multilingual-video-dubbing
description: Create target-language, 48 kHz mono dubbing audio, a frame-preserving MP4, and a measurement-grounded JSON alignment report from an input video and corresponding SRT files.
---

# Reliable multilingual video dubbing

Use this Skill when an MP4, placement-window SRT, source transcript SRT, reference target-script SRT, and target-language code are supplied. It creates the required delivery paths:

- `/outputs/tts_segments/seg_0.wav` (and `seg_N.wav` for every further placement cue),
- `/outputs/dubbed.mp4`, and
- `/outputs/report.json`.

The reference target SRT is the speech input and report target text. Do not independently translate or substitute its dialogue.

## Runtime prerequisites

The runtime must provide `ffmpeg` and `ffprobe`. For offline speech rendering, the default backend tries `espeak-ng` and then `espeak`. A local neural renderer can be selected by passing `backend: "piper"` with a locally available Piper executable and `voice` set to its model path. For production-quality delivery, provision a target-language neural voice locally and use Piper; no network download is attempted.

If neither selected speech renderer produces audio, the script creates an audible FFmpeg fallback rather than silently dropping a required cue. This fallback protects structural delivery only and is not a replacement for a target-language neural voice.

## Run

Every script receives one JSON object on standard input and writes one JSON object on standard output. From the package directory, run the supplied task inputs as follows:

```bash
printf '%s' '{}' | python3 scripts/run_dubbing.py
```

An explicit invocation is:

```bash
printf '%s' '{"video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","backend":"espeak"}' | python3 scripts/run_dubbing.py
```

The entrypoint preflights all input files, creates the output directories, synthesizes one raw cue for each reference-target SRT entry, fits each cue to its matching placement window, produces delivery WAVs, creates timeline-aligned final audio, muxes that audio while copying the source video stream, measures the final MP4 audio, and writes the report from the delivered files.

## Alignment, media, and report rules

- `segments.srt` supplies placement windows only. The source and reference target SRTs supply text and must have exactly the same cue count as the window SRT.
- Every delivered cue is start-anchored to its window. It is tempo-adjusted and padded/trimmed to the exact window duration, so `placed_end_sec` equals `window_end_sec` and drift is zero.
- WAV delivery and MP4 audio are explicitly PCM/AAC 48,000 Hz mono.
- Each delivery WAV and the complete final audio timeline are normalized near the -23 LUFS BS.1770 target. The report's `measured_lufs` is measured from the final delivered MP4 audio, not from an intermediate file.
- The MP4 uses `-c:v copy`; no video frames are decoded/re-encoded by the muxing operation.
- Report duration values are probed from the input and delivered containers. `drift_sec` is computed as `placed_end_sec - window_end_sec`.

Malformed or empty SRTs, mismatched cue counts, missing media, and windows beyond the source visual duration are explicit errors. The entrypoint verifies that the three required files exist before reporting success.

## Script interfaces

- `scripts/run_dubbing.py`: End-to-end entrypoint. Optional JSON fields are `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language`, `output_dir`, `backend`, `voice`, and positive `speed`.
- `scripts/synthesize_speech.py`: JSON fields `text_srt`, `language`, `output_dir`; optional `backend`, `voice`, and positive `speed`. Returns raw WAV paths.
- `scripts/build_dub.py`: JSON fields `video`, `segments_srt`, `source_srt`, `target_srt`, `source_language`, `target_language`, `output_dir`, and `raw_wavs`. Produces all delivery media and the report.
- `scripts/validate_delivery.py`: Optional `output_dir` and `input_video`; returns `{ "ok": bool, "errors": [...], "measured_lufs": number|null }`.

After a successful delivery, validate the actual artifacts with:

```bash
printf '%s' '{}' | python3 scripts/validate_delivery.py
```
