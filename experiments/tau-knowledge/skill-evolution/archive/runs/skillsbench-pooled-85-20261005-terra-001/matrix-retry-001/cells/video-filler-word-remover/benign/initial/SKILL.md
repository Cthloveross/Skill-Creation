---
name: video-filler-word-clips
description: Detect a declared vocabulary of filler words and multi-word filler phrases from a word-timestamped ASR transcript, write the required annotation JSON, and re-encode chronologically concatenated video/audio clips for the detections. Use for videos where word-level ASR timing is available or can be produced locally.
---

# Video filler-word annotations and clips

This Skill separates recognition, lexical detection, and editing. It applies the task's declared filler vocabulary exactly, including phrase matching. It does **not** infer word boundaries from ASR segments: every input token must have its own `start` and `end` time.

## Prerequisites

* The source video must be available to the executor (for this task, `/root/input.mp4`).
* `ffmpeg` and `ffprobe` must be available for clip production.
* Obtain a timestamped ASR result using an installed local recognizer/model. Before choosing a backend, inspect the available executables, Python packages, and model caches; network access is not assumed. Extracting audio as 16 kHz mono PCM WAV is a compatible ASR preparation step.
* The ASR result must contain **word-level** start and end times in source-timeline seconds. If a recognizer exposes only segment times, use an available word-alignment method or a recognizer with word timestamps. Do not assign every word in a segment the segment start time.

A useful ASR intermediate is a JSON object shaped like:

```json
{"segments": [{"words": [{"word": "Um,", "start": 3.5, "end": 3.72}]}]}
```

The packaged entrypoint also accepts a top-level `words` array or a top-level array. Each token needs `word` (or `text`/`token`), `start`, and `end` fields.

## End-to-end method

1. Decode/extract the source audio for local ASR, retaining a clear mapping to source time zero. Run the selected local ASR backend with word timestamps enabled and save its JSON result.
2. Inspect the result for valid, ordered, individual word timings. Resolve ASR failures or lack of word timing before proceeding; never create detections from guessed timing.
3. Invoke `scripts/detect_and_stitch.py` with the ASR JSON, source video, and required artifact paths. The script:
   * case-folds tokens and strips attached edge punctuation only for matching, while retaining the source token timing;
   * detects `um`, `uh`, `hum`, `hmm`, `mhm`, `like`, `you know`, `i mean`, `yeah`, `so`, `kind of`, `basically`, `i guess`, `well`, and `okay`;
   * checks phrases across immediately adjacent ASR tokens, gives the longest phrase priority, and does not emit overlapping partial matches;
   * writes `/root/annotations.json` as an array whose objects contain exactly `word` and `timestamp`, where timestamp is the first matched word's start;
   * clamps each media interval to actual source duration, decodes/re-encodes exact clips, resets each clip's timestamps, and concatenates audio and video from the same interval list.
4. Read the emitted validation JSON. It confirms that the output is decodable, contains audio and video streams, has finite nonnegative duration, and is close to the summed serialized intervals. The optional detailed interval file is useful for diagnosing alignment.

Lexical items such as `like`, `so`, and `well` can also be ordinary content words. This Skill reports lexical candidates because the requested vocabulary explicitly asks for them. If a task instead requires pragmatic/contextual filtering, review candidates against neighboring transcript/audio evidence before using the clip stage and record that additional decision rule.

## Runnable call example

After ASR has written `/root/asr_words.json`, provide this JSON to the script on stdin (for example through the execution runtime's script interface):

```json
{
  "transcript_path": "/root/asr_words.json",
  "video_path": "/root/input.mp4",
  "annotations_path": "/root/annotations.json",
  "output_path": "/root/output.mp4",
  "detailed_intervals_path": "/root/filler_intervals.json",
  "clip_padding_seconds": 0.0
}
```

Equivalent direct invocation is:

```sh
python3 scripts/detect_and_stitch.py < request.json
```

The entrypoint emits one JSON object on stdout. On success it includes `annotation_count`, `interval_count`, `input_duration`, `expected_clip_duration`, and `output_duration`. On a prerequisite or validation error it emits `{"ok": false, "error": "..."}` and exits nonzero.

## Input/output schema for `detect_and_stitch.py`

Input is one JSON object:

* `words` (optional): word-token list, or `transcript_path` (optional): path to a JSON transcript. Exactly one is required.
* `video_path`, `annotations_path`, `output_path`: required paths.
* `detailed_intervals_path` (optional): path for detailed matched and clipped intervals.
* `clip_padding_seconds` (optional, default `0.0`): nonnegative context added on both sides of each word/phrase clip.
* `duration_tolerance_seconds` (optional, default `0.75`): output-duration validation tolerance.
* `ffmpeg`, `ffprobe`, `video_codec`, `audio_codec` (optional): executable/codec overrides when the runtime requires them.

Each normalized input word must have a nonempty string token, finite `start` and `end`, `start >= 0`, and `end > start`. Source token order must be nondecreasing. Output `annotations_path` is the exact task-facing JSON array. Its order is chronological. `detailed_intervals_path`, if selected, is a JSON array containing the matched phrase start/end and the actual clamped clip start/end used for editing.

If no fillers are detected, the script writes `[]` for annotations but fails clip production rather than fabricating a nonempty video. If no valid word-level transcript, no audio/video stream, an invalid source duration, or an unavailable encoder is encountered, it fails explicitly and leaves no claimed successful media artifact.

## Validation checklist

* Parse `annotations.json`; verify it is an array and every item has only a string `word` and finite numeric nonnegative `timestamp`.
* Confirm annotations match the word-level transcript, preserve chronological order, and phrase timestamps use the first word.
* Parse the detailed intervals; ensure each is clamped within the probed input duration and `clip_end > clip_start`.
* Decode `output.mp4`; verify one video and one audio stream and compare its duration with the detailed interval sum. Inspect clip joins when unusually short clips, codec priming, or alignment concerns are present.
