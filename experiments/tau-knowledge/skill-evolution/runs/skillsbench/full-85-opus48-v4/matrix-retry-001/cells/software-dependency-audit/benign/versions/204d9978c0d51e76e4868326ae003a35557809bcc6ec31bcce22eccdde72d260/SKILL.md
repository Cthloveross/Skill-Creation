---
name: software-dependency-audit
description: >
  Audit a Node.js dependency file (npm package-lock.json) for HIGH and CRITICAL
  vulnerabilities and write a reproducible CSV report. Resolves exact installed
  versions (including transitive dependencies) from the lockfile, queries the OSV
  advisory database (api.osv.dev) for the npm ecosystem, filters findings by
  severity, and takes identifier/severity/CVSS/fixed-version/title/reference from a
  single coherent advisory record per finding. Use when a task provides a
  package-lock.json and asks for a security_audit.csv of vulnerable packages.
---

# Software dependency audit

## What this Skill does

Given an npm lockfile (`/root/package-lock.json` by default) it produces a CSV at
`/root/security_audit.csv` with exactly these columns, in this order:

```
Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url
```

Only findings whose severity is `HIGH` or `CRITICAL` are kept.

## Method (and its assumptions)

1. **Resolve installed versions first, filter later.** `scripts/lockfile.py`
   parses both lockfile formats: v2/v3 (`packages` map keyed by `node_modules/...`
   paths) and v1 (recursive `dependencies`). It returns the de-duplicated,
   sorted set of `(name, exact_version)` pairs, including transitive
   dependencies. Resolving versions and filtering by severity are kept as
   separate steps (per the background guidance).
2. **Query one coherent advisory snapshot.** `scripts/audit.py` batch-queries
   OSV (`/v1/querybatch`, ecosystem `npm`) to get vulnerability IDs per
   package/version, then fetches each record once (`/v1/vulns/{id}`). The task
   environment allows internet (`allow_internet: true`), and OSV is a consistent,
   reproducible snapshot source. For each finding **every reported field is
   taken from the same record** — the record's own aliases (CVE), its own
   `database_specific.severity`, its own CVSS vector, its own fixed-version
   event, its own `summary`, and its own reference. Fields from different
   records are never mixed.
3. **Severity + CVSS.** The severity label is taken from the record's
   `database_specific.severity` when present (`MODERATE` is normalised to
   `MEDIUM`); otherwise it is derived from the computed CVSS v3 base score.
   `scripts/cvss.py` computes the CVSS v3.0/3.1 base score deterministically from
   the record's CVSS vector string. Only `HIGH`/`CRITICAL` rows are written.
4. **Preserve missing values explicitly.** Any absent field (no fixed version,
   no computable CVSS, no CVE alias, no reference) is written as `N/A` rather than
   dropped or guessed. When no CVE alias exists the OSV/GHSA id is used as the
   identifier, and the reference falls back to the OSV vulnerability page.
5. **Deterministic output.** Rows are de-duplicated by
   `(Package, Version, CVE_ID)` and sorted by the same key so the report is
   reproducible.

## Running it

The entrypoint reads a JSON config on stdin and writes a JSON summary to stdout
while producing the CSV as a side effect.

Input JSON (all keys optional, defaults shown):
```json
{"lockfile": "/root/package-lock.json",
 "output": "/root/security_audit.csv",
 "severities": ["HIGH", "CRITICAL"]}
```

Example invocation from the Skill directory:
```bash
cd /app/environment/skills/current
echo '{"lockfile":"/root/package-lock.json","output":"/root/security_audit.csv"}' \
  | python3 scripts/audit.py
```

Output JSON on stdout looks like:
```json
{"status":"ok","output":"/root/security_audit.csv",
 "packages_scanned":123,"findings_kept":7,"rows_written":7,
 "errors":[]}
```

If OSV cannot be reached, `status` is `"network_error"` and `errors` lists the
failures; the CSV is still written with a correct header (possibly only the
header). In that case the executor should inspect connectivity before relying on
the result rather than reporting an empty audit as success.

## How the executor should use this

1. Confirm the input lockfile exists (`ls -l /root/package-lock.json`).
2. Run `scripts/audit.py` as shown; read the stdout JSON.
3. Validate the deliverable:
   - `head -1 /root/security_audit.csv` must equal
     `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`.
   - Every data row's `Severity` column must be `HIGH` or `CRITICAL`.
   - Spot-check that each row's fields come from a single advisory record
     (CVE id matches the referenced advisory URL).
   `python3 scripts/validate.py` performs these structural checks and reports
   problems as JSON (input `{"output":"/root/security_audit.csv"}`).
4. If `status` is not `ok`, surface the `errors` and retry the run; do not treat
   a header-only CSV caused by a network error as a completed audit.

## Notes / limits
- The CSV is written with Python's `csv` module, so titles containing commas or
  quotes are safely quoted; embedded newlines in titles are collapsed to spaces.
- Local workspace/linked packages without a resolved version are skipped (they
  are not third-party registry dependencies).
- Severity buckets follow CVSS v3: `0.1–3.9 LOW`, `4.0–6.9 MEDIUM`,
  `7.0–8.9 HIGH`, `9.0–10.0 CRITICAL`.
- See `references/osv-schema.md` for the OSV fields consumed.
