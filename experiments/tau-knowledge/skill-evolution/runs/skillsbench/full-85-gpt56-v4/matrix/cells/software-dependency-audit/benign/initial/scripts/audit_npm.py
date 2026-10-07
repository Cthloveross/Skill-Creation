#!/usr/bin/env python3
"""Create a high/critical npm vulnerability CSV from exact lockfile versions.
Reads one JSON request from stdin and writes one JSON summary to stdout.
"""
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

NA = "N/A"
DEFAULT_ENDPOINT = "https://api.osv.dev/v1/querybatch"
HEADER = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score", "Fixed_Version", "Title", "Url"]


def fail(message):
    raise RuntimeError(message)


def read_request():
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        fail("stdin must contain one JSON object: %s" % exc)
    if not isinstance(request, dict):
        fail("stdin JSON must be an object")
    for key in ("lockfile", "output"):
        if not isinstance(request.get(key), str) or not request[key]:
            fail("%r must be a nonempty path string" % key)
    return request


def name_from_package_path(path, item):
    if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
        return item["name"]
    marker = "node_modules/"
    pos = path.rfind(marker)
    if pos < 0:
        return None
    return path[pos + len(marker):]


def collect_v1(tree, output):
    if not isinstance(tree, dict):
        return
    for name, item in tree.items():
        if not isinstance(item, dict):
            continue
        version = item.get("version")
        if isinstance(name, str) and isinstance(version, str) and version:
            output.add((name, version))
        collect_v1(item.get("dependencies"), output)


def lock_packages(lock):
    found = set()
    packages = lock.get("packages")
    if isinstance(packages, dict):
        for path, item in packages.items():
            if not path or not isinstance(item, dict):
                continue
            name = name_from_package_path(path, item)
            version = item.get("version")
            if isinstance(name, str) and name and isinstance(version, str) and version:
                found.add((name, version))
    # v1 has no packages map. Some transitional locks benefit from both maps.
    collect_v1(lock.get("dependencies"), found)
    if not found:
        fail("no exact installed package versions were found in the lockfile")
    return sorted(found, key=lambda x: (x[0].lower(), x[0], x[1]))


def snapshot_key(name, version):
    return "npm:%s@%s" % (name, version)


def load_snapshot(path, pairs):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        fail("cannot read snapshot: %s" % exc)
    if not isinstance(data, dict):
        fail("snapshot must be an object mapping npm:name@version to OSV vulnerability lists")
    wanted = [snapshot_key(n, v) for n, v in pairs]
    missing = [key for key in wanted if key not in data]
    if missing:
        fail("snapshot is incomplete; missing %d installed package/version entries" % len(missing))
    result = {}
    for key in wanted:
        value = data[key]
        if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
            fail("snapshot entry %s is not a list of OSV vulnerability objects" % key)
        result[key] = value
    return result


def post_json(url, body):
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "reproducible-npm-audit/1"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 200:
                    fail("OSV returned HTTP %s" % response.status)
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    fail("OSV query failed after retries: %s" % last)


def query_osv(pairs, endpoint):
    mapping = {}
    # Keep request bodies comfortably below service limits on very large locks.
    for start in range(0, len(pairs), 500):
        chunk = pairs[start:start + 500]
        body = {"queries": [{"package": {"ecosystem": "npm", "name": name}, "version": version} for name, version in chunk]}
        payload = post_json(endpoint, body)
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or len(results) != len(chunk):
            fail("OSV querybatch response does not align with requested package versions")
        for (name, version), item in zip(chunk, results):
            vulns = item.get("vulns", []) if isinstance(item, dict) else None
            if not isinstance(vulns, list) or not all(isinstance(v, dict) for v in vulns):
                fail("OSV returned an invalid vulnerability list for %s@%s" % (name, version))
            mapping[snapshot_key(name, version)] = vulns
    return mapping


