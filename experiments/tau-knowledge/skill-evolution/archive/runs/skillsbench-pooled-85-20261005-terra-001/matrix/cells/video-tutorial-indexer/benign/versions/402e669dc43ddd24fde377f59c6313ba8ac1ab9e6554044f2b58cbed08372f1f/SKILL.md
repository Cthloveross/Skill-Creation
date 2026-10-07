---
name: video-tutorial-chapter-indexer
description: Create a validated JSON chapter index for a tutorial video by transcribing its audio, reviewing chronological transcript/video evidence, and aligning supplied chapter titles to the first sustained treatment of each topic. Use when a video path, ordered chapter titles, required metadata, and output path are provided.
---

# Video Tutorial Chapter Indexer

This Skill produces the required chapter-index artifact rather than guessing chapter times from equal spacing. It uses a timestamped ASR transcript as evidence, then requires chronological semantic review for the final chapter starts. It is particularly useful for software tutorials, where title wording is often paraphrased and tiny chapters such as a break or save action matter.

## Inputs

Obtain these from the current task at runtime (do not substitute titles or timestamps from another task):

- video file path;
- ordered list of exact chapter-title strings;
- required output metadata: video title and duration in seconds;
- required JSON output path.

The output schema is:

```json
{
  "video_info": {"title": "<provided title>", "duration_seconds": 0},
  "chapters": [{"time": 0, "title": "<exact supplied title>"}]
}
```

## Procedure

1. **Inspect prerequisites and metadata.** Confirm the supplied video exists and retain any supplied video-info file as supporting evidence. Use the supplied duration for the final range check; `ffprobe` duration is useful as a cross-check, not a reason to silently change required metadata.

2. **Create a timestamped transcript.** Run `scripts/prepare_transcript.py` with JSON on stdin. It extracts 16 kHz mono WAV audio using `ffmpeg` and uses the installed `whisper` CLI to write Whisper JSON. A practical initial model for clear English tutorial narration is `small`; use `base` only when runtime limits require it, and compensate with more video review. The script deliberately fails clearly if `ffmpeg`, `ffprobe`, or `whisper` is absent. The executor may install a permitted ASR implementation and model before rerunning it; it must not claim transcription succeeded without a JSON transcript.

   Example input:
   ```json
   {"video_path":"/path/tutorial.mp4","audio_path":"/path/tutorial.wav","transcript_path":"/path/transcript.json","model":"small","language":"en"}
   ```

   Output is JSON containing the actual audio/transcript paths, measured duration, and segment count. Whisper JSON is expected to contain a `segments` array with numeric `start`, `end`, and `text` fields.

3. **Generate review leads, not final answers.** For each title, make a few title-specific aliases from the task terminology and likely spoken/action wording (for example, a tool name, an operation verb, or a phrase the speaker is likely to say). Pass the supplied titles, aliases, and the transcript to `scripts/find_transcript_cues.py`. This ranks segments with lexical/phrase evidence and returns neighboring context. Its output is only a navigation aid: title text is a summary and exact string matching is not semantic alignment.

   Example input:
   ```json
   {
     "transcript_path":"/path/transcript.json",
     "chapters":[
       {"title":"<exact title 1>","aliases":["possible spoken phrase"]},
       {"title":"<exact title 2>","aliases":[]}
     ],
     "per_chapter":8,
     "context":1
   }
   ```

4. **Align in chronological order using transcript plus playback.** Start the first chapter at exactly `0`. For every later supplied chapter, inspect the candidate context and seek the video around it. Select the earliest point after the previous accepted start where the instructor begins *actively demonstrating or teaching* that topic. Do not choose an earlier teaser such as “later we will…”, nor a mere transcript segment split. Explicit topic introductions and a sustained shift in actions/discussion are stronger evidence than a pause or an isolated keyword.

   Review the whole sequence in order. For ambiguous transitions, use the prior and following confirmed topics to identify the topic handoff. Preserve genuine short chapters: a break, save, note, or housekeeping action can be one sentence long and still needs a separate timestamp. Do not fill uncertain regions using arbitrary or equal interpolation. Round to sensible numeric seconds only after selecting evidence-backed starts.

5. **Write and validate the artifact.** Pass the exact runtime title strings and reviewed numeric times to `scripts/write_index.py`. It atomically writes the requested JSON file only after validating all structural invariants.

   Example input:
   ```json
   {
     "video_title":"<provided video title>",
     "duration_seconds":123,
     "titles":["<exact title 1>","<exact title 2>"],
     "times":[0,17],
     "output_path":"/required/output.json"
   }
   ```

   Successful stdout reports the output path and chapter count. The written file has exactly the input titles, in input order.

## Required final checks

Before reporting completion, ensure the writer succeeded and inspect the produced JSON if needed. It must have exactly one entry for every supplied title; reproduce each title character-for-character; have numeric finite timestamps; start with `0`; be strictly increasing with no ties; and keep every time in `[0, duration_seconds]`. If transcript generation, semantic identification, or a required tool is unavailable, report that limitation rather than fabricating evidence or an index.
