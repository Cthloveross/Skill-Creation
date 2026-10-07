---
name: evidence-based-diarized-ass-subtitles
description: Produce RTTM diarization, speaker-prefixed ASS subtitles, and a provenance report from a video when the runtime must be inspected and available ASR/diarization components selected at execution time. Use for video/audio diarization tasks requiring internally consistent temporal artifacts.
---

# Evidence-based diarization and ASS subtitle generation

This Skill separates environment discovery, acoustic processing, alignment, and deterministic artifact writing. It deliberately does **not** treat an ASR segment as a speaker turn and does not invent a whole-recording speaker turn when diarization fails.

## Packaged scripts

All scripts use JSON on stdin and JSON on stdout and require only the Python standard library.

* `scripts/inspect_runtime.py` inspects executable availability, selected importable packages, relevant cache roots, and media metadata. Input: `{"input":"/root/input.mp4"}`. Its output is evidence for component selection; it does not claim that a cached directory is a usable model.
* `scripts/write_artifacts.py` validates normalized diarization turns and writes RTTM, ASS, and report artifacts. Its input schema is described below. It defaults to `/root` output paths, thus writing `/root/diarization.rttm`, `/root/subtitles.ass`, and `/root/report.json`.

## Execution procedure

1. **Inspect before selecting a pipeline.** Run:
   ```sh
   python3 scripts/inspect_runtime.py <<'JSON'
   {"input":"/root/input.mp4"}
   JSON
   ```
   Inspect the emitted command/package availability, ffprobe duration, package documentation, model caches, and network/model-access constraints. Select only components that are genuinely usable in this runtime. Record the exact commands, packages, models, and meaningful parameters actually used.

2. **Extract one canonical audio source.** Use the selected decoder to make a lossless, mono, 16 kHz WAV, for example with ffmpeg using `-vn`, PCM 16-bit audio, `-ar 16000`, and `-ac 1`. All VAD, speaker processing, and ASR must use this same source/time base. Obtain source duration with ffprobe or WAV metadata.

3. **Derive speaker turns from acoustic evidence.** Use an installed diarization pipeline, or an evidence-based composition of VAD, speaker embeddings, and clustering. Preserve VAD-derived speech bounds; do not copy ASR segment bounds into RTTM. Choose clustering count/thresholds based on the recording and selected component documentation. Keep the raw tool speaker identity with each final turn. Merge or resegment only when supported by acoustic/speaker evidence, and reject nonpositive turns.

   A failed diarizer is not permission to output one speaker covering the media. If no viable diarization component can be made operational, report that operational failure to the caller rather than fabricating turns or claiming a successful diarization step. A genuine recording with no detected speech may validly yield an empty turn list.

4. **Transcribe and align text.** Prefer ASR word timing. Assign each word to the final diarization turn with which it has greatest temporal overlap (or whose interval contains its midpoint); resolve ties deterministically by earlier turn. Concatenate assigned words in time order per turn. Do not carry ASR text through VAD silence, and do not duplicate text across adjacent turns. If word timing is unavailable, transcribe each diarization crop or use a documented alignment method while retaining the diarization boundaries as authoritative. For a verified speech turn with no reliable recognized words, use `[unintelligible]` rather than invented transcript content.

5. **Write the deliverables deterministically.** Construct a JSON input from the actual final turns and actual successful provenance, then run:
   ```sh
   python3 scripts/write_artifacts.py <<'JSON'
   {
     "audio_duration_sec": 0.0,
     "turns": [
       {"start": 0.0, "end": 0.0, "speaker": "raw-tool-label", "text": "recognized words"}
     ],
     "output_dir": "/root",
     "file_id": "input",
     "steps_completed": ["audio_extraction", "diarization", "asr", "subtitle_generation"],
     "commands_used": ["actual executable names or commands"],
     "libraries_used": ["actually imported package names"],
     "tools_used": {
       "audio_extraction": "actual tool and settings",
       "diarization": "actual VAD/embedding/diarization tool and model",
       "asr": "actual ASR tool and model",
       "subtitle_generation": "scripts/write_artifacts.py"
     },
     "notes": "Actual method, alignment policy, limitations, and selected parameters."
   }
   JSON
   ```
   Replace illustrative values with runtime results. Each turn requires numeric `start`, exactly one of numeric `end` or `duration`, a nonempty raw `speaker`, and text. The writer maps raw speaker labels in first-occurrence chronological order to `SPEAKER_00`, `SPEAKER_01`, etc.; this exact mapping is used in both RTTM and subtitle cues. It sorts turns chronologically, requires all turns to lie within the measured duration, and derives both speaker count and total speech time from those same final turns.

6. **Validate before finalizing.** Treat successful script output as a structural validation report. Confirm all three paths exist. Inspect that each RTTM line has ten fields, begins `SPEAKER`, has nonnegative start and positive duration; that every ASS dialogue timestamp uses `H:MM:SS.cc`; and that every cue begins with `SPEAKER_XX:`. The JSON report must contain only facts about successfully completed commands/tools and must have counts and speech total derived from the emitted RTTM turns. Recheck audio duration with ffprobe/WAV metadata if it differs from the value supplied to the writer.

## Writer input/output contract

`write_artifacts.py` input is an object with:

* required `audio_duration_sec`: nonnegative number;
* required `turns`: list of `{start, end|duration, speaker, text}` objects;
* optional `output_dir` (default `/root`), `file_id` (default `input`), `steps_completed`, `commands_used`, `libraries_used`, `tools_used`, and `notes`.

It writes the three named files under `output_dir` and emits `{"ok":true,"outputs":...,"num_speakers_pred":...,"total_speech_time_sec":...}`. On bad input or failed writing it emits `{"ok":false,"error":...}` and exits nonzero. It never runs media tools or performs bank/host actions.
