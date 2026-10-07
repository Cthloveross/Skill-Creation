---
name: multilingual-video-dubbing
version: 1.1.0
description: Build a target-language dialogue dub from an MP4 plus aligned SRT files, generate required 48 kHz mono WAV/MP4 artifacts, measure delivered loudness, and write an auditable report. Use when segments.srt defines required dialogue windows and reference_target_text.srt supplies approved target wording.
---

# Multilingual Video Dubbing

Run the end-to-end entrypoint from the task work directory:

```sh
python3 scripts/dub.py <<'JSON'
{}
JSON
```

The script reads the supplied task paths by default and creates these exact deliverables:

* `/outputs/tts_segments/seg_0.wav` (plus one WAV for each later window),
* `/outputs/dubbed.mp4`, and
* `/outputs/report.json`.

It emits one JSON result to stdout on success. It emits a JSON error to stderr and exits nonzero on an unrecoverable media/input error.

## Input schema

The stdin object may override defaults:

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "auto",
  "tts_command": "production-tts --language {lang} --text {text} --output {output}"
}
```

`tts_command` is optional. It is a command template executed without a shell; `{lang}`, `{text}`, and `{output}` are substituted as one command argument each. It must write a decodable audio file at `{output}`. Supply the installed production/neural target-language TTS command when speech naturalness is a delivery criterion. Without it, the pipeline tries installed `espeak-ng` or `espeak` as an offline operational fallback. A last-resort synthetic voiced signal is only to keep media assembly diagnosable when no TTS executable exists; it is not a substitute for human-quality target-language synthesis and must not be editorially accepted.

## Method

1. Parse all SRT files at runtime, require equal segment/source/target entry counts, and use `segments.srt` only for timing. Use `reference_target_text.srt` verbatim for TTS input and report target text.
2. Read and validate the target language code from `target_language.txt`. Synthesize each target segment, explicitly resample/downmix it to 48 kHz mono, and retain its pre-fitting duration.
3. Anchor each clip exactly at its SRT window start. Short clips are silence-padded; long clips are rate-adjusted. Every fitted segment is sample-trimmed to its window, producing negligible end drift. Each emitted segment WAV is BS.1770-measured and gain-adjusted toward -23 LUFS.
4. Assemble decoded WAV inputs into a sample-positioned full-video timeline, normalize that final mix, and mux it with `-c:v copy` so the original visual stream is not re-encoded. The dubbed AAC stream is explicitly 48 kHz mono.
5. Measure `dubbed.mp4` after encoding/muxing using ffmpeg `ebur128`; apply a correction/remux pass if needed. Validate the delivered streams and timing before writing `report.json`.

The report records final-file loudness, actual input/output durations, source and target language codes, and one grounded entry per timing window. `drift_sec` is calculated as `placed_end_sec - window_end_sec`; `duration_control` is always `rate_adjust`, `pad_silence`, or `trim`.

## Required runtime capabilities

`ffmpeg` and `ffprobe` must be available and support PCM WAV, AAC, `ebur128`, `atempo`, and video stream copy. The script otherwise uses only Python standard-library modules. Review pronunciation, target-language fidelity, and naturalness before release: objective timing, codec, and loudness checks cannot establish perceived human-quality speech.
