---
name: flink-longest-stage-per-job
description: >-
  Implement and validate a Flink (Java) job over Google cluster-usage traces that
  groups per-job task SUBMIT events into event-time session "stages" (10-minute
  inactivity gap), counts tasks per stage, and emits (jobId, maxStageTaskCount) per
  job once the job has finished. Use this Skill for the `clusterdata.query.LongestSessionPerJob`
  task: it supplies the data schema, the exact stage/session semantics, a Java
  implementation template, and a Python reference oracle + comparator to validate the
  Flink output locally before relying on the grader.
---

# Longest stage per job (Flink session windows over Google cluster traces)

## What the task requires (restate from the public request)
- Edit ONLY `/app/workspace/src/main/java/clusterdata/query/LongestSessionPerJob.java`
  (do not rename the class) and add the datatype classes it needs under
  `clusterdata.datatypes` (referenced by `clusterdata.utils.AppBase`).
- Do NOT change `pom.xml`. The jar name and `mainClass` are already defined there.
- Parameters (ParameterTool): `--task_input` (one gzipped task-event CSV),
  `--job_input` (one gzipped job-event CSV), `--output` (local output file path).
- A **stage** = a maximal run of task **SUBMIT** events for one `jobId` whose
  consecutive events are separated by **less than 10 minutes** in event time; a gap of
  **>= 10 minutes** with no SUBMIT closes the stage. This is exactly an event-time
  **session window** with `withGap(Time.minutes(10))`, keyed by `jobId`.
- The stage "size" = **number of SUBMIT task events** in the window. Resubmissions count
  separately: do NOT deduplicate by task index. Count every SUBMIT (eventType 0) record.
- Timestamps are in **microseconds**; divide by 1000 to get the milliseconds Flink uses
  for watermarks and `Time.minutes(10)` (= 600000 ms) gap comparison.
- Output one line per job: the tuple string `(jobId,maxStageTaskCount)` (no spaces),
  which is exactly `Tuple2<Long,Integer>.toString()`. Line order does not matter.
- Emit a job only **once it has finished** by joining the job-completion lifecycle
  stream on the same `jobId` key, without discarding accumulated session state
  (see `references/implementation_notes.md`).

## Mandatory first steps in the environment
1. Read the actual contracts before coding:
   - `cat /app/workspace/src/main/java/clusterdata/utils/AppBase.java`
   - `cat /app/workspace/src/main/java/clusterdata/query/LongestSessionPerJob.java`
   - `grep -nE 'mainClass|artifactId|flink.version|<version>' /app/workspace/pom.xml`
   AppBase "mentions" the datatype classes you must create and may provide helper
   source/sink methods or a `main` convention — your implementation must match the
   method names, constructors and the Flink version the pom pins.
2. Confirm the data schema (`references/schema.md`) by sampling the gz files:
   `zcat /app/workspace/data/task_events/part-00001-of-00500.csv.gz | head`
   `zcat /app/workspace/data/job_events/part-00001-of-00500.csv.gz | head`
   Verify column positions match the schema reference before trusting field indices.

## Implement
- Use the templates in `references/` as the logic blueprint, then ADAPT them to the
  real `AppBase`/skeleton signatures and the pinned Flink version:
  - `references/LongestSessionPerJob.java.txt` — the pipeline.
  - `references/TaskEvent.java.txt`, `references/JobEvent.java.txt` — serializable
    datatypes with a `fromString` CSV parser following the published schema.
- Field indices (0-based, `split(",", -1)`):
  - task_events: `0`=timestamp(µs), `2`=jobId, `3`=taskIndex, `5`=eventType.
  - job_events:  `0`=timestamp(µs), `2`=jobId, `3`=eventType.
  - Event-type codes: 0 SUBMIT, 1 SCHEDULE, 2 EVICT, 3 FAIL, 4 FINISH, 5 KILL,
    6 LOST, 7 UPDATE_PENDING, 8 UPDATE_RUNNING.
