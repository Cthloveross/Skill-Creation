---
name: github-monthly-community-pulse
description: Generate a validated JSON activity report for a GitHub repository over a UTC monthly (or other date) creation cohort, including PR lifecycle metrics and label-based issue metrics. Use when a task requires live GitHub activity data and an output file with exact aggregate fields.
---

# GitHub Monthly Community Pulse

Use this Skill to produce an artifact from current GitHub data. It deliberately separates the **creation cohort** from merge, closure, and current-state conditions:

- PR and issue cohort membership is `createdAt` in `[start, end)` UTC.
- `merged` counts cohort PRs whose current GraphQL state is `MERGED`.
- `closed` counts cohort PRs whose current GraphQL state is `CLOSED`, so it does **not** double-count merged PRs.
- PR merge duration is `mergedAt - createdAt` for merged cohort PRs with a merge timestamp.
- A resolved bug is a cohort issue with a bug-matching label and `closedAt` in `[start, end)` UTC.

The supplied task request is the source for repository, date bounds, and output path. Do not substitute date-only search semantics for the script's explicit timestamp checks.

## Prerequisites

- Network access to GitHub.
- GitHub CLI (`gh`) installed and authenticated for GitHub API access. Check with `gh auth status` before running.
- Python 3 standard library.

The script uses GitHub GraphQL search with explicit pagination. GitHub search cannot return more than 1,000 results for one query; if a queried cohort exceeds that limit, it fails rather than silently producing an incomplete report. Use a narrower cohort or an alternate full-history retrieval method in that exceptional case.

## Run

Build a JSON configuration from the current request and pass it on standard input:

```sh
printf '%s' "$CONFIG_JSON" | python3 /app/environment/skills/current/scripts/generate_report.py
```

Input schema:

```json
{
  "repository": "OWNER/REPOSITORY",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "output": "/absolute/path/to/report.json"
}
```

`start` is inclusive and `end` is exclusive, both interpreted as UTC midnight. The command writes the report atomically to `output` and emits a JSON status object to stdout. On an error it emits `{"ok": false, "error": "..."}` and exits nonzero; do not treat such an invocation as a completed artifact.

## Validation and interpretation

The generated file has exactly the requested top-level `pr` and `issue` objects and validates scalar types before it is written. It uses these deterministic conventions:

- Label matching is case-insensitive Unicode `casefold()` substring matching. An issue is counted once even if multiple labels contain the token.
- The average is rounded once, at the final aggregate, to one decimal place (half-up). If no valid merged duration exists, it is `0.0`.
- Authors are grouped by login. Deleted/null authors are represented as `<unknown>`. A tie for top contributor is broken by lexicographically smallest login.
- Search records are deduplicated by GraphQL node ID, and every fetched creation/closure timestamp is rechecked against UTC boundaries.

After a successful invocation, inspect the status object's `report` field and confirm that the target path is the artifact required by the task. Do not alter the generated JSON structure or replace live results with manually calculated values.
