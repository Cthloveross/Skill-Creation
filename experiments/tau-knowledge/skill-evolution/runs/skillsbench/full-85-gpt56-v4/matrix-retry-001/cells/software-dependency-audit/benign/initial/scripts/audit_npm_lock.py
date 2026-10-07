#!/usr/bin/env python3
"""Create a high/critical npm dependency audit CSV from a package-lock file.

stdin: JSON options documented in SKILL.md
stdout: JSON {output_path, rows, warnings, audit_available, osv_available}
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict

HEADER = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score", "Fixed_Version", "Title", "Url"]
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
GHSA_RE = re.compile(r"GHSA-[23456789cfghjmpqrvwx]{4}-[23456789cfghjmpqrvwx]{4}-[23456789cfghjmpqrvwx]{4}", re.I)


def na(value):
    if value is None or value == "":
        return "N/A"
    return str(value).replace("\x00", " ").strip() or "N/A"


def installed_packages(lock):
    """Return name -> sorted exact versions, supporting lockfile versions 1-3."""
    found = defaultdict(set)
    packages = lock.get("packages")
    if isinstance(packages, dict):
        for path, info in packages.items():
            if not path or not isinstance(info, dict) or info.get("link"):
                continue
            version = info.get("version")
            if not isinstance(version, str) or not version:
                continue
            name = info.get("name")
            if not name:
                marker = "node_modules/"
                pos = path.rfind(marker)
                if pos >= 0:
                    tail = path[pos + len(marker):]
                    if tail.startswith("@"):
                        name = "/".join(tail.split("/")[:2])
                    else:
                        name = tail.split("/")[0]
            if name:
                found[str(name)].add(version)
    def walk(deps):
        if not isinstance(deps, dict):
            return
        for name, info in deps.items():
            if not isinstance(info, dict):
                continue
            version = info.get("version")
            if isinstance(version, str) and version:
                found[name].add(version)
            walk(info.get("dependencies"))
    walk(lock.get("dependencies"))
    return {name: sorted(versions) for name, versions in found.items()}


def run_npm_audit(lock_path, npm_bin, timeout, warnings):
    command = [npm_bin, "audit", "--package-lock-only", "--json"]
    try:
        proc = subprocess.run(command, cwd=os.path.dirname(os.path.abspath(lock_path)) or ".",
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        warnings.append("npm audit unavailable: " + str(exc))
        return None
    try:
        return json.loads(proc.stdout)
    except (TypeError, json.JSONDecodeError):
        detail = (proc.stderr or "no JSON response").strip().replace("\n", " ")[:300]
        warnings.append("npm audit did not return parseable JSON: " + detail)
        return None


def npm_records(audit, versions):
    """Normalize npm audit v2 and legacy advisory output to per-advisory records."""
    records = []
    if not isinstance(audit, dict):
        return records
    vulnerabilities = audit.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        for package, finding in vulnerabilities.items():
            if not isinstance(finding, dict):
                continue
            installed = versions.get(package, [])
            via = finding.get("via", [])
            objects = [x for x in via if isinstance(x, dict)]
            # A string via is only a dependency chain, not a separate advisory.
            for adv in objects:
                severity = str(adv.get("severity") or finding.get("severity") or "").upper()
                if severity not in ("HIGH", "CRITICAL"):
                    continue
                for version in installed or ["N/A"]:
                    records.append({"package": package, "version": version,
                                    "identity": "npm:" + str(adv.get("source") or adv.get("url") or adv.get("title") or package),
                                    "severity": severity, "score": (adv.get("cvss") or {}).get("score"),
                                    "fixed": None, "title": adv.get("title"), "url": adv.get("url"),
                                    "raw": adv})
            if not objects and str(finding.get("severity", "")).upper() in ("HIGH", "CRITICAL"):
                for version in installed or ["N/A"]:
                    records.append({"package": package, "version": version, "identity": "npm:" + package,
                                    "severity": str(finding["severity"]).upper(), "score": None,
                                    "fixed": None, "title": "N/A", "url": None, "raw": finding})
    advisories = audit.get("advisories")
    if isinstance(advisories, dict):
        for aid, adv in advisories.items():
            if not isinstance(adv, dict) or str(adv.get("severity", "")).upper() not in ("HIGH", "CRITICAL"):
                continue
            package = adv.get("module_name") or "N/A"
            findings = adv.get("findings") or [{}]
            for finding in findings:
                version = finding.get("version") if isinstance(finding, dict) else None
                records.append({"package": package, "version": version or "N/A", "identity": "npm:" + str(aid),
                                "severity": str(adv["severity"]).upper(), "score": (adv.get("cvss") or {}).get("score"),
                                "fixed": adv.get("patched_versions"), "title": adv.get("title"),
                                "url": adv.get("url"), "raw": adv})
    return records


def cvss_v3_base(vector):
    """Calculate a CVSS v3.x base score from an official vector when possible."""
    if not isinstance(vector, str) or not vector.startswith("CVSS:3"):
        return None
    vals = dict(part.split(":", 1) for part in vector.split("/")[1:] if ":" in part)
    try:
        av = {"N": .85, "A": .62, "L": .55, "P": .2}[vals["AV"]]
        ac = {"L": .77, "H": .44}[vals["AC"]]
        ui = {"N": .85, "R": .62}[vals["UI"]]
        pr = {"N": .85, "L": .62, "H": .27} if vals["S"] == "U" else {"N": .85, "L": .68, "H": .5}
        c = {"H": .56, "L": .22, "N": 0}[vals["C"]]; i = {"H": .56, "L": .22, "N": 0}[vals["I"]]; a = {"H": .56, "L": .22, "N": 0}[vals["A"]]
        impact = 1 - (1-c)*(1-i)*(1-a)
        if impact <= 0: return 0.0
        impact_score = 6.42 * impact if vals["S"] == "U" else 7.52*(impact-.029) - 3.25*((impact-.02) ** 15)
        exploit = 8.22 * av * ac * pr[vals["PR"]] * ui
        value = min(impact_score + exploit, 10) if vals["S"] == "U" else min(1.08*(impact_score + exploit), 10)
        return math.ceil(value * 10 - 1e-9) / 10
    except (KeyError, ValueError):
        return None


def osv_score_and_severity(vuln):
    db = vuln.get("database_specific") or {}
    sev = str(db.get("severity") or "").upper()
    score = None
    for item in vuln.get("severity") or []:
        val = item.get("score") if isinstance(item, dict) else None
        if isinstance(val, (int, float)):
            score = float(val); break
        if isinstance(val, str):
            try: score = float(val); break
            except ValueError:
                calculated = cvss_v3_base(val)
                if calculated is not None:
                    score = calculated; break
    if sev not in ("LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL") and score is not None:
        sev = "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MODERATE" if score >= 4 else "LOW"
    if sev == "MEDIUM": sev = "MODERATE"
    return sev, score


def osv_queries(pairs, endpoint, timeout, warnings):
    result = {}
    for start in range(0, len(pairs), 500):
        chunk = pairs[start:start+500]
        payload = json.dumps({"queries": [{"package": {"ecosystem": "npm", "name": p}, "version": v} for p, v in chunk]}).encode()
        req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            rows = data.get("results", [])
            for pair, row in zip(chunk, rows):
                result[pair] = row.get("vulns", []) if isinstance(row, dict) else []
        except Exception as exc:
            warnings.append("OSV query failed: " + str(exc))
            return None
    return result


def osv_row(package, version, vuln):
    sev, score = osv_score_and_severity(vuln)
    if sev not in ("HIGH", "CRITICAL"):
        return None
    aliases = sorted({a.upper() for a in vuln.get("aliases", []) if isinstance(a, str) and a.upper().startswith("CVE-")})
    fixed = None
    for affected in vuln.get("affected") or []:
        p = affected.get("package") or {}
        if p.get("ecosystem", "").lower() != "npm" or p.get("name") != package:
            continue
        for rng in affected.get("ranges") or []:
            for event in rng.get("events") or []:
                if event.get("fixed"):
                    fixed = event["fixed"]; break
            if fixed: break
    refs = vuln.get("references") or []
    url = next((r.get("url") for r in refs if isinstance(r, dict) and r.get("type") == "ADVISORY" and r.get("url")), None)
    url = url or next((r.get("url") for r in refs if isinstance(r, dict) and r.get("url")), None) or ("https://osv.dev/vulnerability/" + str(vuln.get("id")))
    return {"Package": package, "Version": version, "CVE_ID": ";".join(aliases) or "N/A", "Severity": sev,
            "CVSS_Score": na(('{:.1f}'.format(score)) if score is not None else None), "Fixed_Version": na(fixed),
            "Title": na(vuln.get("summary") or vuln.get("details")), "Url": na(url), "_id": "osv:" + str(vuln.get("id"))}


def npm_row(record):
    text = " ".join(str(record.get(k) or "") for k in ("title", "url"))
    cves = sorted(set(x.upper() for x in CVE_RE.findall(text)))
    return {"Package": na(record["package"]), "Version": na(record["version"]), "CVE_ID": ";".join(cves) or "N/A",
            "Severity": record["severity"], "CVSS_Score": na(record.get("score")), "Fixed_Version": na(record.get("fixed")),
            "Title": na(record.get("title")), "Url": na(record.get("url")), "_id": record["identity"]}


def main():
    try: options = json.load(sys.stdin)
    except json.JSONDecodeError: options = {}
    lock_path = options.get("lock_path", "/root/package-lock.json")
    output_path = options.get("output_path", "/root/security_audit.csv")
    timeout = float(options.get("timeout", 120))
    warnings = []
    with open(lock_path, encoding="utf-8") as f: lock = json.load(f)
    versions = installed_packages(lock)
    audit = run_npm_audit(lock_path, options.get("npm_bin", "npm"), timeout, warnings)
    npm = npm_records(audit, versions)
    pairs = sorted({(r["package"], r["version"]) for r in npm if r["version"] != "N/A"}) if npm else sorted((p, v) for p, vs in versions.items() for v in vs)
    osv = osv_queries(pairs, options.get("osv_url", "https://api.osv.dev/v1/querybatch"), timeout, warnings) if pairs else {}
    rows, covered = [], set()
    if osv is not None:
        selected = set(pairs)
        for package, version in sorted(selected):
            for vuln in osv.get((package, version), []):
                row = osv_row(package, version, vuln)
                if row:
                    key = (package, version, row["_id"])
                    if key not in covered: rows.append(row); covered.add(key)
    # Preserve npm-only findings only when OSV returned no qualifying record for that installed package/version.
    for rec in npm:
        has_osv = any(r["Package"] == na(rec["package"]) and r["Version"] == na(rec["version"]) for r in rows)
        if not has_osv: rows.append(npm_row(rec))
    unique = {}
    for row in rows:
        key = tuple(row[h] for h in HEADER) + (row["_id"],)
        unique[key] = row
    rows = sorted(unique.values(), key=lambda r: (r["Package"].lower(), r["Version"], r["_id"], r["CVE_ID"]))
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"output_path": output_path, "rows": len(rows), "warnings": warnings,
                      "audit_available": audit is not None, "osv_available": osv is not None}, sort_keys=True))

if __name__ == "__main__":
    main()