def severity_vector(record):
    values = []
    for container in (record.get("severity"),):
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict) and isinstance(item.get("score"), str):
                    values.append(item["score"])
    for key in ("database_specific", "ecosystem_specific"):
        obj = record.get(key)
        if isinstance(obj, dict):
            for field in ("cvss", "cvss_vector"):
                if isinstance(obj.get(field), str):
                    values.append(obj[field])
    return next((x for x in values if "CVSS:3" in x.upper()), None)


def round_up_one_decimal(value):
    return math.ceil(value * 10 - 1e-10) / 10.0


def cvss3_score(vector):
    """Return a CVSS v3 base score for an OSV vector, or None if incomplete."""
    if not isinstance(vector, str):
        return None
    metrics = {}
    for part in vector.upper().split("/"):
        if ":" in part:
            key, value = part.split(":", 1)
            metrics[key] = value
    try:
        av = {"N": .85, "A": .62, "L": .55, "P": .2}[metrics["AV"]]
        ac = {"L": .77, "H": .44}[metrics["AC"]]
        ui = {"N": .85, "R": .62}[metrics["UI"]]
        scope = metrics["S"]
        pr_table = {"U": {"N": .85, "L": .62, "H": .27}, "C": {"N": .85, "L": .68, "H": .5}}
        pr = pr_table[scope][metrics["PR"]]
        impact_values = {"H": .56, "L": .22, "N": 0.0}
        c, i, a = (impact_values[metrics[x]] for x in ("C", "I", "A"))
    except (KeyError, ValueError):
        return None
    isc = 1 - (1-c) * (1-i) * (1-a)
    if scope == "U":
        impact = 6.42 * isc
    elif scope == "C":
        impact = 7.52 * (isc - .029) - 3.25 * ((isc - .02) ** 15)
    else:
        return None
    exploit = 8.22 * av * ac * pr * ui
    if impact <= 0:
        return 0.0
    score = min(impact + exploit, 10) if scope == "U" else min(1.08 * (impact + exploit), 10)
    return round_up_one_decimal(score)


def explicit_severity(record):
    for group in ("database_specific", "ecosystem_specific"):
        obj = record.get(group)
        if isinstance(obj, dict):
            value = obj.get("severity")
            if isinstance(value, str):
                normalized = value.upper().strip()
                if normalized in ("CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW", "UNKNOWN"):
                    return "MEDIUM" if normalized == "MODERATE" else normalized
    return None


def classify(record):
    explicit = explicit_severity(record)
    score = cvss3_score(severity_vector(record))
    if explicit in ("HIGH", "CRITICAL"):
        return explicit, score
    if explicit is not None:
        return explicit, score
    if score is None:
        return "UNKNOWN", None
    if score >= 9.0:
        return "CRITICAL", score
    if score >= 7.0:
        return "HIGH", score
    if score >= 4.0:
        return "MEDIUM", score
    return "LOW", score