- Parse defensively: skip short/malformed lines; never silently shift columns.
- `.gz` CSVs: `env.readTextFile(path)` auto-decompresses `.gz`; do not unzip in memory.
- Set `env.setParallelism(1)` so `writeAsText(output, OVERWRITE)` produces a single file
  at the given path (deterministic, one line per tuple).
- The job-finished join: filter job_events to FINISH (eventType 4), connect it with the
  per-job session-count stream keyed by jobId, and emit `(jobId, max count)` from an
  end-of-stream event-time timer so accumulated session state is preserved. See notes.

## Build and run locally (validation, not grading)
- Compile first (compilation success is part of grading):
  `cd /app/workspace && mvn -q -o clean package` (drop `-o` if offline cache is missing;
  internet is allowed). If the shaded/target jar is produced, note its path from pom.
- Run the job locally. Prefer the in-process local environment via the built jar:
  `cd /app/workspace && flink run target/<jarName>.jar --task_input data/task_events/part-00001-of-00500.csv.gz --job_input data/job_events/part-00001-of-00500.csv.gz --output /tmp/out.txt`
  If no Flink CLI/cluster is available, run the main class with the Maven-resolved
  classpath (flink-clients on classpath gives an embedded MiniCluster):
  `mvn -q -o exec:java -Dexec.mainClass=clusterdata.query.LongestSessionPerJob -Dexec.args="--task_input data/task_events/part-00001-of-00500.csv.gz --job_input data/job_events/part-00001-of-00500.csv.gz --output /tmp/out.txt"`
  (add the exec plugin only for your local test; never edit pom for the submission).

## Validate the output against the independent oracle
`scripts/oracle.py` recomputes the expected per-job answer directly from the gz CSVs
using the SAME semantics (ms = µs/1000, 600000 ms gap, count SUBMITs, emit finished jobs).
`scripts/compare.py` diffs the Flink output file against the oracle.

Example:
```
echo '{"task_input":"/app/workspace/data/task_events/part-00001-of-00500.csv.gz","job_input":"/app/workspace/data/job_events/part-00001-of-00500.csv.gz"}' \
  | python3 /app/environment/skills/current/scripts/oracle.py > /tmp/oracle.json
echo '{"oracle_json_path":"/tmp/oracle.json","output_path":"/tmp/out.txt"}' \
  | python3 /app/environment/skills/current/scripts/compare.py
```
`compare.py` prints `{"match":true,...}` on agreement, otherwise lists
`only_in_expected`, `only_in_output`, and `count_mismatches` so you can locate the bug
(wrong field index, µs/ms, dedup, gap boundary, or finished-job filter).

## Script I/O schemas
- `scripts/oracle.py`: stdin JSON `{"task_input":str,"job_input":str,
  "gap_ms":int=600000,"finish_event_types":[int]=[4],"only_finished":bool=true}`.
  stdout JSON `{"counts":{jobId(str):maxCount(int)},"num_jobs":int}`.
- `scripts/compare.py`: stdin JSON with `output_path` (file or directory of part files)
  and either `expected` (dict jobId->count) or `oracle_json_path` (path to oracle.py
  output). stdout JSON `{"match":bool,"num_expected":int,"num_output":int,
  "only_in_expected":[...],"only_in_output":[...],"count_mismatches":[[job,exp,got],...]}`.

## Handling ambiguity / failure modes
- "Finished" default = job FINISH event (type 4). If the grader indicates missing or
  extra jobs, keep Flink and oracle consistent and try, in order:
  (a) broaden finish types to all terminal job events `[2,3,4,5,6]`; or
  (b) emit every job that has SUBMITs (set `only_finished=false` and switch the Flink
      pipeline to the single-stream variant in `references/implementation_notes.md`
      that emits each job's max on the end-of-stream timer, with no finish join).
  Change the Flink constant AND the oracle flag together so local validation stays valid.
- If compilation fails, reconcile API names with the pinned Flink version (imports for
  `Time`, `EventTimeSessionWindows`, `KeyedCoProcessFunction`, `Types`) and the exact
  method/constructor signatures AppBase expects for the datatype classes.
- Do not hardcode any jobId or count into the Java or the Skill; always read the actual
  `--task_input`/`--job_input` at runtime.
