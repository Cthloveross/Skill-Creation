---
name: broadcast-multilingual-video-dubbing
description: Create an aligned neural-TTS dubbing track from SRT timing windows and a reference target-language SRT, then deliver a 48 kHz mono MP4 with copied video, final-file BS.1770 loudness measurement, and an auditable JSON report. Use when ffmpeg/ffprobe and an installed target-language neural TTS runtime are available.
---

# Broadcast multilingual video dubbing

This Skill makes the reference target-language SRT the TTS source of truth. `segments.srt` supplies only placement windows. It anchors every synthesized utterance at the corresponding window start and rate-adjusts it to the window duration, so the reported end drift is zero apart from output-container timestamp precision.

## Prerequisites

* `ffmpeg` and `ffprobe` must be on `PATH` and ffmpeg must include `loudnorm` and `ebur128`.
* A target-language neural TTS runtime is required. `scripts/synthesize_kokoro.py` supports an installed Kokoro package plus `numpy` and `soundfile`; it never substitutes a tone, source audio, or machine translation if synthesis is unavailable.
* The source, target, and segment SRTs must each have the same number of nonempty cues in the intended order. Windows may overlap; they are mixed. Every window must have positive duration.
* The source language is not reliably recoverable from untagged subtitle text. Supply its known ISO 639-1 code explicitly to the build script. Read and pass the target ISO code verbatim (after trimming whitespace) from `target_language.txt`.

## Procedure

1. Read `target_language.txt`, trim it, and use that ISO code to configure a target-language TTS pipeline. Do not independently translate `source_text.srt`: synthesize `reference_target_text.srt`.
2. Generate raw speech WAVs. For Kokoro, run `synthesize_kokoro.py` with JSON on standard input. Select a voice appropriate to the target language; its defaults cover Kokoro's common language codes. If a requested code or voice is unsupported, stop and use another installed neural TTS engine rather than fabricating audio.
3. Call `build_dub.py`. It downmixes explicitly to mono, resamples to 48 kHz, changes speed using chained `atempo` filters, and `apad`/`atrim`s to exactly each window. It constructs a full timeline, applies two-pass `loudnorm` to the complete mix, muxes with `-c:v copy`, and measures LUFS from the delivered MP4 audio stream.
4. Retain `/outputs/tts_segments/seg_0.wav` (and the other generated segment WAVs), `/outputs/dubbed.mp4`, and `/outputs/report.json`. The segment WAVs are cut from the final normalized timeline, so their gain matches the delivered track.
5. Run `validate_delivery.py` before declaring success. Resolve any reported errors rather than editing report timing fields by hand.

Example (paths are runtime inputs; replace the source language and voice only with known values):

```bash
TARGET_LANGUAGE="$(tr -d '[:space:]' < /root/target_language.txt)"
printf '%s' '{"text_srt":"/root/reference_target_text.srt","language":"'"$TARGET_LANGUAGE"'","output_dir":"/root/raw_tts"}' \
  | python3 scripts/synthesize_kokoro.py
printf '%s' '{"video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","target_srt":"/root/reference_target_text.srt","raw_wav_dir":"/root/raw_tts","source_language":"en","target_language":"'"$TARGET_LANGUAGE"'","output_dir":"/outputs"}' \
  | python3 scripts/build_dub.py
printf '%s' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","segment_dir":"/outputs/tts_segments"}' \
  | python3 scripts/validate_delivery.py
```

## Script interfaces

### `synthesize_kokoro.py`

Reads one JSON object from stdin:

```json
{"text_srt":"PATH","language":"ISO-639-1","output_dir":"PATH","voice":"OPTIONAL_KOKORO_VOICE","speed":1.0}
```

It writes `raw_0.wav`, `raw_1.wav`, etc. in `output_dir` and emits `{"raw_wavs":[...],"language":...}` on stdout. `voice` defaults only for documented common Kokoro language mappings. Its source SRT parser preserves multi-line cue text as a space-separated utterance.

### `build_dub.py`

Reads one JSON object:

```json
{
  "video":"PATH", "segments_srt":"PATH", "source_srt":"PATH", "target_srt":"PATH",
  "raw_wav_dir":"PATH", "source_language":"ISO-639-1", "target_language":"ISO-639-1",
  "output_dir":"/outputs", "raw_wavs":["OPTIONAL/EXPLICIT/raw_0.wav"]
}
```

Use either ordered `raw_wavs` or `raw_wav_dir` containing `raw_0.wav` onward. It emits the paths, duration, and final MP4-integrated LUFS. The output report has all requested global fields and per-window fields. `tts_duration_sec` is the unmodified raw neural-TTS duration; `placed_start_sec`, `placed_end_sec`, and `drift_sec` describe the duration-controlled timeline actually delivered. The only duration-control value emitted is `rate_adjust`, which is one of the permitted values and preserves full speech content.

### `validate_delivery.py`

Reads `{"video":"PATH","report":"PATH","segment_dir":"PATH","lufs_tolerance":1.0}` and emits `{ "ok": bool, "errors": [...], "measured_lufs": number }`. It checks MP4 stream metadata, required report structure, anchor and drift consistency, existence of all segment WAVs, and remeasures delivered-file loudness with `ebur128`. It treats -23 LUFS within the supplied tolerance as compliant. If SpeechMOS/UTMOS is installed, independently score the final speech segments and investigate values below 3.5; MOS is a quality review signal, not a replacement for listening review.

The scripts intentionally fail on missing inputs, invalid SRT, unavailable binaries, failed ffmpeg operations, or unmeasurable loudness. They do not claim a successful deliverable in those cases.
