---
name: npm-high-critical-security-audit
description: Audit an npm package-lock.json resolved dependency graph and write a reproducible CSV of HIGH and CRITICAL vulnerabilities, with CVE, CVSS, remediation, and advisory provenance. Use when an npm dependency audit is requested and npm/network or an OSV-compatible advisory service may be available.
---

# Npm high/critical dependency audit

Use `scripts/audit_npm_lock.py` to inspect the exact versions recorded in a
`package-lock.json`, invoke npm's audit service, enrich matching findings from
OSV, and produce the required CSV. The script includes transitive dependencies;
it does not infer versions from semver declarations.

## Run

The script reads one JSON object from standard input and writes a JSON execution
summary to standard output. Its input schema is:

- `lock_path` (optional string): package lock path; defaults to
  `/root/package-lock.json`.
- `output_path` (optional string): output CSV path; defaults to
  `/root/security_audit.csv`.
- `npm_bin` (optional string): npm executable; defaults to `npm`.
- `osv_url` (optional string): OSV query-batch endpoint; defaults to the public
  `https://api.osv.dev/v1/querybatch` endpoint. Set to an internally provided
  compatible endpoint when auditing offline.
- `timeout` (optional positive number): per subprocess/request timeout in
  seconds; defaults to 120.

Example:

```sh
python3 /app/environment/skills/current/scripts/audit_npm_lock.py <<'JSON'
{"lock_path":"/root/package-lock.json","output_path":"/root/security_audit.csv"}
JSON
```

The executor should then confirm that `/root/security_audit.csv` exists, has
exactly these columns in this order,

`Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`

and that every row has severity `HIGH` or `CRITICAL`. An empty CSV containing
only the header is a valid result when no qualifying findings are returned.

## Method and provenance

1. The helper parses lockfile v1, v2, and v3 layouts to map installed package
   names and exact versions, including nested/transitive installations.
2. It runs `npm audit --package-lock-only --json` in the lockfile directory.
   npm audit findings are the initial applicability source. npm may exit nonzero
   when it finds vulnerabilities; JSON output is still consumed.
3. For vulnerable exact package versions, it queries OSV in batches. When OSV
   returns a HIGH/CRITICAL record, each output row is populated entirely from
   that one OSV record: aliases, severity/CVSS, fixed range event, summary, and
   reference. This avoids mixing fields across related advisory aliases.
4. If an npm advisory cannot be matched to an OSV record, the script emits the
   coherent npm advisory fields instead. Fields npm does not publish (including
   a CVE or a fixed version) are explicitly `N/A`; it never borrows them from a
   different record.
5. Rows are deduplicated and sorted by package, installed version, advisory
   identity, and CVE field for reproducibility. Values containing multiple CVE
   aliases are semicolon-separated in stable order.

If npm is unavailable or its response is invalid, the script can still query
OSV for every exact lockfile package version. It reports only OSV records whose
own metadata or CVSS data establishes HIGH/CRITICAL severity. If neither source
is reachable, it writes the header-only CSV and returns a summary containing
warnings; this is an observable incomplete-data condition, not a claim that the
project is vulnerability-free.
