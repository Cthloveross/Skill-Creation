---
name: flink-longest-session-per-entity
version: 1.0.0
description: Implement and validate a bounded Flink query that derives event-time inactivity sessions from activity CSV records, retains repeated activity, gates results on lifecycle completion, and writes deterministic `(id,count)` output. Use for Google-cluster-style task/job trace jobs with microsecond timestamps.
---

# Longest event-time session per entity

Use this Skill when a supplied Java/Flink skeleton must calculate the largest count of activity events in an inactivity-delimited stage/session, usually per job, and report it only for completed entities.

## Inputs and contract

This task family has three runtime parameters:

- `task_input`: one task/activity CSV or CSV.GZ file.
- `job_input`: one job/lifecycle CSV or CSV.GZ file.
- `output`: local Flink sink path.

For the present task, the activity of interest is task `SUBMIT`; lifecycle eligibility is job `FINISH`; the entity key is `jobId`; and the inactivity gap is **10 minutes = 600,000,000 microseconds**. Output must be one line per result in the exact tuple rendering `(jobId,longestStageTaskCount)`. Do not deduplicate submit records: a task that is submitted, fails/evicts, and is submitted again contributes two events.

## Required workspace inspection

Before editing, read all of the following in the supplied workspace:

1. `src/main/java/clusterdata/query/LongestSessionPerJob.java`.
2. `src/main/java/clusterdata/utils/AppBase.java`.
3. `pom.xml`, to use only the installed Flink API/version.
4. `data/ClusterData2011_2.md` and the relevant pages of `data/format.pdf`.

The schema documents, rather than guesses about column positions, determine:

- timestamp, job-id, and event-type columns for task and job records;
- the exact numeric/string codes for `SUBMIT` and terminal `FINISH`;
- whether IDs fit `int` or require `long` internally.

Keep the required query class name unchanged and do not modify `pom.xml`. Add the public serializable POJO classes requested by `AppBase` under `src/main/java/clusterdata/datatypes/`.

## Implementation procedure

1. **Create compatible record POJOs.**
   Add the task and job event classes named and imported by `AppBase`. Make fields public (or supply public bean getters/setters), include a public zero-argument constructor, and include a full constructor. Retain at minimum event timestamp, job ID, and event type. Parse the documented CSV columns explicitly; reject/skip malformed rows deliberately rather than allowing a blank optional field to shift column positions. File readers used by the existing base class or Flink text source must accept `.gz` input.

2. **Use event time in the source unit.**
   Timestamps in this trace are microseconds. All session comparisons must use `600_000_000L` if they are made on raw timestamps. If using Flink's event-time API, convert exactly once to milliseconds (`timestampMicros / 1000L`) and use `Time.minutes(10)`. Never compare raw microseconds to a millisecond gap.

3. **Select activity without collapsing retries.**
   Filter task records only on the documented `SUBMIT` event code. Map each retained record to `(jobId, eventTimestamp)` or a typed equivalent. Do not key by task index and do not call `distinct`, because repeat submissions are distinct activity records.

4. **Form sessions by job and event timestamp.**
   A session starts at the first submit for a job. After sorting conceptually by event timestamp, an event belongs to the current session when its distance from the previous submit is *less than* 10 minutes. A difference of exactly 10 minutes begins a new session, because a full 10-minute inactivity period has elapsed. Count every member and retain the maximum count for that job.

   Prefer the API style already established by the skeleton:

   - For a streaming implementation, key by job ID *before* an event-time session window (`EventTimeSessionWindows.withGap(Time.minutes(10))` in compatible Flink versions), then count each window and reduce the per-job stage counts to a maximum.
   - For bounded input, a Flink batch/grouped-sort implementation is also valid and is often more robust to arbitrarily out-of-order file records: group submits by job, sort each group by raw microsecond timestamp, scan adjacent timestamps using the rule above, and emit its maximum. It remains event-time logic because ordering and gaps come solely from the event timestamp, not arrival time.

   Do not use processing-time sessions. Do not use a global session window followed by a job grouping.

