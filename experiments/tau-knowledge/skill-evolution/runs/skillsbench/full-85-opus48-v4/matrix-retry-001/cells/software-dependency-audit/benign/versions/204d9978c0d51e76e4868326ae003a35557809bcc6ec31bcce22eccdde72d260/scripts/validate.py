"""Structural validation of the produced security_audit.csv.

Reads JSON on stdin: {"output": "/root/security_audit.csv",
                      "severities": ["HIGH", "CRITICAL"]}
Prints JSON on stdout describing whether the CSV meets the output contract.
This checks structure only (header, allowed severities, duplicate rows,
explicit N/A for empties); it does not re-run the network audit.
"""
import csv
import json
import sys

EXPECTED = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score",
            "Fixed_Version", "Title", "Url"]


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        cfg = {}
    path = cfg.get("output", "/root/security_audit.csv")
    want = {s.upper() for s in cfg.get("severities", ["HIGH", "CRITICAL"])}

    problems = []
    rows = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if header != EXPECTED:
                problems.append(f"header mismatch: {header}")
            for r in reader:
                rows.append(r)
    except FileNotFoundError:
        print(json.dumps({"ok": False, "problems": ["output file missing"],
                          "rows": 0}))
        return

    seen = set()
    for i, r in enumerate(rows, 1):
        if len(r) != len(EXPECTED):
            problems.append(f"row {i}: wrong column count ({len(r)})")
            continue
        rec = dict(zip(EXPECTED, r))
        if rec["Severity"].upper() not in want:
            problems.append(f"row {i}: severity {rec['Severity']} not in {sorted(want)}")
        for col in EXPECTED:
            if rec[col] == "":
                problems.append(f"row {i}: empty {col} (should be N/A)")
        key = (rec["Package"], rec["Version"], rec["CVE_ID"])
        if key in seen:
            problems.append(f"row {i}: duplicate {key}")
        seen.add(key)

    print(json.dumps({"ok": not problems, "problems": problems,
                      "rows": len(rows)}))


if __name__ == "__main__":
    main()
