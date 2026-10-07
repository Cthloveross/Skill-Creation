#!/usr/bin/env python3
"""Write the three required blind-review copies.

stdin: {"auto_discover":true,"targets":{"paper1.pdf":[target],...}}
stdout: {"documents":[report,...],"valid":true}
"""
import json
import sys
from anonymize import process

NAMES = ("paper1.pdf", "paper2.pdf", "paper3.pdf")


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("input must be an object")
    auto = request.get("auto_discover", True)
    if not isinstance(auto, bool):
        raise ValueError("auto_discover must be boolean")
    by_name = request.get("targets", {})
    if not isinstance(by_name, dict):
        raise ValueError("targets must be an object keyed by filename")
    unknown = set(by_name) - set(NAMES)
    if unknown:
        raise ValueError("unknown target filename(s): " + ", ".join(sorted(unknown)))
    reports = []
    for name in NAMES:
        targets = by_name.get(name, [])
        if not isinstance(targets, list):
            raise ValueError("targets for " + name + " must be an array")
        reports.append(process({"input": "/root/" + name, "output": "/root/redacted/" + name,
                                "auto_discover": auto, "clear_metadata": True, "targets": targets}))
    print(json.dumps({"documents": reports, "valid": all(x["valid"] for x in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
