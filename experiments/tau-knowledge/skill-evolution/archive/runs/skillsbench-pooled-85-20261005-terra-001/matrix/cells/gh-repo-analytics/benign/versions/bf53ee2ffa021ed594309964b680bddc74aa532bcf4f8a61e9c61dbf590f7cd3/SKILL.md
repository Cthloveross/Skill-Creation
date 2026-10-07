---
name: github-monthly-activity-report
description: Build a validated JSON activity report for a GitHub repository from complete pull-request and issue data. Use for monthly creation cohorts, current PR merge/closed status, merge-time averages, top authors, label-substring bug classification, and in-window issue closures.
---

# GitHub monthly activity report

## Mandatory artifact

The deliverable is a file, not a chat summary. The execution agent must create the requested output path and validate it before finishing. For the current task, the required path is exactly `/app/report.json`.

This Skill never invents repository metrics. It needs either authenticated GitHub access through the normal `gh` CLI or complete, approved record arrays/snapshots supplied to the runtime. If neither is available (for example, a network-disabled runtime with no copied data), explicitly report the missing-data prerequisite rather than writing guessed counts.

## Semantics

Use UTC half-open creation intervals `[start, end)`. December 2024 means:

- `start`: `2024-12-01T00:00:00Z`
- `end`: `2025-01-01T00:00:00Z`

For the selected creation cohort:

- `pr.total` counts all PRs created in the interval.
- `pr.merged` counts cohort PRs that are currently merged (`mergedAt`/`merged_at` is non-null, or state is `MERGED`).
- `pr.closed` counts cohort PRs currently closed **without** being merged. Merged and unmerged-closed PRs are separate status categories.
- `pr.avg_merge_days` is the mean of `mergedAt - createdAt` for merged cohort PRs, in days, rounded once at the final aggregate to one decimal place.
- `pr.top_contributor` is the author login with the most cohort PRs. Ties sort case-insensitively by login and then by the original login.
- `issue.total` counts non-PR issues created in the interval.
- `issue.bug` counts cohort issues once when any label name contains `bug`, case-insensitively.
- `issue.resolved_bugs` counts cohort bug issues whose `closedAt`/`closed_at` falls in the same interval. It is a closure-timestamp measure, not a present-state measure.

## Recommended execution for `cli/cli`, December 2024

When authenticated GitHub retrieval is available, run this actual command from the package root. Do not leave the command as a plan; it writes `/app/report.json` atomically.

```sh
python3 scripts/collect_and_build.py <<'JSON'
{
  "owner": "cli",
  "repo": "cli",
  "start": "2024-12-01T00:00:00Z",
  "end": "2025-01-01T00:00:00Z",
  "output_path": "/app/report.json",
  "audit_path": "/app/report-audit.json"
}
JSON
python3 scripts/verify_report.py <<'JSON'
{"path":"/app/report.json"}
JSON
```

`collect_and_build.py` accepts one JSON object on stdin with required string keys `owner`, `repo`, `start`, `end`, and `output_path`; `audit_path` is optional. It requests all REST states, pages backwards through descending creation-time results until records older than `start` are reached, then writes a report and optional audit file. It emits a JSON status object to stdout or exits nonzero with a JSON error.

The `gh` CLI must be authenticated and able to reach GitHub. Its normal GitHub access is the only network mechanism used by this Skill.

## Building from supplied data

If complete PR and issue arrays were obtained through an approved mechanism, use the pure builder instead of refetching:

```sh
python3 scripts/build_report.py <<'JSON'
{
  "start": "2024-12-01T00:00:00Z",
  "end": "2025-01-01T00:00:00Z",
  "pull_requests_path": "/path/to/pull_requests.json",
  "issues_path": "/path/to/issues.json",
  "output_path": "/app/report.json",
  "audit_path": "/app/report-audit.json"
}
JSON
```

For each collection, supply exactly one of its direct array key (`pull_requests` or `issues`) and its `*_path` key. Files must be JSON arrays of record objects. REST snake_case and GraphQL camelCase timestamps are accepted. The data must include stable IDs, creation times, PR state and merge timestamp fields, PR authors where available, issue closure timestamp fields, and labels.

## Final validation

Run `scripts/verify_report.py` on the exact destination. It accepts `{"path":"..."}` and emits the parsed report only when it has exactly this contract:

```json
{
  "pr": {
    "total": 0,
    "merged": 0,
    "closed": 0,
    "avg_merge_days": 0.0,
    "top_contributor": "login"
  },
  "issue": {
    "total": 0,
    "bug": 0,
    "resolved_bugs": 0
  }
}
```

The illustration is a schema only, not data to copy. Counts must be nonnegative JSON integers, the average must be a finite nonnegative JSON float rounded to one decimal place, and the contributor must be nonempty. Reconcile the optional audit file when investigating unexpected boundaries, duplicate records, labels, merges, or closures.
