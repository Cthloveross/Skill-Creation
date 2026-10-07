---
name: multilingual-video-dubbing
version: 1.0.0
description: Create a target-language, window-aligned dialogue dub from an MP4 and SRT files, normalize final audio to EBU R128 / ITU-R BS.1770-4 practice, mux it with copied video, and write an auditable JSON report. Use when target dialogue is supplied as an SRT reference script and exact subtitle windows define placement.
---

# Multilingual Video Dubbing

`script/dub.py` is an executable end-to-end pipeline. It reads the actual supplied files at runtime; it never embeds a transcript, language, time window, or expected result.

## Prerequisites

* `ffmpeg` and `ffprobe` must be installed and able to decode the input video and encode AAC.
* A target-language TTS engine must be available. Pass it with `tts_command`, using `{text}`, `{output}`, and `{lang}` placeholders. The command must create a WAV file at `{output}`. It is run without a shell.
* If no command is supplied, the script tries `espeak-ng` and then `espeak`. This is an availability fallback, not a claim that an eSpeak voice meets a human-quality requirement. For delivery, use an installed neural/production voice selected for the requested target language and evaluate it by listening (and, where available, UTMOS) before accepting the artifact.

The script relies only on Python's standard library plus those executables. It uses the reference target SRT as TTS content. It uses the segments SRT exclusively as placement windows.

## Input JSON

Supply JSON on stdin. All paths below have defaults matching the stated task. `source_language` may be explicitly supplied as an ISO 639-1 code; `auto` uses a conservative Unicode heuristic because SRT has no mandatory language metadata.

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "auto",
  "tts_command": "my-neural-tts --lang {lang} --text {text} --output {output}"
}
```

Run it as:

```sh
python3 scripts/dub.py <<'JSON'
{"tts_command":"my-neural-tts --lang {lang} --text {text} --output {output}"}
JSON
```

The command emits one JSON object to stdout. On success it names the report and media artifacts. On failure it emits `{"ok":false,"error":"..."}` to stderr and exits nonzero; no report should be treated as valid.

## Processing method

1. Parse SRT timestamps exactly to milliseconds. Require at least one nonempty, positive segment and matching source/target entries by ordinal position. The target code is read and validated from `target_language.txt` rather than inferred.
2. Synthesize each reference-target entry. The raw synthesis duration is saved for the report. Convert every result explicitly to 48 kHz mono.
3. Keep every clip at its window start. Short clips receive silence padding; longer clips use `atempo` rate adjustment. The resulting clip is sample-trimmed to the window length, so `placed_end - window_end` is at most one 48 kHz sample. Each segment WAV, including required `tts_segments/seg_0.wav`, is independently normalized using measured BS.1770 integrated loudness.
4. Delay the fitted clips by sample counts and mix them into a full-length 48 kHz mono timeline. The final timeline is measured with ffmpeg `ebur128`, gain-corrected toward -23 LUFS, muxed with `-c:v copy`, and remeasured from the delivered MP4 audio. A final correction/remux pass accounts for encoder changes.
5. Validate decoded output stream existence, 48 kHz mono properties, final LUFS measurability, nonnegative ordered windows, placement tolerance, and drift tolerance. The report's `measured_lufs` is measured from `dubbed.mp4`, not an intermediate WAV.

The final video stream is copied without visual re-encoding. Original audio is replaced by the dubbed timeline. The pipeline rejects unmeasurably silent output because such output cannot satisfy a meaningful BS.1770 speech-delivery requirement.

## Output and validation

Successful execution creates:

* `/outputs/tts_segments/seg_0.wav` (and one WAV per remaining segment), 48 kHz mono;
* `/outputs/dubbed.mp4`, copied original video plus AAC 48 kHz mono dub;
* `/outputs/report.json` with exactly the requested global fields and per-segment fields.

`duration_control` is always one of `rate_adjust`, `pad_silence`, or `trim`. This implementation uses `pad_silence` for shorter raw speech and `rate_adjust` for equal/longer speech; it avoids content-destroying trimming. `tts_duration_sec` is the pre-duration-control synthesized duration, while placement fields describe fitted audio.

Inspect the returned `validation` object and preserve the generated report. For editorial acceptance, additionally listen around each subtitle boundary and assess pronunciation/naturalness with a language-appropriate reviewer; timing and LUFS checks cannot prove linguistic correctness or human perceived quality.
