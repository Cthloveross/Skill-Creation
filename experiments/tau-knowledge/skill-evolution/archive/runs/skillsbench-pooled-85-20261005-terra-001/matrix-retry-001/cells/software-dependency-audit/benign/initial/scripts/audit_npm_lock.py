#!/usr/bin/env python3
"""Offline npm audit normalizer. JSON stdin -> JSON stdout; writes CSV on success."""
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEADER = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score", "Fixed_Version", "Title", "Url"]
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1}


def text(value, default="N/A"):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return default
    return str(value).strip() or default


def first_url(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                candidate = item.get("url") or item.get("reference")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    return "N/A"


def cves_from(record):
    """Return declared CVE aliases, never relabeling a GHSA/source number as a CVE."""
    candidates = []
    for key in ("cves", "aliases", "cve", "cve_id", "id", "github_advisory_id"):
        value = record.get(key) if isinstance(record, dict) else None
        if isinstance(value, list):
            candidates.extend(str(x) for x in value)
        elif value is not None:
            candidates.append(str(value))
    for key in ("url", "title", "overview", "description"):
        value = record.get(key) if isinstance(record, dict) else None
        if isinstance(value, str):
            candidates.append(value)
    found = sorted({m.group(0).upper() for item in candidates for m in CVE_RE.finditer(item)})
    return found or ["N/A"]


def read_lock_versions(lock):
    """Return package-name -> versions and lock package-path -> exact version."""
    by_name, by_node = {}, {}

    def add(name, version, node=None):
        if not isinstance(name, str) or not isinstance(version, (str, int, float)):
            return
        version = str(version)
        by_name.setdefault(name, set()).add(version)
        if node:
            by_node[node] = version

    packages = lock.get("packages")
    if isinstance(packages, dict):
        for node, meta in packages.items():
            if not isinstance(meta, dict) or not meta.get("version"):
                continue
            name = meta.get("name")
            if not name and isinstance(node, str) and "node_modules/" in node:
                name = node.rsplit("node_modules/", 1)[-1]
            add(name, meta.get("version"), node)

    def walk(deps, prefix=""):
        if not isinstance(deps, dict):
            return
        for name, meta in deps.items():
            if not isinstance(meta, dict):
                continue
            node = (prefix + "node_modules/" + name) if prefix else "node_modules/" + name
            add(name, meta.get("version"), node)
            walk(meta.get("dependencies"), node + "/")

    walk(lock.get("dependencies"))
    return by_name, by_node


def versions_for(name, nodes, by_name, by_node):
    versions = set()
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, str):
                clean = node[2:] if node.startswith("./") else node
                if clean in by_node:
                    versions.add(by_node[clean])
    if not versions:
        versions.update(by_name.get(name, set()))
    return sorted(versions) or ["N/A"]


def score_from(record):
    score = record.get("cvss") if isinstance(record, dict) else None
    if isinstance(score, dict):
        score = score.get("score")
    if score is None and isinstance(record, dict):
        score = record.get("cvssScore")
    return text(score)


def fixed_from(value):
    if isinstance(value, dict):
        return text(value.get("version"))
    if value is False or value is None:
        return "N/A"
    candidate = text(value)
    if candidate.lower() in {"none", "no fix", "<0.0.0", "false"}:
        return "N/A"
    return candidate


def make_rows(name, versions, record, fixed="N/A"):
    """Create rows solely from one advisory record plus resolved installed version."""
    severity = text(record.get("severity")).upper()
    if severity not in SEVERITY_RANK:
        return []
    title = text(record.get("title") or record.get("overview") or record.get("description"))
    url = first_url(record.get("url") or record.get("references"))
    score = score_from(record)
    rows = []
    for version in versions:
        for cve in cves_from(record):
            rows.append([text(name), text(version), cve, severity, score, fixed, title, url])
    return rows


