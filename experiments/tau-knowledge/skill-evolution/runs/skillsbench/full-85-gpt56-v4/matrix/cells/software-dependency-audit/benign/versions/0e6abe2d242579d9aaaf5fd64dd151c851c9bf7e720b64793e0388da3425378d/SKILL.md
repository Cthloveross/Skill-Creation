---
name: npm-high-critical-security-audit
description: Audit exact installed npm dependencies in a package-lock.json against OSV advisory records and write a deterministic CSV containing only HIGH and CRITICAL findings. Use for reproducible dependency vulnerability reports that require package/version, CVE or advisory identifier, severity, CVSS, remediation, title, and URL.
---

# npm HIGH/CRITICAL dependency audit

This Skill resolves package names and exact installed versions from `package-lock.json`, including nested/transitive packages, then queries one coherent advisory source (OSV) for each exact npm package/version. It does **not** combine title, severity, remediation, and references from different advisory sources.

## Runtime requirements

* Python 3 standard library.
* Network access to the OSV API for a live scan, or a complete previously saved OSV snapshot for an offline scan.
* The lockfile must be a valid npm lockfile containing exact `version` values. Lockfile versions 1, 2, and 3 are supported.

## Run

Send one JSON object on stdin. For the requested task, run from any directory with paths supplied explicitly:

```sh
python3 /app/environment/skills/current/scripts/audit_npm.py <<'JSON'
{"lockfile":"/root/package-lock.json","output":"/root/security_audit.csv","provenance":"/root/security_audit.provenance.json"}
JSON
```

Input schema:

* `lockfile` (required): path to package-lock JSON.
* `output` (required): CSV destination.
* `provenance` (optional): destination for a JSON record of the OSV endpoint/snapshot hash, package count, and selected advisory IDs.
* `snapshot` (optional): path to a complete snapshot made with `save_snapshot`. When present no network is used.
* `save_snapshot` (optional): where to save the exact package/version-to-OSV-results mapping returned by a live scan. This enables a later offline repeat.
* `endpoint` (optional): OSV querybatch endpoint; defaults to `https://api.osv.dev/v1/querybatch`.

The script emits a JSON summary on stdout. It writes CSV atomically only after all requested OSV query batches have been obtained and interpreted. A failed or incomplete advisory query is an error rather than a silently partial report.

The output header is exactly:

`Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`

`CVE_ID` is the lexicographically first CVE alias of the OSV record. If the record has no CVE alias, its stable OSV/GHSA identifier is used so that the finding remains identifiable. Missing score, fix, summary, or reference values are written as `N/A`.

## Offline reproducibility

For an offline run, first capture a live snapshot using `save_snapshot`, then provide that file as `snapshot` on later runs. A snapshot must contain an entry for every exact package/version in the lockfile, including entries with an empty list; this prevents an incomplete cache from being presented as a complete audit. Do not mix a partial snapshot with live query results in one report.

## Severity and remediation method

The script uses OSV's ecosystem/database severity when supplied. Otherwise it derives HIGH (7.0–8.9) or CRITICAL (9.0–10.0) from an OSV CVSS v3 vector. CVSS scores are calculated from the vector using the CVSS v3 base-score formula. Only records classified HIGH or CRITICAL are retained.

For a vulnerable package version, a fixed version is taken only from the matching OSV affected-range interval. Thus a fixed release from an unrelated record is never substituted. Rows are deduplicated by package, installed version, and OSV advisory ID, and are sorted deterministically.

## Validate

After the audit succeeds, validate the deliverable without changing it:

```sh
python3 /app/environment/skills/current/scripts/validate_audit_csv.py <<'JSON'
{"csv":"/root/security_audit.csv"}
JSON
```

The validator checks the required header, eight fields per row, nonempty package/version/identifier, permitted severities, and that only HIGH/CRITICAL rows are present. Review the provenance JSON with the CSV when explaining which advisory snapshot produced the report.
