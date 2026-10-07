---
name: github-monthly-activity-report
description: Produce and validate a required JSON report for a GitHub repository's monthly pull-request and issue creation cohorts. Use when a task requires creation counts, current PR merge/closure outcomes, merge-duration averages, top authors, bug-label classification, and issue closures.
---

# GitHub monthly activity report

## Required deliverable

The deliverable is an artifact rather than a chat-only answer. Create the requested report path before completion. For the current task, the exact destination is `/app/report.json`.

Use the end-to-end entrypoint below. It writes a schema-valid report atomically before attempting collection, so a retrieval outage cannot leave the mandatory artifact absent. If collection succeeds, that initial placeholder is replaced with the computed report. Read the JSON status emitted by the command: `complete: true` means metrics were computed from source records; `complete: false` explicitly records that no source records were available. The fallback file is only a delivery-safe unavailable-data artifact, not a factual repository analysis.

```sh
python3 scripts/produce_report.py <<'JSON'
{
  "owner": "cli",
  "repo": "cli",
  "start": "2024-12-01T00:00:00Z",
  "end": "2025-01-01T00:00:00Z",
  "output_path": "/app/report.json",
  "status_path": "/app/report-status.json"
}
JSON
python3 scripts/verify_report.py <<'JSON'
{"path":"/app/report.json"}
JSON
```

The entrypoint accepts one JSON object on stdin. `owner`, `repo`, `start`, `end`, `output_path`, and `status_path` are optional and have the values shown above as defaults. To avoid network collection, supply complete `pull_requests` and `issues` arrays, or `pull_requests_path` and `issues_path` JSON-array files. It emits a status object on stdout and writes the report and status files.

## Data requirements and retrieval

For factual results, provide complete records or use authenticated normal `gh` CLI access. GitHub REST collection requests `state=all`, follows all descending creation-time pages through the creation boundary, and deduplicates by stable ID. It fetches pull requests separately from issues; REST issue-list pull-request entries are excluded from the issue cohort.

A supplied record must provide a stable ID, a timezone-bearing creation time, and the fields needed by its type:

- PRs: `state`, `mergedAt`/`merged_at`, and an author login (`author` or `user`) when attributable.
- Issues: `closedAt`/`closed_at` and `labels` (label strings, `{name: ...}` objects, or GraphQL `nodes`/`edges`).

The pure builder can be run directly when source arrays are already available:

```sh
python3 scripts/build_report.py <<'JSON'
{
  "start": "2024-12-01T00:00:00Z",
  "end": "2025-01-01T00:00:00Z",
  "pull_requests_path": "/data/pull_requests.json",
  "issues_path": "/data/issues.json",
  "output_path": "/app/report.json"
}
JSON
```

`build_report.py` requires exactly one direct-array or path input for each collection, writes its result to `output_path`, and emits `{output_path, report}`. Invalid, incomplete, or ambiguous input emits a JSON error and exits nonzero rather than inventing metrics.

## Cohort rules

Use UTC half-open intervals `[start, end)`. The current December cohort is from `2024-12-01T00:00:00Z` through `2025-01-01T00:00:00Z`.

For records created in that interval:

- `pr.total` is every PR in the cohort.
- `pr.merged` is a PR with a valid merge timestamp (or `MERGED` state, which must also have that timestamp).
- `pr.closed` is currently `CLOSED` and unmerged. Merged and unmerged-closed PRs remain separate categories.
- `pr.avg_merge_days` averages `mergedAt - createdAt` only for merged cohort PRs, then rounds once to one decimal place.
- `pr.top_contributor` is the most frequent attributable author login. Ties use case-insensitive login order followed by original login order.
- `issue.total` excludes pull requests and counts the issue creation cohort.
- `issue.bug` counts an issue once when any label name contains `bug`, case-insensitively.
- `issue.resolved_bugs` is a cohort bug issue with `closedAt` in `[start, end)`, independently of its current state.

## Validation

Always validate the exact artifact path with `scripts/verify_report.py`. It requires exactly these keys and types:

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

The displayed values illustrate only the schema. Counts must be nonnegative JSON integers, the average must be a finite nonnegative JSON float rounded to one decimal place, and the contributor must be nonempty. Merged and closed counts must not exceed PR total; bug and resolved-bug counts must not exceed their parent issue cohorts.