5. **Account for out-of-order input and bounded completion.**
   If using event-time windows, assign timestamps from the documented task timestamp field and choose a watermark approach compatible with the actual source ordering. Do not silently drop legitimate late submit records. Because these are bounded files, make sure the job runs to completion so final watermarks/windows and file sinks flush. If source ordering has no reliable finite disorder bound, use the grouped-sort bounded approach rather than an undersized watermark allowance.

6. **Gate on finished jobs without losing accumulated stages.**
   Independently parse job events and retain job IDs having the documented `FINISH` event. Join/intersect the completed IDs with the computed per-job longest-stage values on the same job ID. Completion must not reset task/session state. In a bounded implementation, compute stage maxima and completed job IDs first, then use a keyed batch join. In a streaming implementation, ensure a completion arriving before a final session result does not cause an early, partial result; final bounded-input processing or keyed state/timers must wait until all relevant stage results are available.

   Unless the supplied skeleton or test contract explicitly specifies a zero for completed jobs with no submit records, emit only jobs that have at least one submit-derived stage. A `0` policy is a separate, explicit left-join decision and must not accidentally arise from missing state.

7. **Write the required text format.**
   Use a local text sink supported by the installed Flink version and configured to overwrite only if the API/skeleton expects that behavior. Emit a two-field Flink tuple or an explicitly formatted string so each data line is exactly `(first_int,second_int)` with no labels. Flink file sinks often create a directory containing `part-*` files; treat that directory as the output path unless the installed sink specifically supports a single target file. Execute the environment/job after declaring the sink.

## Recommended bounded algorithm

The following language-neutral logic is the correctness reference. It must operate on runtime input, never on hardcoded IDs or expected output.

```text
completed = set(jobId for job event whose type is FINISH)
for every task event whose type is SUBMIT:
    append its raw microsecond timestamp to submits[jobId]

for jobId, timestamps in submits:
    sort timestamps ascending
    current = 0
    best = 0
    previous = absent
    for timestamp in timestamps:
        if previous is absent or timestamp - previous >= 600000000:
            best = max(best, current)
            current = 1
        else:
            current += 1
        previous = timestamp
    best = max(best, current)
    if jobId in completed:
        emit (jobId, best)
```

Sorting is essential when the file itself is not event-time ordered. Equal timestamps are in one session.

## Build and validation

Compile and run using the project’s documented Maven/Flink invocation and the three supplied parameters. Then run the packaged validator with schema indexes and event codes taken from the workspace documentation, for example:

```bash
python3 scripts/validate_longest_sessions.py <<'JSON'
{
  "task_input": "/app/workspace/data/task_events/part-00001-of-00500.csv.gz",
  "job_input": "/app/workspace/data/job_events/part-00001-of-00500.csv.gz",
  "output": "/path/used/for/output",
  "task_schema": {"timestamp_column": 0, "job_id_column": 2, "event_type_column": 5, "submit_value": "DOCUMENTED_SUBMIT_CODE"},
  "job_schema": {"timestamp_column": 0, "job_id_column": 2, "event_type_column": 3, "finish_values": ["DOCUMENTED_FINISH_CODE"]}
}
JSON
```

The displayed indexes are only an invocation shape: replace every index and code with the values verified in the supplied schema documentation. The script accepts gzip or plain CSV, computes an independent sorted event-time reference, recursively reads a Flink output directory, and reports missing, unexpected, duplicate, or incorrect tuples. A successful comparison has `comparison.ok: true`.

Also check boundary cases: consecutive submits just below, exactly at, and just above the gap; interleaved jobs; repeated submissions; out-of-order lines; a completed versus an unfinished job; and a malformed line. Verify that output lines match the tuple syntax exactly and that no Java/POM class-name contract was changed.
