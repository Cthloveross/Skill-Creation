#!/usr/bin/env python3
"""Validate the shape and requested severity restriction of an audit CSV."""
import csv
import json
import os
import sys

HEADER = ["Package", "Version", "CVE_ID", "Severity", "CVSS_Score", "Fixed_Version", "Title", "Url"]


def fail(message):
    raise RuntimeError(message)


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict) or not isinstance(request.get("csv"), str):
        fail('stdin must be {"csv":"path"}')
    path = request["csv"]
    if not os.path.isfile(path):
        fail("CSV does not exist: " + path)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        fail("CSV header must exactly equal " + ",".join(HEADER))
    for line_number, row in enumerate(rows[1:], 2):
        if len(row) != len(HEADER):
            fail("line %d has %d columns, expected 8" % (line_number, len(row)))
        if not row[0] or not row[1] or not row[2]:
            fail("line %d has empty Package, Version, or CVE_ID" % line_number)
        if row[3] not in ("HIGH", "CRITICAL"):
            fail("line %d has disallowed severity %r" % (line_number, row[3]))
    print(json.dumps({"valid": True, "findings": len(rows) - 1, "csv": path}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(2)
