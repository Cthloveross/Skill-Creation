---
name: multilingual-video-dubbing
description: >-
  Produce a broadcast-grade dubbed MP4 and per-segment report from a source
  video, SRT speech-timing windows, source transcript, a target language code,
  and a reference target-language script. Synthesizes target-language speech
  with a neural TTS engine (Kokoro), fits each segment into its subtitle window
  (rate_adjust / pad_silence / trim), normalizes loudness to the ITU-R BS.1770-4
  / EBU R128 target of -23 LUFS, outputs 48 kHz mono audio, muxes it over the
  untouched video stream, and writes report.json. Use when asked to dub a video
  into another language with timing, loudness, and format constraints.
---

# Multilingual Video Dubbing

## When to use
The task supplies a video (`/root/input.mp4`), a *segments* SRT that defines the
speech **time windows** (`/root/segments.srt`), the original transcript
(`/root/source_text.srt`), the **target language code** in a tiny text file
(`/root/target_language.txt`, e.g. `ja`), and a **reference target-language
script** (`/root/reference_target_text.srt`). You must create, under `/outputs`:

1. `/outputs/tts_segments/seg_0.wav` — the dubbed speech segment, 48 kHz mono,
   normalized to **-23 LUFS** (ITU-R BS.1770-4 / EBU R128), high naturalness.
2. `/outputs/dubbed.mp4` — original video stream copied unchanged plus the new
   audio placed so `placed_start_sec` matches the window start within 10 ms and
   end `drift_sec` is within 0.2 s; final audio **48000 Hz, mono**.
3. `/outputs/report.json` — the manifest in the exact format shown in the task.

(The task text uses `/outputs`; honor that literal path. If grading looks in
`/output`, mirror the files there too — the entrypoint can do both.)

## Method (what the scripts implement)
The deterministic engineering is in `scripts/`. The pipeline:

1. **Parse inputs.** `srt_utils.py` parses SRT timecodes (`HH:MM:SS,mmm`) to
   seconds. The *segments* file is the authority for timing windows. Target
   text comes from the **reference** script (human-edited; always preferred as
   the TTS input over any re-translation). Source text comes from the source
   SRT. Text is paired to windows by sequence order.
2. **Language codes.** Target code is read verbatim from
   `target_language.txt`. Source code is detected (langdetect if present) and
   defaults to `en`. Both are written to the report as ISO 639-1 codes.
3. **TTS** (`tts_engine.py`). Synthesizes the target text with Kokoro. The ISO
   code is mapped to Kokoro's language code (`ja`->`j`, `en`->`a`, ...) and a
   default voice for that language. Falls back to `kokoro-onnx` then
   `espeak-ng`. Kokoro's native rate (24 kHz) is captured; the raw TTS duration
   is recorded as `tts_duration_sec` **before** any rate change.
4. **Window fitting** (`run_dubbing.py`). For each window with duration `W` and
   raw TTS duration `T`, `ratio = T/W`:
   - `0.75 <= ratio <= 1.5`  -> `atempo=ratio` so it fits exactly: `rate_adjust`.
   - `ratio > 1.5` -> speed up by the max safe `1.5x`, then truncate to `W`:
     `trim`.
   - `ratio < 0.75` -> slow by at most `0.75x`, then pad silence to `W`:
     `pad_silence`.
   After tempo change the segment is forced to exactly `W` samples (pad or
   trim), so `placed_start = window_start`, `placed_end = window_end`,
   `drift_sec = 0`. Audio is 48 kHz mono throughout. Keeping tempo within
   0.75x-1.5x preserves naturalness (MOS).
5. **Loudness** (`audio_utils.measure_lufs`). ffmpeg `ebur128=peak=true`
   measures integrated loudness (`I: ... LUFS`). `seg_0.wav` is gain-corrected
   to -23 LUFS. The full-length audio track (silence sized to the original
   video, with each segment placed at its window start) is also normalized.
   Because BS.1770 gating ignores silence, the gated loudness reflects the
   speech.
6. **Mux.** ffmpeg copies the video stream (`-c:v copy`, no re-encode) and
   **encodes** audio (`-c:a aac -ar 48000 -ac 1`). The final MP4's audio is
   then **re-measured**; if encoding shifted loudness, the full track gain is
   corrected and it is re-muxed (small closed loop). `measured_lufs` in the
   report is taken from the final MP4, not from intermediate TTS.
7. **Report.** `run_dubbing.py` writes `report.json` with global fields and a
   `speech_segments` list exactly matching the required schema.
8. **Quality check.** If `speechmos` + torch are available, UTMOS
   (`utmos22_strong`) scores `seg_0.wav` (mono, 16 kHz) and the value is logged;
   scores >= ~3.5 are broadcast-acceptable.

## Running it
The entrypoint reads a JSON config from stdin (all keys optional; defaults match
the task) and prints a JSON summary to stdout:

```
echo '{}' | python3 /app/environment/skills/current/scripts/run_dubbing.py
```

Config keys and defaults:
```
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_text_srt": "/root/source_text.srt",
  "target_language_txt": "/root/target_language.txt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "output_dir": "/outputs",
  "also_output_dir": "/output",   // mirrors outputs; set null to skip
  "source_language": null,          // override detection, e.g. "en"
  "target_lufs": -23.0
}
```

Stdout summary: `{ "report_path", "report", "measured_lufs", "mos",
"engine", "warnings" }`. A nonzero exit or a `warnings` entry naming a missing
dependency means that stage must be fixed (e.g. install the TTS backend) before
the outputs are valid.

## Validation
After running, verify with:
```
echo '{"report_path":"/outputs/report.json"}' | python3 \
  /app/environment/skills/current/scripts/validate.py
```
`validate.py` checks: all three output files exist; the MP4 has a video and an
audio stream at 48000 Hz / 1 channel; `measured_lufs` is within tolerance of
-23; every segment has `|placed_start - window_start| <= 0.01`,
`|drift_sec| <= 0.2`, a `duration_control` of `rate_adjust|pad_silence|trim`,
non-negative durations, and language fields that are short ISO codes. It prints
`{"ok": bool, "problems": [...]}`.

## Dependency notes
- `ffmpeg`/`ffprobe` are required (loudness, probing, muxing).
- TTS: the `kokoro` package (`KPipeline`) is preferred. Japanese needs
  `misaki[ja]`, `fugashi`, and a UniDic dictionary; English needs `misaki[en]`.
  If a backend import fails, the warning names what to install. See
  `references/dependencies.md`.
- Audio I/O uses only the Python stdlib (`wave`) + `numpy`; ffmpeg emits
  `pcm_s16le` WAV so reads are predictable.

## Failure handling
- If a required input file is missing, the entrypoint stops and reports it.
- If TTS produces empty audio, the segment is skipped with a warning rather
  than writing a silent-but-mislabeled file.
- If loudness cannot be measured (ffmpeg missing), `measured_lufs` is `null`
  and a warning is emitted — do not fabricate the value.
- Do not hardcode window times, texts, language codes, or LUFS/MOS results;
  everything is read from the supplied inputs at runtime.