def legacy_rows(report, by_name, by_node):
    rows = []
    advisories = report.get("advisories", {})
    if not isinstance(advisories, dict):
        return rows
    for advisory in advisories.values():
        if not isinstance(advisory, dict):
            continue
        name = advisory.get("module_name") or advisory.get("name")
        findings = advisory.get("findings")
        versions = set()
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict) and finding.get("version") is not None:
                    versions.add(str(finding["version"]))
        if not versions:
            versions.update(versions_for(name, [], by_name, by_node))
        rows.extend(make_rows(name, sorted(versions), advisory, fixed_from(advisory.get("patched_versions"))))
    return rows


def v2_rows(report, by_name, by_node):
    rows = []
    vulnerabilities = report.get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict):
        return rows

    # Direct object entries are advisory source records. String entries are graph
    # links; resolve them to their own direct source records without copying fields.
    def sources_for(package, seen):
        if package in seen:
            return []
        seen = set(seen)
        seen.add(package)
        item = vulnerabilities.get(package)
        if not isinstance(item, dict):
            return []
        result = []
        via = item.get("via", [])
        if isinstance(via, dict):
            via = [via]
        if not isinstance(via, list):
            return result
        for source in via:
            if isinstance(source, dict):
                result.append(source)
            elif isinstance(source, str):
                result.extend(sources_for(source, seen))
        return result

    for name, summary in vulnerabilities.items():
        if not isinstance(summary, dict):
            continue
        versions = versions_for(name, summary.get("nodes"), by_name, by_node)
        direct_sources = sources_for(name, set())
        for source in direct_sources:
            # Current npm source objects generally carry severity/title/url. Do not
            # fill missing source fields from a different package summary.
            rows.extend(make_rows(name, versions, source, "N/A"))
    return rows


def load_report(config):
    supplied = config.get("audit_json_path")
    if supplied:
        path = Path(supplied)
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh), {"kind": "supplied_audit_json", "path": str(path)}

    executable = config.get("npm_executable", "npm")
    if not isinstance(executable, str) or not executable:
        raise ValueError("npm_executable must be a nonempty string")
    lockfile = Path(config.get("lockfile", "/root/package-lock.json"))
    proc = subprocess.run(
        [executable, "audit", "--offline", "--package-lock-only", "--json"],
        cwd=str(lockfile.parent), text=True, capture_output=True, check=False
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("npm did not return a JSON audit report while offline: " + (proc.stderr.strip() or str(exc)))
    # npm conventionally exits 1 when vulnerabilities exist, so return code alone
    # is not failure. An error object means no complete report was obtained.
    if isinstance(report, dict) and report.get("error"):
        raise RuntimeError("offline npm audit failed: " + text(report.get("error")))
    if proc.returncode not in (0, 1):
        raise RuntimeError("offline npm audit failed: " + (proc.stderr.strip() or "exit " + str(proc.returncode)))
    return report, {"kind": "npm_audit_offline", "command": [executable, "audit", "--offline", "--package-lock-only", "--json"]}


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin must be a JSON object")
        lock_path = Path(config.get("lockfile", "/root/package-lock.json"))
        with lock_path.open("r", encoding="utf-8") as fh:
            lock = json.load(fh)
        if not isinstance(lock, dict):
            raise ValueError("lockfile root must be a JSON object")
        report, provenance = load_report(config)
        if not isinstance(report, dict):
            raise ValueError("audit report root must be a JSON object")
        by_name, by_node = read_lock_versions(lock)
        rows = legacy_rows(report, by_name, by_node) if isinstance(report.get("advisories"), dict) else v2_rows(report, by_name, by_node)
        unique = {tuple(row) for row in rows}
        ordered = sorted(unique, key=lambda r: (SEVERITY_RANK[r[3]], r[0].lower(), r[1], r[2], r[6].lower(), r[7]))
        output = Path(config.get("output_csv", "/root/security_audit.csv"))
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(HEADER)
            writer.writerows(ordered)
        provenance["lockfile"] = str(lock_path)
        print(json.dumps({"ok": True, "output_csv": str(output), "rows": len(ordered), "provenance": provenance}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)

if __name__ == "__main__":
    main()
