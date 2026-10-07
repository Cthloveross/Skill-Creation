---
name: offline-npm-security-audit
description: Produce a reproducible CSV audit of HIGH and CRITICAL vulnerabilities in an npm package-lock.json using an explicitly supplied offline npm audit report or npm's offline cache. Use when network access is unavailable and the required result includes exact installed versions and coherent advisory details.
---

# Offline npm dependency security audit

This Skill audits the exact resolved dependency graph in an npm lockfile, including transitive packages. It does **not** contact an advisory service: when it invokes npm, it uses `npm audit --offline --package-lock-only --json`. An offline advisory cache, or a previously generated local npm audit JSON report, is therefore a prerequisite.

## Inputs and prerequisites

1. Confirm that the lockfile is the dependency snapshot to audit. The default is `/root/package-lock.json`.
2. Prefer an audit JSON report generated from that exact lockfile and the intended local advisory snapshot. Do not combine a report from one dependency snapshot with another lockfile.
3. If no report is supplied, ensure npm and all required advisory data are locally available. The Skill runs npm only with `--offline`; it never falls back to network access.
4. If npm reports an offline-cache or audit failure, stop and obtain a complete local advisory report/database. Do not create a header-only report as a substitute for a failed scan.
5. A reportable record needs an actual CVE, numeric CVSS base score, non-placeholder title, and absolute HTTP(S) advisory URL. npm v2 summaries containing only numeric or GHSA source references are insufficient unless their `via` entries include complete advisory objects.

The supplied report may use npm's legacy `advisories` format or current `vulnerabilities` format. Each emitted CSV row takes its CVE, severity, score, remediation, title, and URL from **one advisory record**. Fields from aliases or package summaries are never mixed into another advisory.

## Run

Invoke `scripts/audit_npm_lock.py` with a JSON object on stdin. For the task paths:

```json
{
  "lockfile": "/root/package-lock.json",
  "output_csv": "/root/security_audit.csv"
}
```

To normalize a saved local audit report instead of invoking npm:

```json
{
  "lockfile": "/root/package-lock.json",
  "audit_json_path": "/path/to/local/npm-audit.json",
  "output_csv": "/root/security_audit.csv"
}
```

Input fields:

- `lockfile` (string, optional): package lock path; defaults to `/root/package-lock.json`.
- `output_csv` (string, optional): destination; defaults to `/root/security_audit.csv`.
- `audit_json_path` (string, optional): local npm audit JSON. If provided, npm is not invoked.
- `npm_executable` (string, optional): executable when no saved report is given; defaults to `npm`.

The script emits a JSON status object on stdout:

- success: `{"ok": true, "output_csv": "...", "rows": 0, "provenance": {...}, "skipped": {...}}`
- prerequisite or parse error: `{"ok": false, "error": "..."}` and a nonzero exit status.

## Method

The script extracts exact installed versions from `packages` entries in lockfile v2/v3 and from nested dependencies in v1-compatible locks. It expands audit graph nodes where available and filters advisory records by their source severity, keeping only `HIGH` and `CRITICAL`.

Before a finding is emitted, it validates the source CVSS score and the source severity together: `HIGH` requires a score from 7.0 through 10.0 and `CRITICAL` requires a score from 9.0 through 10.0. An advisory whose own severity and score conflict (for example, `CRITICAL` with 5.4) is skipped rather than relabeling the advisory or combining it with a different record. The `skipped` status counts disclose omitted incomplete or inconsistent candidate records.

The output is UTF-8 CSV with exactly this header:

```text
Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url
```

`Fixed_Version` is `N/A` only when the source says no remediation is available. Findings are de-duplicated by `(Package, Version, CVE_ID)` and sorted deterministically. A header-only CSV is valid only when a completed advisory scan yields no reportable HIGH/CRITICAL CVE findings.

## Validation

After success, verify that `/root/security_audit.csv` exists, parses as UTF-8 CSV, and has exactly the required columns in order. For every row, confirm that the package/version is in the lockfile, the CVE has the `CVE-YYYY-NNNN...` shape, the severity is `HIGH` or `CRITICAL`, the numeric score is within the corresponding CVSS band, and the URL is absolute HTTP(S). Retain the lockfile and audit JSON/cache snapshot named in `provenance` for reproducibility.
