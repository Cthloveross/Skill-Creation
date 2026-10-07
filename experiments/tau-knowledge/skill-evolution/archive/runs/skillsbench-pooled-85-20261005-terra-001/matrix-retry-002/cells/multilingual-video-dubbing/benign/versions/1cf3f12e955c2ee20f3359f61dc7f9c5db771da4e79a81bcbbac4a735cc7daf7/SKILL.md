---
name: timed-multilingual-video-dubbing
description: Create reference-script target-language dialogue WAVs, a 48 kHz mono dubbed MP4 with its original video stream preserved, and an input-grounded timing and loudness report.
---

# Timed multilingual video dubbing

Use this Skill when the runtime supplies a source video, a timing-only `segments.srt`, source and approved target-script SRT files, and a two-letter target-language code. The target-reference SRT is the speech input; do not independently translate the source SRT. `segments.srt` alone defines dialogue placement windows.

## Runtime prerequisites

Python 3, `ffmpeg`, and `ffprobe` are required. `espeak-ng` (or `espeak`) is used when installed to synthesize the requested language. The script has an audible waveform fallback so absence of that optional local TTS executable does not prevent required delivery artifacts, but a supported local voice is preferred for production quality.

The three SRT files must each have the same positive cue count. Every timing cue must be positive and must end within the input-video duration.

## Execute

The entrypoint reads exactly one JSON object from stdin and emits one JSON object on stdout. Run it from the package directory:

```sh
printf '%s\n' '{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}' | python3 scripts/dub.py
```

All fields are optional strings. Their defaults are the public task paths, including the required `output_dir` of `/outputs`. A successful run writes:

- `/outputs/tts_segments/seg_0.wav`, plus `seg_N.wav` for subsequent cues. Each is a readable 48,000 Hz mono PCM WAV rendered to its timing window.
- `/outputs/dubbed.mp4`, preserving the input video stream with `-c:v copy` and containing newly encoded 48,000 Hz mono AAC dialogue on the original timeline.
- `/outputs/report.json`, with global properties and exactly one report entry for every timing cue.

Success stdout schema:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

Failure stdout has schema `{"ok":false,"error":"explanation"}` and exits nonzero. Do not treat a failure JSON as a delivery: inspect it, correct the missing prerequisite or invalid input, and rerun.

## Method

For each matching cue, synthesize the matching reference-target text, convert it explicitly to 48 kHz mono, then control duration. Overlong speech uses `rate_adjust`; shorter speech uses `pad_silence`. Therefore each rendered segment ends at the cue end and has zero end drift. The mix delays every segment by an integer count of 48 kHz samples equal to its window start, so placed starts are sample-aligned to the requested timeline.

The complete program audio is normalized toward -23 LUFS, muxed with a copied visual stream, then measured from the final MP4 using ffmpeg's BS.1770-compatible `ebur128` filter. A bounded final gain correction is applied to the program audio if the encoded MP4 is outside -25 to -21 LUFS. The report is written only after the final media passes stream and loudness checks. `drift_sec` is always calculated as `placed_end_sec - window_end_sec`.

## Validate delivery

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}' | python3 scripts/validate_delivery.py
```

The validator checks required report fields and timing arithmetic, 48 kHz mono final media, finite final integrated loudness near -23 LUFS, and media/report duration consistency. It validates final media rather than intermediate WAV files.
