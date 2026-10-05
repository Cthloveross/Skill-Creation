#!/usr/bin/env python3
"""Task entrypoint for the three required blind-review PDFs.

stdin:
{"auto_discover": true,
 "targets":{"paper1.pdf":[target, ...],"paper2.pdf":[...],"paper3.pdf":[...]}}

The only outputs are /root/redacted/paper1.pdf through paper3.pdf. Target
objects use the schema documented by anonymize.py. stdout is its JSON report.
"""
import json
import sys

from anonymize import process

NAMES = ("paper1.pdf", "paper2.pdf", "paper3.pdf")


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("input must be an object")
    targets_by_name = request.get("targets", {})
    if not isinstance(targets_by_name, dict):
        raise ValueError("targets must be an object keyed by paper filename")
    unknown = set(targets_by_name) - set(NAMES)
    if unknown:
        raise ValueError("unknown target filename(s): " + ", ".join(sorted(unknown)))
    auto = request.get("auto_discover", True)
    if not isinstance(auto, bool):
        raise ValueError("auto_discover must be boolean")
    reports = []
    for name in NAMES:
        targets = targets_by_name.get(name, [])
        if not isinstance(targets, list):
            raise ValueError("targets for " + name + " must be an array")
        reports.append(process({
            "input": "/root/" + name,
            "output": "/root/redacted/" + name,
            "auto_discover": auto,
            "clear_metadata": True,
            "targets": targets,
        }))
    print(json.dumps({"documents": reports, "valid": all(r["valid"] for r in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
