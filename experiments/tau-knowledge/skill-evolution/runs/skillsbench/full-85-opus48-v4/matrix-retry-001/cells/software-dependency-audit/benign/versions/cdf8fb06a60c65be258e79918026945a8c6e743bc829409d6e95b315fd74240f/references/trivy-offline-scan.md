# Trivy offline npm scan — fields consumed

Command (as issued by `scripts/audit.py`):

```
trivy fs --skip-db-update --offline-scan --scanners vuln \
  --severity HIGH,CRITICAL --include-dev-deps \
  --format json --quiet --cache-dir <dir-with-db/trivy.db> <package-lock.json>
```

- `--skip-db-update --offline-scan`: never touch the network; use the local DB.
- `--include-dev-deps`: include dev dependencies (still third-party code).
- `--cache-dir`: the directory that contains `db/trivy.db` (auto-detected).

## JSON shape and the fields we map

```
Results[].Vulnerabilities[]:
  PkgName            -> Package
  InstalledVersion   -> Version
  VulnerabilityID    -> CVE_ID        (CVE; else a CVE from VendorIDs; else the id)
  Severity           -> Severity      (HIGH/CRITICAL filter; from SeveritySource)
  SeveritySource     -> which CVSS source to prefer for coherence
  CVSS[src].V3Score  -> CVSS_Score    (prefer SeveritySource, else nvd>ghsa>redhat;
                                        V2Score only if no V3Score; N/A if none)
  FixedVersion       -> Fixed_Version (verbatim; N/A if empty)
  Title / Description-> Title         (Title preferred; whitespace collapsed)
  PrimaryURL         -> Url           (else first Reference; else nvd.nist.gov; else N/A)
```

Each row's fields all come from the *same* vulnerability record. Rows are
de-duplicated by `(Package, Version, CVE_ID)` and sorted case-insensitively.

## Reproducibility note

The DB snapshot is pinned by the environment (see `trivy --version` →
"Vulnerability DB UpdatedAt"). Re-running the same command against the same DB
yields the same rows. Do not fall back to live network advisory APIs: that mixes
snapshots and makes the report non-reproducible (future-dated advisories appear
and disappear).
