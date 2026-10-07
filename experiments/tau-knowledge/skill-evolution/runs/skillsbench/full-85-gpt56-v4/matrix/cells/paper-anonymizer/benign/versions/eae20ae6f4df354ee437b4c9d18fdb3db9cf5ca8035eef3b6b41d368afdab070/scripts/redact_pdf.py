#!/usr/bin/env python3
"""Apply a reviewed redaction JSON config read from stdin; emit report JSON."""
import json
import os
import sys
from pathlib import Path

import fitz
from pdf_redaction_common import (normalize_config, redact_document, scrub_metadata,
                                  find_remaining)


def main():
    cfg = json.load(sys.stdin)
    targets, metadata_keys, clear_xmp = normalize_config(cfg)
    src, dst = str(cfg["input"]), str(cfg["output"])
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("output must differ from input")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(src)
    pages_before = doc.page_count
    boundary, counts = redact_document(doc, targets)
    missing_required = [t["text"] for t in targets if t["required"] and counts[t["text"]] == 0]
    metadata_before = scrub_metadata(doc, metadata_keys, clear_xmp)
    if missing_required:
        doc.close()
        raise ValueError("required target had no eligible exact match: " + "; ".join(missing_required))
    doc.save(dst, garbage=4, deflate=True)
    doc.close()

    check = fitz.open(dst)
    _, remaining = find_remaining(check, targets)
    metadata_after = dict(check.metadata or {})
    pages_after = check.page_count
    xmp_present = bool(check.get_xml_metadata())
    check.close()
    ok = pages_before == pages_after and not any(remaining.values())
    for key in metadata_keys:
        if metadata_after.get(key, ""):
            ok = False
    if clear_xmp and xmp_present:
        ok = False
    report = {
        "ok": ok, "input": src, "output": dst,
        "page_count_before": pages_before, "page_count_after": pages_after,
        "first_reference_boundary": None if boundary is None else
            {"page": boundary[0] + 1, "y": round(boundary[1], 2)},
        "redaction_match_counts": counts, "remaining_eligible_matches": remaining,
        "metadata_before": metadata_before, "metadata_after": metadata_after,
        "xmp_metadata_present_after": xmp_present,
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        raise SystemExit(2)