def version_parts(value):
    """A conservative semver comparator adequate for OSV introduced/fixed events."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value == "0":
        return (0, 0, 0, ())
    match = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$", value)
    if not match:
        return None
    nums = (int(match.group(1)), int(match.group(2) or 0), int(match.group(3) or 0))
    pre = match.group(4)
    if pre is None:
        preparts = ((2, ""),)  # release is after all prereleases
    else:
        preparts = tuple((0, int(x)) if x.isdigit() else (1, x) for x in pre.split("."))
    return nums + (preparts,)


def version_less(left, right):
    a, b = version_parts(left), version_parts(right)
    if a is None or b is None:
        return None
    return a < b


def matching_fixed_version(record, installed):
    """Return the closing fixed event for the affected interval containing installed."""
    for affected in record.get("affected", []) if isinstance(record.get("affected"), list) else []:
        if not isinstance(affected, dict):
            continue
        for rng in affected.get("ranges", []) if isinstance(affected.get("ranges"), list) else []:
            if not isinstance(rng, dict) or rng.get("type") != "SEMVER":
                continue
            open_start = None
            for event in rng.get("events", []) if isinstance(rng.get("events"), list) else []:
                if not isinstance(event, dict):
                    continue
                if "introduced" in event:
                    open_start = event["introduced"]
                for close_key in ("fixed", "last_affected", "limit"):
                    if close_key not in event or open_start is None:
                        continue
                    start_ok = (open_start == "0" or version_less(open_start, installed) in (True, False))
                    before_close = version_less(installed, event[close_key])
                    # A fixed/limit release is exclusive; last_affected is inclusive.
                    if close_key == "last_affected" and before_close is False:
                        before_close = (version_less(event[close_key], installed) is False)
                    if start_ok and before_close is True and close_key == "fixed" and isinstance(event[close_key], str):
                        return event[close_key]
                    open_start = None
    return NA


def record_identifier(record):
    aliases = record.get("aliases") if isinstance(record.get("aliases"), list) else []
    cves = sorted(str(x) for x in aliases if isinstance(x, str) and x.upper().startswith("CVE-"))
    if cves:
        return cves[0]
    identifier = record.get("id")
    return identifier if isinstance(identifier, str) and identifier else NA


def primary_url(record):
    refs = record.get("references") if isinstance(record.get("references"), list) else []
    good = [r for r in refs if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"]]
    for preferred_type in ("ADVISORY", "WEB"):
        for ref in good:
            if ref.get("type") == preferred_type:
                return ref["url"]
    return good[0]["url"] if good else NA


def title(record):
    value = record.get("summary")
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = record.get("details")
    if isinstance(value, str) and value.strip():
        return value.strip().splitlines()[0]
    return NA


def rows_for(pairs, mapping):
    rows = []
    seen = set()
    for package, version in pairs:
        for record in mapping[snapshot_key(package, version)]:
            if record.get("withdrawn"):
                continue
            severity, score = classify(record)
            if severity not in ("HIGH", "CRITICAL"):
                continue
            osv_id = record.get("id") if isinstance(record.get("id"), str) else ""
            key = (package, version, osv_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append([package, version, record_identifier(record), severity,
                         ("%.1f" % score) if score is not None else NA,
                         matching_fixed_version(record, version), title(record), primary_url(record)])
    return sorted(rows, key=lambda row: (row[0].lower(), row[0], row[1], row[2], row[7]))


def write_csv(path, rows):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temporary = tempfile.mkstemp(prefix=".security_audit.", suffix=".csv", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerows(rows)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_json(path, data):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temporary = tempfile.mkstemp(prefix=".security_audit.", suffix=".json", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main():
    request = read_request()
    try:
        with open(request["lockfile"], "r", encoding="utf-8") as handle:
            lock = json.load(handle)
    except Exception as exc:
        fail("cannot read lockfile: %s" % exc)
    if not isinstance(lock, dict):
        fail("lockfile root must be a JSON object")
    pairs = lock_packages(lock)
    if request.get("snapshot"):
        mapping = load_snapshot(request["snapshot"], pairs)
        source = "snapshot"
    else:
        mapping = query_osv(pairs, request.get("endpoint", DEFAULT_ENDPOINT))
        source = "live-osv"
    if isinstance(request.get("save_snapshot"), str) and request["save_snapshot"]:
        write_json(request["save_snapshot"], mapping)
    rows = rows_for(pairs, mapping)
    write_csv(request["output"], rows)
    raw_hash = hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    selected = sorted({row[2] for row in rows})
    provenance = {"source": source, "osv_endpoint": None if source == "snapshot" else request.get("endpoint", DEFAULT_ENDPOINT),
                  "snapshot_sha256": raw_hash, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "installed_package_version_count": len(pairs), "high_critical_row_count": len(rows),
                  "selected_identifiers": selected}
    if isinstance(request.get("provenance"), str) and request["provenance"]:
        write_json(request["provenance"], provenance)
    print(json.dumps({"output": request["output"], "packages": len(pairs), "findings": len(rows), "source": source, "snapshot_sha256": raw_hash}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
