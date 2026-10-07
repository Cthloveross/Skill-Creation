"""Offline dependency audit entrypoint (Trivy-based).

Reads a JSON config on stdin and writes a reproducible CSV security audit as a
side effect, printing a JSON summary on stdout.

Config (all keys optional, defaults shown):
    {"lockfile": "/root/package-lock.json",
     "output": "/root/security_audit.csv",
     "severities": ["HIGH", "CRITICAL"],
     "include_dev": true,
     "trivy_bin": null,            # auto-detected with shutil.which
     "cache_dir": null}            # auto-detected offline Trivy cache

Why Trivy and offline: the task ships a *local* Trivy advisory database and the
environment may be offline. Per the background guidance we use the locally
available advisory snapshot rather than silently mixing it with partial network
results, so results are reproducible from one coherent source. We therefore run
Trivy with `--skip-db-update --offline-scan` against the pre-seeded cache.

Output columns (exact order):
    Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url

Each row's fields come from a single Trivy vulnerability record. The severity
label is Trivy's resolved `Severity` (driven by its `SeveritySource`); the CVSS
score is taken from that same source when available (coherent severity+score),
falling back to nvd/ghsa/redhat otherwise. Missing values are written as `N/A`.
Rows are de-duplicated by (Package, Version, CVE_ID) and sorted by that key.
"""
import csv
import json
import os
import shutil
import subprocess
import sys

EXPECTED = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score",
            "Fixed_Version", "Title", "Url"]

# Candidate offline Trivy cache directories (dir that CONTAINS the `db` folder).
CACHE_CANDIDATES = [
    "/root/.cache/trivy",
    "/root/trivy-cache",
    os.path.join(os.path.expanduser("~"), ".cache", "trivy"),
]

NA = "N/A"


def _find_cache_dir(explicit=None):
    cands = ([explicit] if explicit else []) + CACHE_CANDIDATES
    for c in cands:
        if c and os.path.exists(os.path.join(c, "db", "trivy.db")):
            return c
    return None


def _score_from_record(vuln):
    """Pick a CVSS score coherently: same source as the severity label first,
    then a deterministic nvd>ghsa>redhat fallback. Returns a string or N/A."""
    cvss = vuln.get("CVSS") or {}

    def pick(src):
        d = cvss.get(src) or {}
        s = d.get("V3Score")
        if s is None:
            s = d.get("V2Score")
        return s

    order = []
    sev_src = vuln.get("SeveritySource")
    if sev_src:
        order.append(sev_src)
    for src in ("nvd", "ghsa", "redhat"):
        if src not in order:
            order.append(src)
    for src in order:
        s = pick(src)
        if s is not None:
            # keep Trivy's numeric formatting (e.g. 7.5, 9.4) without trailing .0 noise
            if isinstance(s, float) and s.is_integer():
                return str(int(s))
            return str(s)
    return NA


def _title(vuln):
    t = (vuln.get("Title") or "").strip()
    if not t:
        t = (vuln.get("Description") or "").strip()
    if not t:
        return NA
    return " ".join(t.split())  # collapse newlines/whitespace


def _url(vuln):
    u = (vuln.get("PrimaryURL") or "").strip()
    if u:
        return u
    refs = vuln.get("References") or []
    for r in refs:
        if r:
            return r
    vid = vuln.get("VulnerabilityID", "")
    if vid.upper().startswith("CVE-"):
        return "https://nvd.nist.gov/vuln/detail/" + vid
    return NA


def _cve_id(vuln):
    vid = (vuln.get("VulnerabilityID") or "").strip()
    if vid.upper().startswith("CVE-"):
        return vid
    # prefer a CVE alias from VendorIDs if the primary id is a GHSA/other
    for vid2 in (vuln.get("VendorIDs") or []):
        if vid2.upper().startswith("CVE-"):
            return vid2
    return vid or NA


def run_trivy(lockfile, severities, include_dev, trivy_bin, cache_dir):
    trivy_bin = trivy_bin or shutil.which("trivy")
    if not trivy_bin:
        return None, ["trivy binary not found on PATH"]
    cache_dir = _find_cache_dir(cache_dir)
    if not cache_dir:
        return None, ["offline Trivy DB not found (looked for */db/trivy.db)"]
    cmd = [trivy_bin, "fs", "--skip-db-update", "--offline-scan",
           "--scanners", "vuln",
           "--severity", ",".join(s.upper() for s in severities),
           "--format", "json", "--quiet",
           "--cache-dir", cache_dir]
    if include_dev:
        cmd.append("--include-dev-deps")
    cmd.append(lockfile)
    env = dict(os.environ)
    env.setdefault("TRIVY_DISABLE_VEX_NOTICE", "true")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=540)
    except Exception as exc:  # noqa: BLE001
        return None, ["trivy invocation failed: %s" % exc]
    if proc.returncode != 0:
        return None, ["trivy exit %d: %s" % (proc.returncode,
                                             proc.stderr.strip()[:500])]
    try:
        return json.loads(proc.stdout), []
    except json.JSONDecodeError as exc:
        return None, ["could not parse trivy json: %s" % exc]


def extract_rows(trivy_json, want_sev):
    rows = []
    for result in (trivy_json.get("Results") or []):
        for vuln in (result.get("Vulnerabilities") or []):
            sev = (vuln.get("Severity") or "").upper()
            if sev not in want_sev:
                continue
            rows.append({
                "Package": vuln.get("PkgName", "") or NA,
                "Version": vuln.get("InstalledVersion", "") or NA,
                "CVE_ID": _cve_id(vuln),
                "Severity": sev,
                "CVSS_Score": _score_from_record(vuln),
                "Fixed_Version": (vuln.get("FixedVersion") or "").strip() or NA,
                "Title": _title(vuln),
                "Url": _url(vuln),
            })
    # de-duplicate by (Package, Version, CVE_ID), keep first, then sort
    seen = {}
    for r in rows:
        key = (r["Package"], r["Version"], r["CVE_ID"])
        if key not in seen:
            seen[key] = r
    out = list(seen.values())
    out.sort(key=lambda r: (r["Package"].lower(), r["Version"], r["CVE_ID"]))
    return out


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(EXPECTED)
        for r in rows:
            w.writerow([r[c] for c in EXPECTED])


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        cfg = {}
    lockfile = cfg.get("lockfile", "/root/package-lock.json")
    output = cfg.get("output", "/root/security_audit.csv")
    severities = cfg.get("severities", ["HIGH", "CRITICAL"])
    include_dev = cfg.get("include_dev", True)
    want_sev = {s.upper() for s in severities}

    if not os.path.exists(lockfile):
        print(json.dumps({"status": "input_missing", "output": output,
                          "errors": ["lockfile not found: %s" % lockfile]}))
        return

    data, errors = run_trivy(lockfile, severities, include_dev,
                             cfg.get("trivy_bin"), cfg.get("cache_dir"))
    if data is None:
        # Do NOT silently fall back to network results; surface the failure and
        # still write a valid header so the contract (file + columns) holds.
        write_csv(output, [])
        print(json.dumps({"status": "scan_error", "output": output,
                          "rows_written": 0, "errors": errors}))
        return

    rows = extract_rows(data, want_sev)
    write_csv(output, rows)
    print(json.dumps({"status": "ok", "output": output,
                      "findings_kept": len(rows), "rows_written": len(rows),
                      "errors": []}))


if __name__ == "__main__":
    main()
