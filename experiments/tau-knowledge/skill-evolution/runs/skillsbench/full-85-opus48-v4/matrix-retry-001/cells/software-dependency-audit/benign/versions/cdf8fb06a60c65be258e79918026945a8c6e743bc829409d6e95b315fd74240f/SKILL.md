---
name: software-dependency-audit
description: >
  Audit a Node.js dependency file (npm package-lock.json) for HIGH and CRITICAL
  vulnerabilities and write a reproducible CSV report. Scans the lockfile with
  the locally installed Trivy scanner against its pre-seeded OFFLINE advisory
  database (no network), filters findings by severity, and takes
  identifier/severity/CVSS/fixed-version/title/reference from a single coherent
  advisory record per finding. Use when a task provides a package-lock.json and
  asks for a security_audit.csv of vulnerable packages.
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

1. **Use the local offline advisory snapshot — do not mix in network results.**
   The task environment ships a pre-seeded Trivy vulnerability database (e.g.
   `/root/.cache/trivy/db/trivy.db`, also linked at `/root/trivy-cache`). Per the
   background guidance, in an offline environment we use that locally available
   data rather than silently mixing it with partial network results, which keeps
   the report reproducible and attributable to one snapshot. `scripts/audit.py`
   runs `trivy fs --skip-db-update --offline-scan` so it never updates or hits
   the network, regardless of whether internet happens to be allowed.
2. **Resolve installed versions first, filter later.** Trivy parses the lockfile
   (both v1 `dependencies` and v2/v3 `packages`), resolving the exact installed
   version of every package including transitive and dev dependencies. We pass
   `--include-dev-deps` so *all* third-party dependencies present in the lockfile
   are considered (dev dependencies are still third-party code). Severity
   filtering (`--severity HIGH,CRITICAL`) is applied as a separate step after
   resolution.
3. **One coherent source record per finding.** For each Trivy vulnerability
   record every reported field is taken from that same record: its
   `VulnerabilityID` (a CVE; a CVE from `VendorIDs` is used only if the primary
   id is not a CVE), its resolved `Severity`, its CVSS score, its
   `FixedVersion`, its `Title`, and its `PrimaryURL`. Fields from different
   records are never mixed.
4. **Severity + CVSS stay coherent.** Trivy's `Severity` label (driven by its
   `SeveritySource`) decides HIGH/CRITICAL inclusion. The CVSS score is taken
   from that *same* source when it publishes one, else from a deterministic
   `nvd > ghsa > redhat` fallback (the task explicitly allows a score from NVD,
   GHSA, or RedHat). Note Trivy may rate a record HIGH/CRITICAL from one source
   while only another source publishes a numeric score; the label still governs
   inclusion.
5. **Preserve missing values explicitly.** Any absent field (no fixed version,
   no published CVSS score, no reference) is written as `N/A` rather than dropped
   or guessed.
6. **Deterministic output.** Rows are de-duplicated by
   `(Package, Version, CVE_ID)` and sorted case-insensitively by the same key so
   the report is reproducible. The same package at two installed versions yields
   two rows.

## Running it

The entrypoint reads a JSON config on stdin and writes a JSON summary to stdout
while producing the CSV as a side effect.

Input JSON (all keys optional, defaults shown):
```json
{"lockfile": "/root/package-lock.json",
 "output": "/root/security_audit.csv",
 "severities": ["HIGH", "CRITICAL"],
 "include_dev": true,
 "trivy_bin": null,
 "cache_dir": null}
```

`trivy_bin`/`cache_dir` are auto-detected (`shutil.which("trivy")` and the first
cache directory that contains `db/trivy.db` among `/root/.cache/trivy`,
`/root/trivy-cache`, `~/.cache/trivy`). Set them only to override.

Example invocation from the Skill directory:
```bash
cd /app/environment/skills/current
echo '{"lockfile":"/root/package-lock.json","output":"/root/security_audit.csv"}' \
  | python3 scripts/audit.py
```

Output JSON on stdout looks like:
```json
{"status":"ok","output":"/root/security_audit.csv",
 "findings_kept":22,"rows_written":22,"errors":[]}
```

Failure modes are explicit:
- `"status":"input_missing"` — the lockfile path does not exist.
- `"status":"scan_error"` — Trivy is not installed or its offline DB was not
  found, or the scan failed; `errors` explains why. A valid header-only CSV is
  still written so the file/column contract holds, but the executor must NOT
  treat a header-only CSV from a scan error as a completed audit — fix Trivy /
  the cache and rerun.

## How the executor should use this

1. Confirm the input lockfile exists (`ls -l /root/package-lock.json`) and that
   Trivy + its offline DB are present (`trivy --version`;
   `ls /root/.cache/trivy/db/trivy.db`).
2. Run `scripts/audit.py` as shown; read the stdout JSON and confirm
   `"status":"ok"`.
3. Validate the deliverable with `scripts/validate.py`
   (input `{"output":"/root/security_audit.csv"}`), which checks:
   - header equals
     `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`;
   - every data row's `Severity` is `HIGH` or `CRITICAL`;
   - no empty cells (empties must be `N/A`);
   - no duplicate `(Package, Version, CVE_ID)` rows.
4. If `status` is not `ok`, surface `errors` and fix the environment before
   relying on the result; never report a header-only CSV as success.

## Notes / limits
- The scan is fully offline (`--skip-db-update --offline-scan`); results reflect
  the shipped DB snapshot and are reproducible for that snapshot.
- The CSV is written with Python's `csv` module, so titles and multi-value fixed
  versions containing commas are safely quoted; embedded newlines in titles are
  collapsed to spaces.
- `Fixed_Version` preserves Trivy's value verbatim (which may list fixes for
  several release branches, e.g. `"7.5.2, 6.3.1, 5.7.2"`); `N/A` when no fix is
  known.
- Set `include_dev` to `false` only if a task explicitly scopes the audit to
  production dependencies.
- See `references/trivy-offline-scan.md` for the exact Trivy fields consumed.
