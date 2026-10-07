"""Dependency security audit entrypoint.

Reads a JSON config on stdin:
  {"lockfile": "/root/package-lock.json",
   "output": "/root/security_audit.csv",
   "severities": ["HIGH", "CRITICAL"]}
All keys are optional; defaults match the public task.

Writes the CSV report as a side effect and prints a JSON summary on stdout:
  {"status": "ok"|"network_error", "output": path, "packages_scanned": int,
   "findings_kept": int, "rows_written": int, "errors": [...]}

For each finding, identifier/severity/CVSS/fixed-version/title/reference are all
taken from the SAME OSV advisory record. Missing values are written as N/A.
Rows are de-duplicated by (Package, Version, CVE_ID) and sorted deterministically.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lockfile import load_packages  # noqa: E402
from cvss import base_score_from_vector, severity_bucket  # noqa: E402

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
COLUMNS = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score",
           "Fixed_Version", "Title", "Url"]
NA = "N/A"


def _post(url, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _retry(fn, retries=3, delay=2):
    last = None
    for attempt in range(retries):
        try:
            return fn(), None
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(delay)
    return None, last


def query_vuln_ids(packages, errors):
    """Return set of (name, version, vuln_id) via OSV querybatch."""
    pairs = set()
    chunk = 200
    for i in range(0, len(packages), chunk):
        batch = packages[i:i + chunk]
        payload = {"queries": [
            {"package": {"name": n, "ecosystem": "npm"}, "version": v}
            for (n, v) in batch]}
        res, err = _retry(lambda p=payload: _post(OSV_BATCH, p))
        if err is not None:
            errors.append(f"querybatch failed: {err}")
            continue
        results = res.get("results", []) if isinstance(res, dict) else []
        for (n, v), entry in zip(batch, results):
            if not isinstance(entry, dict):
                continue
            for vuln in entry.get("vulns", []) or []:
                vid = vuln.get("id")
                if vid:
                    pairs.add((n, v, vid))
    return pairs


def fetch_records(ids, errors):
    cache = {}
    for vid in sorted({vid for (_, _, vid) in ids}):
        rec, err = _retry(lambda u=OSV_VULN + vid: _get(u))
        if err is not None:
            errors.append(f"fetch {vid} failed: {err}")
            cache[vid] = None
        else:
            cache[vid] = rec
    return cache


def _cve_from(rec, vid):
    aliases = rec.get("aliases", []) or []
    cves = sorted(a for a in aliases if isinstance(a, str) and a.startswith("CVE-"))
    return cves[0] if cves else vid


def _cvss_score(rec):
    for sev in rec.get("severity", []) or []:
        if str(sev.get("type", "")).startswith("CVSS_V3"):
            score = base_score_from_vector(sev.get("score"))
            if score is not None:
                return score
    return None


def _severity_label(rec, score):
    db = (rec.get("database_specific") or {}).get("severity")
    if isinstance(db, str) and db.strip():
        label = db.strip().upper()
        if label == "MODERATE":
            label = "MEDIUM"
        return label
    return severity_bucket(score)


def _fixed_version(rec, name):
    for aff in rec.get("affected", []) or []:
        pkg = aff.get("package", {}) or {}
        if pkg.get("ecosystem") == "npm" and pkg.get("name") == name:
            for rng in aff.get("ranges", []) or []:
                for ev in rng.get("events", []) or []:
                    if "fixed" in ev and ev["fixed"]:
                        return ev["fixed"]
    return None


def _reference(rec, vid):
    refs = rec.get("references", []) or []
    advisory = [r.get("url") for r in refs if r.get("type") == "ADVISORY" and r.get("url")]
    if advisory:
        return advisory[0]
    for r in refs:
        if r.get("url"):
            return r["url"]
    return f"https://osv.dev/vulnerability/{vid}"


def _title(rec):
    summary = rec.get("summary")
    if summary:
        return " ".join(str(summary).split())
    details = rec.get("details")
    if details:
        return " ".join(str(details).split())[:200]
    return NA


def build_rows(ids, cache, severities):
    want = {s.upper() for s in severities}
    rows = {}
    for (name, version, vid) in sorted(ids):
        rec = cache.get(vid)
        if not rec:
            continue
        score = _cvss_score(rec)
        label = _severity_label(rec, score)
        if label not in want:
            continue
        cve = _cve_from(rec, vid)
        key = (name, version, cve)
        if key in rows:
            continue
        fixed = _fixed_version(rec, name)
        rows[key] = {
            "Package": name,
            "Version": version,
            "CVE_ID": cve,
            "Severity": label,
            "CVSS_Score": (f"{score:.1f}" if score is not None else NA),
            "Fixed_Version": fixed if fixed else NA,
            "Title": _title(rec),
            "Url": _reference(rec, vid),
        }
    return [rows[k] for k in sorted(rows.keys())]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        cfg = {}
    lockfile = cfg.get("lockfile", "/root/package-lock.json")
    output = cfg.get("output", "/root/security_audit.csv")
    severities = cfg.get("severities", ["HIGH", "CRITICAL"])

    errors = []
    packages = load_packages(lockfile)
    ids = query_vuln_ids(packages, errors)
    cache = fetch_records(ids, errors)
    rows = build_rows(ids, cache, severities)
    write_csv(output, rows)

    status = "ok" if not errors else "network_error"
    print(json.dumps({
        "status": status,
        "output": output,
        "packages_scanned": len(packages),
        "findings_kept": len(rows),
        "rows_written": len(rows),
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
