#!/usr/bin/env python3
"""Structural validation of a diff_report.json.

Stdin (JSON): {"report_path": "/root/diff_report.json"}
Stdout (JSON): {"valid": bool, "errors": [...], "deleted_count": n, "modified_count": n}

Checks (derived from the public output contract):
 - top-level keys exactly deleted_employees, modified_employees
 - deleted_employees: list of EMP##### strings, sorted ascending
 - modified_employees: list of {id, field, old_value, new_value}
     id is EMP##### string; field is a non-empty string;
     numeric values are JSON numbers, text values are strings (not mixed junk)
     list sorted by (id, field)
"""
import sys
import re
import json

ID_RE = re.compile(r"^EMP\d+$")


def main():
    errors = []
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
        path = cfg.get("report_path", "/root/diff_report.json")
        with open(path) as f:
            d = json.load(f)
    except Exception as e:  # noqa
        print(json.dumps({"valid": False, "errors": ["cannot load report: %s" % e]}))
        return

    if set(d.keys()) != {"deleted_employees", "modified_employees"}:
        errors.append("top-level keys must be exactly deleted_employees, modified_employees; got %s" % sorted(d.keys()))

    deleted = d.get("deleted_employees", [])
    if not isinstance(deleted, list):
        errors.append("deleted_employees must be a list")
        deleted = []
    for x in deleted:
        if not (isinstance(x, str) and ID_RE.match(x)):
            errors.append("deleted id not an EMP##### string: %r" % x)
    if deleted != sorted(deleted):
        errors.append("deleted_employees not sorted by ID")

    modified = d.get("modified_employees", [])
    if not isinstance(modified, list):
        errors.append("modified_employees must be a list")
        modified = []
    for m in modified:
        if not isinstance(m, dict):
            errors.append("modified entry not an object: %r" % m)
            continue
        if set(m.keys()) != {"id", "field", "old_value", "new_value"}:
            errors.append("modified entry keys must be id, field, old_value, new_value; got %s" % sorted(m.keys()))
        mid = m.get("id")
        if not (isinstance(mid, str) and ID_RE.match(mid)):
            errors.append("modified id not an EMP##### string: %r" % mid)
        if not (isinstance(m.get("field"), str) and m.get("field")):
            errors.append("modified field not a non-empty string: %r" % m.get("field"))
        for k in ("old_value", "new_value"):
            v = m.get(k)
            if not isinstance(v, (str, int, float)) or isinstance(v, bool):
                errors.append("%s must be string or number: %r" % (k, v))
    keyed = [(m.get("id"), str(m.get("field"))) for m in modified if isinstance(m, dict)]
    if keyed != sorted(keyed):
        errors.append("modified_employees not sorted by (id, field)")

    print(json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "deleted_count": len(deleted),
        "modified_count": len(modified),
    }))


if __name__ == "__main__":
    main()
