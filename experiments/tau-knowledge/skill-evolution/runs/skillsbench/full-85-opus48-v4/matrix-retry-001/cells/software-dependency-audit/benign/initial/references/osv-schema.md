# OSV record fields consumed by this Skill

The audit queries https://api.osv.dev. Two endpoints are used:

- `POST /v1/querybatch` with body
  `{"queries":[{"package":{"name":<pkg>,"ecosystem":"npm"},"version":<ver>}, ...]}`.
  The response `results` array is positionally aligned with the queries; each
  entry may contain `vulns:[{"id":...,"modified":...}]`.
- `GET /v1/vulns/{id}` returns the full advisory record.

From each full record (one coherent source per finding) the Skill reads:

- `id` — e.g. `GHSA-xxxx-...`; used as the identifier when no CVE alias exists,
  and for the fallback reference URL `https://osv.dev/vulnerability/{id}`.
- `aliases` — list; the first `CVE-...` (sorted) becomes `CVE_ID`.
- `database_specific.severity` — qualitative label
  (`LOW`/`MODERATE`/`HIGH`/`CRITICAL`); `MODERATE` maps to `MEDIUM`. This is the
  preferred severity source. Only `HIGH`/`CRITICAL` are reported.
- `severity[]` — entries like `{"type":"CVSS_V3","score":"CVSS:3.1/AV:N/..."}`.
  The `score` is a vector string; the numeric base score is computed from it.
  If no CVSS v3 vector is present, the CVSS column is `N/A` and the severity
  falls back to the qualitative label (or the bucket of the computed score).
- `affected[].package` + `affected[].ranges[].events[].fixed` — the fixed
  version for the matching npm package; `N/A` when absent.
- `summary` (preferred) or `details` — the title/description (whitespace
  collapsed).
- `references[]` — the `ADVISORY` url is preferred, else the first url, else the
  OSV vulnerability page.

All fields for a single CSV row come from the same record so that identifier,
severity, score, remediation (fixed version), title and reference stay mutually
consistent. Missing values are written explicitly as `N/A`, and rows are
de-duplicated by `(Package, Version, CVE_ID)` and sorted for reproducibility.
