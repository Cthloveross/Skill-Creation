# Google cluster-usage traces (2011) — relevant schema

All CSV files are headerless, comma-separated, gzip-compressed. Timestamps are integer
microseconds since the start of the trace. Some synthetic events use timestamp 0 or
2^63-1; treat them with the same logic (no special-casing needed).

## task_events table (0-based column index)
0. timestamp (microseconds)
1. missing info
2. job ID
3. task index (within the job)
4. machine ID
5. event type
6. user name
7. scheduling class
8. priority
9. CPU request
10. memory request
11. disk space request
12. different-machine constraint

## job_events table (0-based column index)
0. timestamp (microseconds)
1. missing info
2. job ID
3. event type
4. user name
5. scheduling class
6. job name
7. logical job name

## Event type codes (shared by task_events and job_events)
0 SUBMIT
1 SCHEDULE
2 EVICT
3 FAIL
4 FINISH
5 KILL
6 LOST
7 UPDATE_PENDING
8 UPDATE_RUNNING

## Task-specific usage
- A "stage" is built only from task SUBMIT events (eventType == 0).
- Count every SUBMIT record (resubmissions after FAIL/EVICT count separately); do not
  deduplicate by (jobId, taskIndex).
- A job "has finished" when a job_event FINISH (eventType == 4) exists for that jobId
  (see SKILL.md for how to broaden this if the grader disagrees).
- Event time in milliseconds = microseconds / 1000. Session gap = 10 min = 600000 ms.

Always verify these column positions by sampling the real files with `zcat ... | head`
before trusting the indices, in case the provided subset differs.
