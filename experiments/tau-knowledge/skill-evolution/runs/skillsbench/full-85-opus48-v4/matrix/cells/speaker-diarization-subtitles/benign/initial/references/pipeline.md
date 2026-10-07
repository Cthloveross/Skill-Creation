# Diarization + Subtitle Pipeline Reference

## Stage contract

1. **Audio extraction** — `ffmpeg -vn -acodec pcm_s16le -ar 16000 -ac 1` to a WAV.
   16 kHz mono is what VAD / embedding / Whisper models expect. Measure duration
   with `ffprobe format=duration`.
2. **VAD** — determine speech regions in seconds. Authority for *where speech is*.
   Backends tried: silero-vad (torch.hub), webrtcvad, energy-based fallback.
   Never return one segment spanning the whole file unless the signal truly is a
   single contiguous voiced region.
3. **Speaker embeddings** — one ECAPA embedding per speech region >= 0.5 s
   (speechbrain `spkrec-ecapa-voxceleb`). L2-normalize for cosine distance.
4. **Clustering** — AgglomerativeClustering(metric=cosine, linkage=average,
   distance_threshold=`DIAR_THRESHOLD`, default 0.70). Unknown speaker count is
   estimated by the threshold. Short/unembedded regions inherit the label of the
   nearest embedded region in time (keep their VAD timing).
5. **Post-process** — merge adjacent same-speaker turns separated by <=0.4 s;
   drop turns shorter than `MIN_SEG_SEC` (default 0.20 s). Relabel by first
   appearance to contiguous indices.
6. **ASR** — faster-whisper then openai-whisper (`WHISPER_MODEL`, default
   `small`), word timestamps when available. Text is attached to diarization
   turns by word-midpoint containment (fallback: max temporal overlap). ASR
   times are never used to create RTTM turns.
7. **Write artifacts**
   - RTTM: `SPEAKER input 1 <start> <dur> <NA> <NA> spk00 <NA> <NA>` (6-decimal
     seconds; durations strictly positive).
   - ASS: `[Script Info]`, `[V4+ Styles]`, `[Events]`; Dialogue timestamps in
     `H:MM:SS.cc` centiseconds; Text prefixed `SPEAKER_00: ...`. Cue spans equal
     the diarization turn spans. Empty-text cues are skipped.
   - report.json: statistics derived from the written RTTM and measured audio.

## Label mapping

Cluster index `k` -> RTTM label `spk{k:02d}` and ASS label `SPEAKER_{k:02d}`.
The mapping is a single explicit table so RTTM, subtitles, and the report refer
to each speaker consistently.

## Report consistency rules (checked by validate.py)

- `num_speakers_pred` == count of distinct RTTM speaker labels.
- `total_speech_time_sec` == sum of RTTM durations (tolerance 0.5 s).
- `audio_duration_sec` == measured media duration (> 0).
- `commands_used`, `libraries_used`, `tools_used` reflect what actually ran.

## Environment knobs

- `DIAR_THRESHOLD` — cosine merge threshold. Raise if one voice fragments; lower
  if distinct voices merge.
- `WHISPER_MODEL` — tiny/base/small/medium/large.
- `MIN_SEG_SEC` — minimum final turn length.
- `HF_TOKEN` / `HUGGINGFACE_TOKEN` — enables the optional pyannote full pipeline.

## Failure handling

If no embedding model is available, VAD turns are emitted as a single speaker and
the limitation is recorded in `notes` (preferred over fabricating speakers). If
no ASR backend is available, RTTM/report are still written and `notes` records
that subtitles may be empty. Never substitute a single all-audio segment for
failed diarization.
