---
name: multilingual-video-dubbing
version: 1.0.0
description: Create an aligned, 48 kHz mono multilingual dub from an MP4, timing SRT, source/reference SRT scripts, and a target ISO language code. Use when the reference target script is the authoritative text and a report with per-window alignment and final LUFS is required.
---

# Multilingual video dubbing

This Skill synthesizes the **reference target-language SRT text**, fits each utterance to the corresponding `segments.srt` window, replaces the input audio while stream-copying the input video, and writes an auditable report. It uses Microsoft Edge Neural TTS through `edge-tts` when available (and can install that small Python package at runtime if internet access is permitted). This is preferred to a local formant synthesizer for natural speech.

## Input and output contract

Run `scripts/dub.py` with a JSON object on stdin. All paths may be overridden; defaults are the paths in this task.

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en"
}
```

`source_language` is optional. If omitted, the entrypoint makes a conservative script-based guess (`en` for Latin-script source text); provide it explicitly when that is not correct. The target code is always read from `target_language_file`, normalized to lowercase, and used both in the report and to select the voice.

The program emits one JSON result object to stdout. On success it creates:

- `OUTPUT_DIR/tts_segments/seg_N.wav` for every segment (including required `seg_0.wav`), 48 kHz mono and loudness-normalized;
- `OUTPUT_DIR/dubbed.mp4`, with the original first video stream copied and new AAC mono audio;
- `OUTPUT_DIR/report.json` matching the requested schema.

Example:

```sh
python3 /app/environment/skills/current/scripts/dub.py <<'JSON'
{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}
JSON
```

## Method and safeguards

1. Parse SRT timecodes exactly to milliseconds. Segment windows are authoritative; source and reference texts are paired in SRT order and are never machine-translated.
2. Synthesize each target entry with a language-specific neural voice. Supported target codes are `ar`, `de`, `en`, `es`, `fr`, `hi`, `it`, `ja`, `ko`, `pt`, `ru`, and `zh`. The program stops with a clear error for another code rather than silently using the wrong-language voice.
3. Decode synthesized media with FFmpeg, convert explicitly to 48 kHz mono PCM, and record this unadjusted decoded duration as `tts_duration_sec`.
4. Apply FFmpeg `atempo` stages to fit every synthesis to its speech window. This preserves the complete text and gives `duration_control: "rate_adjust"`; the final sample is trimmed to the window boundary to remove sub-sample encoder/resampler residue. The placement start is the SRT window start and the declared drift is calculated as `placed_end_sec - window_end_sec`.
5. Normalize individual segment WAVs and the complete timeline to approximately -23 LUFS. LUFS is measured from the final delivered audio with FFmpeg `ebur128`; a corrective gain pass is made when needed. The reported value is the measurement of the audio muxed into the finished MP4, not an intermediate synthesis measurement.
6. Build a silent timeline equal to the measured input duration, delay each segment by its window start, mix it, and mux it with `-c:v copy`, `-c:a aac`, `-ar 48000`, and `-ac 1`.
7. Validate that the final file has video and mono 48 kHz audio, that each rendered segment duration is within 10 ms of its SRT window, and that the copied video codec matches the source. The script fails instead of emitting a misleading report when a prerequisite or validation fails.

The rate adjustment can sound less natural for extreme text/window mismatches. The report preserves the original TTS duration so an operator can identify such cases. This Skill does not claim a MOS score because that requires a separately installed MOS model and listening-quality evaluation.

## Runtime requirements and failure handling

Requires `python3`, FFmpeg/FFprobe with `ebur128`, and network access to Edge TTS on first synthesis. `edge-tts` is installed with `python -m pip install edge-tts` only when not already importable. If package installation, the speech service, FFmpeg, a required file, an SRT pairing, or final validation fails, stdout remains a JSON error object and the process exits nonzero. Do not substitute an unrelated local voice: rerun in an environment with the declared neural TTS access.
