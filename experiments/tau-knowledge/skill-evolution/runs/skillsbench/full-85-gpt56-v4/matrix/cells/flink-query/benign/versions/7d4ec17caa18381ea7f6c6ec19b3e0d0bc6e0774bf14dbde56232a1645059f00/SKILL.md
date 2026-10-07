---
name: flink-longest-session-per-job
description: Implement and validate a bounded Apache Flink Java job over gzipped Google cluster task/job event CSVs. Use for tasks that require the largest event-time session of task SUBMITs per job, emitted only for completed jobs.
---

# Longest event-time stage per job

## Contract

Implement the existing job class without changing its name or `pom.xml`. The runtime arguments are, in order, `task_input`, `job_input`, and `output`. Inputs are individual gzipped CSV files and timestamps are **microseconds**. Output must contain one text line per completed job formatted exactly as Flink's two-field tuple, e.g. `(jobId,count)`; output ordering is immaterial.

A stage contains consecutive task `SUBMIT` records for one job whose timestamp separation is less than ten minutes. Ten minutes in this source is `600_000_000L` microseconds. A separation equal to the gap begins a new stage. Every SUBMIT input row counts, including a resubmission of the same task index.

## Inspect the supplied project first

1. Read `ClusterData2011_2.md` and the relevant table in `format.pdf`; do not infer column positions from a generic CSV layout. Confirm the task and job columns for timestamp, job ID, and event type, and confirm the numeric codes for `SUBMIT` and job `FINISH`.
2. Read the skeleton and `AppBase` before choosing APIs. It determines the installed Flink API generation, argument parsing conventions, and the datatype class names expected by the project.
3. Inspect `pom.xml` only to identify available Flink/Java APIs and compiler level; do not edit it.

For the standard Google trace schema, task/job timestamp, job ID, and event type are fields 0, 2, and 5 respectively; task SUBMIT and job FINISH have codes 0 and 4. Treat this as something to verify against the supplied schema, not a reason to shift columns when optional trailing fields are absent.

## Implementation method

Create the serializable public record classes required by `AppBase` under `src/main/java/clusterdata/datatypes/`. Give each a public no-argument constructor and public fields (or the exact bean-compatible form used by the existing code). Retain at least timestamp (`long`), job ID (`long`), and event type (`int`). Parse each CSV row deliberately:

- read gzip through the file/source mechanism supported by the installed Flink version;
- split CSV while preserving empty columns (`split(",", -1)` is sufficient only after confirming this trace has no quoted CSV fields; otherwise use a CSV parser available in the project);
- reject malformed rows and rows whose required numeric columns cannot be parsed;
- never replace a missing middle column, as that shifts all later fields.

Construct two streams:

1. From task events, retain only `SUBMIT` records. Assign **event-time** timestamps from the source timestamp field in microseconds and assign watermarks that allow bounded input to finish all event-time windows. Key by job ID before sessionization.
2. From job events, retain only `FINISH` records and key by the same job ID.

Apply an event-time session window with a `600_000_000L` microsecond gap to the keyed SUBMIT stream and count records per session. Do not key by task index and do not deduplicate events. A session window is preferred because it correctly represents dynamic sessions and closes when the bounded source advances its watermark.

Then reduce the session counts per job to their maximum and emit it only if that job has a FINISH event. Use a keyed connected/coordinated stream, keyed state, or a bounded-safe join appropriate to the installed Flink version. The completion side must not discard a previously accumulated maximum merely because the completion event arrives before a session result in processing order. With bounded files, arrange finalization so either ordering of the two input streams yields the completed job's maximum. Do not use processing-time timers for stage semantics.

Use `long` for timestamps and job identifiers; do not truncate microsecond timestamps or job IDs to `int`. Counts may be `int` or `long`, but render the required numeric tuple form without labels. Configure the project-supported local text sink to the supplied `output` path. Check the installed API's overwrite behavior and whether it writes a single file or a directory; satisfy the invocation contract rather than hardcoding a sample output path.

## Edge cases to preserve

- Events from different job IDs never share a stage.
- Same-timestamp SUBMITs belong to one stage and each increments its count.
- A difference below the gap remains in one stage; a difference equal to or above the gap begins another.
- An unfinished job must not be output.
- A job with multiple FINISH records remains a single output job.
- Out-of-order task records must be handled under the chosen event-time/watermark policy rather than relying on source file order. For this bounded trace, use a watermark strategy appropriate for the actual Flink version and source ordering; if using zero out-of-orderness, only do so after establishing the source ordering makes it valid.

## Build and runtime validation

Compile using the project's normal Maven command and run the packaged job with all three paths. Inspect the generated output to ensure every nonblank line matches `^\\([0-9]+,[0-9]+\\)$` and that no duplicate job IDs occur.

Use `scripts/reference_longest_stage.py` as an independent, non-Flink check of the supplied inputs. It is not a replacement for executing the Flink job: it uses a sorted event-time calculation to establish expected completed-job maxima. Compare output as a mapping, not line order.

Example reference invocation (from this Skill directory):

```sh
printf '%s\n' '{"task_input":"/app/workspace/data/task_events/part-00001-of-00500.csv.gz","job_input":"/app/workspace/data/job_events/part-00001-of-00500.csv.gz"}' | python3 scripts/reference_longest_stage.py
```

The script reads one JSON object from stdin and emits one JSON object to stdout with `rows` as sorted `[jobId, maxCount]` pairs. It exits nonzero for missing files or invalid top-level input. Its schema defaults match the documented Google trace layout but can be overridden only after schema inspection via `task_timestamp_column`, `task_job_id_column`, `task_event_type_column`, `job_job_id_column`, `job_event_type_column`, `submit_event_type`, `finish_event_type`, and `gap_microseconds`.
