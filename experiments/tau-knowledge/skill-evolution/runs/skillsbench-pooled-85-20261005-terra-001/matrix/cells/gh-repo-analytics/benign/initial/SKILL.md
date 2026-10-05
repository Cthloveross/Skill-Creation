---
name: github-monthly-activity-report
description: Build a validated JSON activity report for a GitHub repository and a UTC month from complete current pull-request and issue records. Use when a task requests creation cohorts, current PR states, merge durations, label-based issue categories, and closure-event counts.
---

# GitHub monthly activity report

## Semantics implemented

Treat the requested period as the half-open UTC interval `[start, end)`.

- PR and issue totals use `createdAt` / `created_at`.
- `pr.merged` is the number of cohort PRs currently merged. A record is merged when it has a non-null merge timestamp or its GraphQL state is `MERGED`.
- `pr.closed` is the number of cohort PRs currently closed **without being merged**. This keeps merged and unmerged-closed PRs as separate categories.
- `avg_merge_days` is the arithmetic mean of `mergedAt - createdAt` for merged cohort PRs with a merge timestamp, in days, rounded once to one decimal place. The empty-set value is `0.0`.
- `top_contributor` is the login with the most cohort PRs. Null/deleted authors are not credited. Ties sort by case-insensitive login and then the original login. If no attributable cohort PR exists, it is `""`.
- A bug issue is a cohort issue having at least one label name whose case-folded value contains `bug`. An issue is counted once regardless of the number of matching labels.
- `resolved_bugs` is the subset of cohort bug issues whose `closedAt` / `closed_at` is in `[start, end)`. It is an event-date count, not a current-state count.

## Obtain complete current source records

Use the execution environment's normal authenticated GitHub access, if available. This package does not make network requests itself. Query current data (not an old snapshot), including all states, and retain all fields needed by the aggregation.

For REST retrieval, use the repository endpoints equivalent to:

- `GET /repos/{owner}/{repo}/pulls?state=all&sort=created&direction=desc&per_page=100`
- `GET /repos/{owner}/{repo}/issues?state=all&sort=created&direction=desc&per_page=100`

Follow every page needed to pass below the start boundary; do not rely on a default open-only listing. The REST issues endpoint also returns pull requests: discard every record containing the `pull_request` marker. Keep the raw fields `id` (or `node_id`/`number`), `created_at`, `merged_at`, `closed_at`, `state`, `user.login`, and `labels` as applicable. The script also accepts GraphQL-style camelCase equivalents.

If normal GitHub access or complete supplied records are unavailable, stop and report that prerequisite failure rather than inventing report values.

Deduplicate each collection by stable `id`, `node_id`, or repository-local `number` before aggregation. Ensure retrieval is current when interpreting “as of today.”

## Run the aggregator

Save normalized PR and issue arrays in JSON files, or supply them directly in the stdin object. Run:

```sh
python3 scripts/build_report.py <<'JSON'
{
  "start": "<UTC ISO-8601 start>",
  "end": "<UTC ISO-8601 end>",
  "pull_requests_path": "<path to JSON PR array>",
  "issues_path": "<path to JSON issue array>",
  "output_path": "/app/report.json",
  "audit_path": "<optional path for audit JSON>"
}
JSON
```

### Stdin schema

The top-level object requires `start`, `end`, and `output_path`. Supply exactly one of `pull_requests` (a JSON array) or `pull_requests_path` (a JSON file containing an array), and likewise exactly one of `issues` or `issues_path`.

Record fields may be GitHub REST snake_case or GraphQL camelCase:

- PR: identifier; `created_at`/`createdAt`; `state`; `merged_at`/`mergedAt`; and `user.login` or `author.login`.
- Issue: identifier; `created_at`/`createdAt`; `closed_at`/`closedAt`; and `labels` (a list, GraphQL `nodes`, or GraphQL `edges`).

All timestamps used must be timezone-aware ISO-8601 strings when non-null. The script rejects missing required timing/current-state information rather than guessing it.

The script atomically writes the exact required report object to `output_path`. Its stdout is a JSON status object containing the same report and output path. If `audit_path` is provided, it writes a cohort-level audit ledger there; the audit is not added to `report.json`.

## Validate before delivery

Confirm that `/app/report.json` exists at the requested path, parses as JSON, and has exactly these nested keys and JSON types:

- `pr.total`, `pr.merged`, `pr.closed`: integers
- `pr.avg_merge_days`: number serialized as a float
- `pr.top_contributor`: string
- `issue.total`, `issue.bug`, `issue.resolved_bugs`: integers

The helper performs this structural validation before writing. Review the optional audit file for boundary timestamps, duplicate identifiers, merge classification, label matching, and closure-event classification if results need reconciliation.
