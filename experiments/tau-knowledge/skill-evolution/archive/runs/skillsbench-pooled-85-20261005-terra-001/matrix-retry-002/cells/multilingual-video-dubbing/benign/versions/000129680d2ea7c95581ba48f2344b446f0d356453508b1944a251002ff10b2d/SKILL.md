---
name: timed-multilingual-video-dubbing
description: Create target-language TTS segment WAVs, a 48 kHz mono dubbed MP4 that preserves an input video's visual stream, and an input-grounded timing and loudness report.
---

# Timed multilingual video dubbing

Use this Skill to replace dialogue on the exact windows declared by `segments.srt`. It uses target dialogue from `reference_target_text.srt`, not a new translation, preserves the input video stream with stream copy, and writes the requested artifacts at the required absolute paths.

## Runtime prerequisites

- Python 3 standard library;
- `ffmpeg` and `ffprobe` with `loudnorm` and `ebur128` filters;
- `espeak-ng` or `espeak`, with a voice for the target ISO 639-1 language code.

The three SRT files must contain the same nonzero number of cues. `segments.srt` supplies timing only; source and reference SRTs supply the report text and TTS text respectively. Every segment must have positive duration and end within the source video duration.

## Execute

The executor must run the entrypoint; documentation alone does not create media artifacts. From the package directory, pass one JSON object to the script:

```sh
printf '%s\n' '{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}' | python3 scripts/dub.py
```

The successful invocation creates:

- `/outputs/tts_segments/seg_0.wav` and one `seg_N.wav` for every additional timing cue. Each is readable PCM WAV at 48,000 Hz, mono, contains the corresponding reference-script utterance, and has its window duration.
- `/outputs/dubbed.mp4`, which retains the original visual stream and carries new 48,000 Hz mono AAC audio on the original timeline.
- `/outputs/report.json`, containing actual probed program durations, final-MP4 integrated loudness, input-derived text, and one alignment record per timing window.

The script emits JSON on stdout. Its stdin is a JSON object whose optional string fields are `input_video`, `segments_srt`, `source_srt`, `reference_target_srt`, `target_language_file`, `output_dir`, and `source_language`. Defaults are the public paths above. A success result is `{"ok":true,"video":"...","report":"...","measured_lufs":number}`. Invalid inputs, missing programs, failed TTS, or failed media validation produce `{"ok":false,"error":"..."}` and a nonzero exit status.

## Method

For each cue, the entrypoint synthesizes the exact reference-target cue using the requested language, resamples/downmixes it to 48 kHz mono, and either rate-adjusts overlong speech or pads shorter speech to the timing-window duration. The segment waveform is delayed by an exact sample count equal to its SRT start and mixed onto a silent program-length timeline. The complete timeline is normalized and measured after muxing. A bounded gain correction is made against the measured loudness of the final MP4, targeting -23 LUFS with an accepted delivery range of -25 to -21 LUFS.

`placed_start_sec` is the window start. Segment WAVs are rendered to the complete window duration, so `placed_end_sec` is the window end apart from sub-sample rounding. `drift_sec` is calculated as `placed_end_sec - window_end_sec`.

## Validate final delivery

After the creation command succeeds, validation may be run against the delivered files:

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}' | python3 scripts/validate_delivery.py
```

This checks final—not intermediate—MP4 stream format, duration/report consistency, report timing arithmetic, and BS.1770 integrated loudness. If creation fails, correct the reported prerequisite or input problem and rerun. Do not substitute source text for the reference target text, report unmeasured loudness, or leave artifacts in a staging directory instead of `/outputs`.
