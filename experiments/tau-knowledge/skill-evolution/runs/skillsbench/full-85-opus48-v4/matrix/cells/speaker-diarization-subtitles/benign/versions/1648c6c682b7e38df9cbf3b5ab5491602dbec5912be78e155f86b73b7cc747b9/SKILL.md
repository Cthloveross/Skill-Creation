---
name: speaker-diarization-subtitles
description: >-
  Build a speaker-diarization + transcription pipeline for a video/audio file and
  emit three mutually consistent artifacts: an RTTM diarization file, an ASS
  subtitle file whose cues carry SPEAKER_XX speaker-label prefixes, and a
  report.json summarizing the pipeline. Use this when a task asks to "perform
  diarization" on a media file and produce RTTM, subtitle (.ass), and a JSON
  report. The pipeline discovers installed tools at runtime (ffmpeg, a VAD, a
  speaker-embedding model, clustering, and an ASR model), falls back gracefully,
  and derives all report statistics from the artifacts it actually produced.
---

# Speaker Diarization + Subtitle Generation

## What this task requires

Given an input media file (default `/root/input.mp4`), produce exactly three files:

1. `/root/diarization.rttm` — one `SPEAKER` turn per line, ten whitespace-separated
   fields: `SPEAKER <file-id> 1 <start> <duration> <NA> <NA> <spk-label> <NA> <NA>`.
   Start >= 0, duration strictly > 0. The example uses labels like `spk00`.
2. `/root/subtitles.ass` — an ASS file with `[Script Info]`, `[V4+ Styles]`, and
   `[Events]` sections. Each `Dialogue:` line uses **centisecond** timestamps
   (`H:MM:SS.cc`) and text prefixed with the speaker label, e.g.
   `SPEAKER_00: Hello there.` Subtitle time spans follow the diarization segment
   boundaries, not raw ASR word boundaries.
3. `/root/report.json` — keys: `num_speakers_pred`, `total_speech_time_sec`,
   `audio_duration_sec`, `steps_completed`, `commands_used`, `libraries_used`,
   `tools_used` (object), `notes`. Every statistic MUST be derived from the
   RTTM/audio actually produced, never hardcoded.

Consistency rule: `num_speakers_pred` == number of distinct speaker labels in the
RTTM; `total_speech_time_sec` == sum of RTTM durations; `audio_duration_sec` ==
measured media duration; subtitle cue timings == RTTM segment timings.

## Method (assumptions and ordering)

The pipeline is: extract 16 kHz mono WAV → detect speech (VAD) → extract speaker
embeddings on speech regions → cluster embeddings into speakers → merge/clean
segments → transcribe with ASR → assign ASR text to diarization segments by
temporal overlap → write RTTM, ASS, and report.

Key design points taken from the domain background:
- VAD (or a diarization model) is the authority for *where speech is*. ASR
  segment/word times are used only to attach text, never to invent RTTM turns.
- Short speech regions give unreliable standalone embeddings; keep their VAD
  timing but assign their speaker identity from the nearest embedded segment.
- Clustering uses cosine distance with average linkage; the merge threshold is a
  tunable parameter (`DIAR_THRESHOLD`, default 0.70) — pick from the embedding
  distribution, do not treat one score as ground truth.
- Never use an "all-duration single segment" fallback. A one-speaker result is
  valid only when the audio supports it.
- ASS uses two-decimal centisecond times; do not reuse SRT millisecond precision.

Component availability is discovered at runtime. The script tries, in order:
pyannote.audio full pipeline (optional, often needs an HF token) → custom
VAD+embedding+clustering using silero-vad / webrtcvad + speechbrain ECAPA +
scikit-learn. ASR tries faster-whisper then openai-whisper, falling back to
segment-level text if word timestamps are unavailable. Whatever path succeeds is
recorded in `tools_used`/`libraries_used`.

## How to run (executor)

1. Inspect the environment first:
   `python3 scripts/run_pipeline.py --probe` prints a JSON report of which
   backends import successfully. Use it to understand what will be used.
2. Run the end-to-end pipeline (reads a JSON config on stdin; all keys optional,
   defaults target the task paths):

   ```bash
   echo '{"input":"/root/input.mp4","out_rttm":"/root/diarization.rttm","out_ass":"/root/subtitles.ass","out_report":"/root/report.json"}' \
     | python3 scripts/run_pipeline.py
   ```

   With no stdin it uses the defaults above. It writes the three files and prints
   a JSON status object to stdout (`{"ok":true,"num_speakers":...,...}`).
3. Validate the produced artifacts (does not regenerate them):

   ```bash
   echo '{"rttm":"/root/diarization.rttm","ass":"/root/subtitles.ass","report":"/root/report.json"}' \
     | python3 scripts/validate.py
   ```

   `validate.py` checks RTTM field count and positive durations, ASS section +
   `SPEAKER_` prefixes + centisecond timestamp format, report schema, and the
   cross-artifact consistency rules. Fix any reported failure and rerun the
   pipeline. Output is JSON `{"ok":bool,"errors":[...],"warnings":[...]}`.

If a stage is impossible in the environment (e.g. no ASR model and no network),
the pipeline still emits diarization + RTTM and an ASS file with empty-text cues
is avoided; the `notes` field records the limitation explicitly rather than
fabricating output. Diarization without a usable embedding model falls back to
energy/pause-based turn detection but still never collapses to one all-audio turn
unless the audio genuinely contains a single contiguous speaker region.

## Tuning / troubleshooting

- Over-fragmentation (one person split into many `spk`): raise `DIAR_THRESHOLD`
  (e.g. `DIAR_THRESHOLD=0.85`). Merger of distinct voices: lower it (e.g. 0.6).
  Set via environment: `DIAR_THRESHOLD=0.6 python3 scripts/run_pipeline.py`.
- `WHISPER_MODEL` (default `small`) selects the ASR size; use `base`/`tiny` for
  speed on CPU, `medium` for accuracy.
- `MIN_SEG_SEC` (default 0.20) drops micro-segments from the final RTTM.
- Always re-run `validate.py` after any change and confirm the three files parse.

See `references/pipeline.md` for the detailed stage contract and format rules.
