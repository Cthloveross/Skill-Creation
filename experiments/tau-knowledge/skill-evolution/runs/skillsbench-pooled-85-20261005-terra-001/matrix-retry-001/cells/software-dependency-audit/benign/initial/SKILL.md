---
name: offline-npm-security-audit
description: Produce a reproducible CSV audit of HIGH and CRITICAL vulnerabilities in an npm package-lock.json using an explicitly supplied offline npm audit report or npm's offline cache. Use when network access is unavailable and the required result includes installed versions and advisory details.
---

# Offline npm dependency security audit

This Skill audits the exact resolved dependency graph in a lockfile, including transitive packages. It does **not** contact an advisory service: when it invokes npm, it uses `npm audit --offline --package-lock-only --json`. Therefore an offline advisory cache (or a previously generated offline audit JSON report) is a prerequisite.

## Inputs and prerequisite checks

1. Confirm the lockfile is the dependency snapshot to audit. The default is `/root/package-lock.json`.
2. Prefer supplying an audit JSON report created from that same lockfile and the intended local advisory snapshot. Do not combine an audit report from one lockfile or database snapshot with another lockfile.
3. If no report is supplied, ensure npm and its required advisory data are available locally. The script will run npm only with `--offline`; it never falls back to a networked audit.
4. If npm reports an offline-cache or audit failure, stop and obtain a complete local advisory report/database. Do not treat that failure as a clean audit and do not create an empty findings report as a substitute.

The supplied report must be npm audit JSON in either the legacy `advisories` form or the current `vulnerabilities` form. Legacy advisories contain the fullest advisory metadata. Current reports are supported when their `via` records include advisory objects. A current npm summary containing only numeric/source references cannot by itself provide the requested CVE, title, score, and URL; such incomplete entries are retained with explicit `N/A` cells rather than guessed from an unrelated advisory.

## Run

Run the entrypoint with JSON on stdin. For the task paths:

```json
{
  "lockfile": "/root/package-lock.json",
  "output_csv": "/root/security_audit.csv"
}
```

To use a saved local report instead of invoking npm:

```json
{
  "lockfile": "/root/package-lock.json",
  "audit_json_path": "/path/to/local/npm-audit.json",
  "output_csv": "/root/security_audit.csv"
}
```

Invoke `scripts/audit_npm_lock.py`. Its stdout is a JSON status object:

- success: `{"ok": true, "output_csv": ..., "rows": ..., "provenance": ...}`
- prerequisite/parse failure: `{"ok": false, "error": ...}` and a nonzero exit status.

The input object fields are:

- `lockfile` (string, optional): package lock path; defaults to `/root/package-lock.json`.
- `output_csv` (string, optional): destination; defaults to `/root/security_audit.csv`.
- `audit_json_path` (string, optional): a local npm audit JSON report. If present, npm is not run.
- `npm_executable` (string, optional): npm executable to use when no report is supplied; defaults to `npm`.

## Method

The script reads exact installed versions from lockfile package entries (and supports lockfile v1 nested dependencies). It parses audit records, expands all affected installed node paths, and keeps only source-record severities `high` and `critical`. Each CSV row uses fields from a single advisory record. It extracts CVE aliases only when an actual `CVE-YYYY-NNNN...` identifier is present; unknown data is represented as `N/A`. A no-fix result is `N/A`.

The output is UTF-8 CSV with exactly this header:

```text
Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url
```

Rows are de-duplicated by their complete reported values and sorted deterministically by severity, package, installed version, CVE, title, and URL. A header-only CSV is valid when the completed advisory scan has no HIGH/CRITICAL findings.

## Validation

After a successful run, verify that `/root/security_audit.csv` exists, is parseable as CSV, has exactly the eight required columns in the required order, and every `Severity` is `HIGH` or `CRITICAL`. Review the returned provenance and retain the lockfile plus audit JSON/cache snapshot so the result can be reproduced. `N/A` is an explicit missing-value marker, not evidence that a field was searched online.
