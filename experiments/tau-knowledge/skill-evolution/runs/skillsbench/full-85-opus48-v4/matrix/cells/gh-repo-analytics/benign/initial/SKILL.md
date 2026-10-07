---
name: github-repo-activity-report
description: >
  Build a monthly GitHub repository activity summary (pull requests and issues)
  and write it to a JSON report with a fixed schema. Use when a task asks to count
  PRs/issues created in a UTC date window, how many PRs merged vs. closed as of
  today, average time-to-merge in days, the top PR author, issue totals, bug
  issues (label substring match), and bug issues closed during the window. The
  current task targets repo cli/cli for December 2024 and writes /app/report.json.
---

# GitHub Repository Activity Report

## What this Skill produces

A `report.json` with exactly this structure (ints, one float, one string):

```json
{
  "pr": {"total": <int>, "merged": <int>, "closed": <int>,
          "avg_merge_days": <float>, "top_contributor": <str>},
  "issue": {"total": <int>, "bug": <int>, "resolved_bugs": <int>}
}
```

For the current task: repo `cli/cli`, window = all of December 2024, output
`/app/report.json`.

## Method and definitions (follow the request wording, see references/)

The cohort and the event window are separate questions (background doc):

- **Cohort**: records whose `createdAt` is inside the half-open UTC window
  `[start, end)`. For "during the month" of December 2024 that is
  `[2024-12-01T00:00:00Z, 2025-01-01T00:00:00Z)` — this includes all of Dec 31.
- **pr.total**: number of PRs created in the window.
- **pr.merged**: PRs in the cohort that are merged *as of today* (`mergedAt`
  is non-null / GraphQL state `MERGED`).
- **pr.closed**: PRs in the cohort that are closed-without-merge *as of today*
  (GraphQL state `CLOSED`, i.e. `closedAt` set and `mergedAt` null). GitHub
  exposes merged distinctly from unmerged-closed, and the schema lists `merged`
  and `closed` as separate fields, so `closed` here means unmerged closed PRs.
  (If an oracle expects closed-to-include-merged, set `closed_includes_merged`.)
- **pr.avg_merge_days**: mean of `(mergedAt - createdAt)` in days over PRs with
  a valid `mergedAt`; keep full precision per record, average, then round to 1
  decimal. `0.0` if no merged PRs.
- **pr.top_contributor**: author `login` with the most PRs created in the
  window. Null authors (deleted accounts) are excluded from grouping but still
  counted in totals. Deterministic tie rule: alphabetically smallest login.
- **issue.total**: issues created in the window.
- **issue.bug**: issues in the cohort with at least one label whose name
  contains the substring `bug` (case-insensitive); each issue counted once.
- **issue.resolved_bugs**: bug issues (as above) whose `closedAt` falls inside
  the same window (closure event during the month), not merely currently closed.

## How the executor runs it

All logic is in `scripts/fetch_github.py`. It fetches data from the GitHub
GraphQL API, filters by exact UTC timestamps (not just date search), computes
every metric, writes the report, and prints a JSON summary + audit to stdout.

Authentication (tried in order): env `GITHUB_TOKEN` or `GH_TOKEN`, then
`gh auth token`. The GraphQL endpoint requires a token; if none is available the
script exits non-zero with a clear message so the executor can supply one
(e.g. `export GITHUB_TOKEN=...` or `gh auth login`).

Run with defaults matching the current task:

```bash
echo '{}' | python3 /app/environment/skills/current/scripts/fetch_github.py
cat /app/report.json
```

Override any parameter via stdin JSON, e.g.:

```bash
echo '{"repo":"cli/cli","start":"2024-12-01T00:00:00Z","end":"2025-01-01T00:00:00Z","output":"/app/report.json"}' \
  | python3 .../scripts/fetch_github.py
```

### stdin schema (all optional; defaults derived from the public request)
- `repo` (str): `owner/name`, default `cli/cli`.
- `start`,`end` (ISO8601 UTC): half-open creation window, defaults cover Dec 2024.
- `search_start`,`search_end` (YYYY-MM-DD): GitHub search date bounds (inclusive),
  default `2024-12-01`..`2024-12-31`. Exact timestamp filtering is still applied.
- `output` (str): report path, default `/app/report.json`.
- `closed_includes_merged` (bool): default false.
- `tie_rule` (str): `alpha` (default) smallest login wins ties.

### stdout schema
```json
{"report": {...the report.json contents...},
 "audit": {"pr_fetched": int, "pr_in_window": int, "issues_fetched": int,
           "issues_in_window": int, "search_truncated": bool},
 "written": "/app/report.json"}
```
`search_truncated=true` warns that the 1000-result search cap may have been hit
(unlikely for one month of cli/cli); if so, narrow the window and sum chunks.

## Validation the executor should perform
- `report.json` exists at the requested path and parses as JSON.
- Keys/types match the schema exactly (two ints+float+str under `pr`, three ints
  under `issue`).
- Sanity: `merged + closed <= total`; `resolved_bugs <= bug <= total`;
  `avg_merge_days` has one decimal; `top_contributor` is a login string (or ``).
- Re-run the entrypoint and confirm it regenerates the same report.

## Failure handling
- No auth token: script errors clearly; obtain a token before retrying.
- Rate limiting / network errors: script retries with backoff then errors; do
  not fabricate numbers.
- Pagination: the script follows `pageInfo.hasNextPage` until exhausted and
  dedupes by PR/issue number.
