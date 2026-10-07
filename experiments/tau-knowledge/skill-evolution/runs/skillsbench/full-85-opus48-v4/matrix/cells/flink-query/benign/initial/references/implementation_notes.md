# Implementation notes and design rationale

## Session (stage) semantics
- Key by jobId first, then apply `EventTimeSessionWindows.withGap(Time.minutes(10))`.
- Flink gap semantics: two consecutive events belong to the same session iff their
  event-time difference is < gap. A difference >= gap starts a new session. This matches
  "a stage ends when there is an inactivity period of 10 minutes".
- Window payload = number of SUBMIT events (count the elements). Use an AggregateFunction
  counting records, plus a ProcessWindowFunction to attach the jobId key, yielding
  Tuple2<Long jobId, Integer countInStage> per session.
- Per job, the answer is the maximum count across its sessions.

## Units
- Timestamps are microseconds. The timestamp assigner must return milliseconds
  (micros / 1000) because `Time.minutes(10)` is 600000 ms. Mixing units silently
  breaks window membership.

## Emitting only finished jobs (default)
- Build a second stream from job_events filtered to FINISH (eventType 4), mapped to
  Tuple2<Long jobId, Integer 0>.
- `connect` the session-count stream (keyed by jobId) with the finish stream (keyed by
  jobId) and use a `KeyedCoProcessFunction` that:
  - processElement1 (session count): `maxCount = max(maxCount, value.f1)`; store in
    ValueState; register an event-time timer at `Long.MAX_VALUE`.
  - processElement2 (finish marker): set a `finished` ValueState flag; register the
    same timer.
  - onTimer: if `finished == true` and `maxCount` is set, emit `(jobId, maxCount)`.
- On a bounded source, end-of-input pushes the watermark to Long.MAX_VALUE, firing the
  timer exactly once per key. This preserves accumulated session state until the
  completion signal, as required.
- Both input streams need watermark strategies so the connected operator watermark can
  advance; the finish stream's event timestamps are irrelevant (use 0) because only the
  end-of-stream watermark matters.

## Alternative: emit every job (no finish join)
If the grader expects all jobs with SUBMITs (not just finished ones), drop the finish
stream and run the session-count stream through a single `KeyedProcessFunction` keyed by
jobId that updates a max ValueState per element and registers a Long.MAX_VALUE event-time
timer; onTimer emit `(jobId, maxCount)`. Set the oracle's `only_finished=false` to match.
Do NOT use `maxBy(...)` straight into the sink: it emits every running maximum, producing
multiple lines per job.

## Output
- `env.setParallelism(1)` and `stream.map(t -> "("+t.f0+","+t.f1+")")
  .writeAsText(output, FileSystem.WriteMode.OVERWRITE)` writes a single file with one
  tuple per line. `Tuple2.toString()` already yields `(f0,f1)` with no spaces if you
  prefer to sink the tuple directly.

## Reading gzipped CSV
- `env.readTextFile(path)` registers InflaterInputStreamFactory for `.gz` and streams
  decompressed lines; no manual unzip. Parse per line in a MapFunction.

## Compilation
- Match the Flink version pinned in pom.xml. Datatype classes must be `Serializable`
  with a public no-arg constructor and public fields (or getters) compatible with the
  DataStream API. Confirm the exact names/methods AppBase expects before finalizing.
