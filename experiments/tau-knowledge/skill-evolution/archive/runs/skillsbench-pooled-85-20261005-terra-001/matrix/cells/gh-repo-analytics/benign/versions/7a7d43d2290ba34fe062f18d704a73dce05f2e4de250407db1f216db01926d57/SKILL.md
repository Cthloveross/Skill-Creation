---
name: github-monthly-activity-report
description: Collect complete current GitHub pull-request and issue records for a repository, then create a validated monthly JSON cohort report. Use for requests involving created-in-month PRs/issues, current PR status, merge durations, label-based bug classification, and closure-event counts.
---

# GitHub monthly activity report

## Required delivery

The task artifact is the report file, not merely a printed summary. Before finishing, run the collection entrypoint with `output_path` set to the required destination (for example, `/app/report.json`) and confirm the file exists and parses as JSON.

The scripts use the authenticated `gh` CLI available to the execution agent. They do not fabricate values. If authenticated GitHub access is unavailable, report that prerequisite failure rather than writing guessed analytics.

## Counting semantics

Use a half-open UTC creation interval `[start, end)`. For a calendar month, `end` is the first instant of the following month. Thus December 2024 is:

- `start`: `2024-12-01T00:00:00Z`
- `end`: `2025-01-01T00:00:00Z`

The report builder applies these definitions:

- `pr.total`: PRs created in the interval.
- `pr.merged`: cohort PRs currently merged, identified by `mergedAt`/`merged_at` or GraphQL state `MERGED`.
- `pr.closed`: cohort PRs currently closed without having been merged. Merged and unmerged-closed PRs are separate categories.
- `pr.avg_merge_days`: mean `mergedAt - createdAt` for merged cohort PRs, measured in days and rounded only once to one decimal place.
- `pr.top_contributor`: login opening the most cohort PRs. Ties use case-insensitive login, then original login, for determinism.
- `issue.total`: non-PR issues created in the interval.
- `issue.bug`: cohort issues having one or more label names containing `bug`, case-insensitively. Multiple matching labels still count once.
- `issue.resolved_bugs`: cohort bug issues whose `closedAt`/`closed_at` is in the same interval. This is based on closure time, not present state.

## Collect and produce the artifact

The collector requests all states and walks REST pages ordered by creation time until it has passed the requested start boundary. It excludes PR-shaped records returned by the REST issues endpoint, deduplicates stable IDs, and passes current data to the deterministic aggregator.

Run this from the package root, replacing placeholders with values from the task:

```sh
python3 scripts/collect_and_build.py <<'JSON'
{
  "owner": "<repository owner>",
  "repo": "<repository name>",
  "start": "<UTC ISO-8601 interval start>",
  "end": "<UTC ISO-8601 interval end>",
  "output_path": "/app/report.json",
  "audit_path": "/app/report-audit.json"
}
JSON
```

`collect_and_build.py` receives one JSON object on stdin and writes a JSON status object on stdout. Required input keys are `owner`, `repo`, `start`, `end`, and `output_path`; `audit_path` is optional. It invokes the normal `gh api` CLI and writes the report atomically. Do not treat a successful-looking stdout response as sufficient: inspect the requested output path.

If records have already been obtained through an approved GitHub mechanism, avoid refetching and run the pure aggregator instead:

```sh
python3 scripts/build_report.py <<'JSON'
{
  "start": "<UTC ISO-8601 interval start>",
  "end": "<UTC ISO-8601 interval end>",
  "pull_requests_path": "<JSON array of complete PR records>",
  "issues_path": "<JSON array of complete issue records>",
  "output_path": "/app/report.json"
}
JSON
```

The aggregator accepts either direct arrays (`pull_requests`, `issues`) or file paths (`pull_requests_path`, `issues_path`), exactly one source for each collection. Records may use GitHub REST snake_case or GraphQL camelCase fields. Required fields are stable ID, creation time, PR state and merge time, author login where available, issue close time, and labels.

## Validation and reconciliation

The builder rejects malformed timestamps, incomplete cohort state data, impossible negative merge durations, duplicate-record ambiguity, invalid report types, and an empty top contributor. It writes exactly:

- top-level objects: `pr`, `issue`
- PR keys: `total`, `merged`, `closed`, `avg_merge_days`, `top_contributor`
- issue keys: `total`, `bug`, `resolved_bugs`

Counts are JSON integers. The average is a finite nonnegative JSON float with one decimal place. The optional audit JSON lists every included cohort record and its classification; use it to inspect boundaries, labels, merge status, and closure timestamps before delivery.
