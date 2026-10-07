#!/usr/bin/env python3
"""Independently verify output of a reviewed redaction JSON config from stdin."""
import json
import sys

import fitz
from pdf_redaction_common import normalize_config, find_remaining, token_loss_summary


def all_text(doc):
    return "\n".join(page.get_text("text") for page in doc)


def main():
    cfg = json.load(sys.stdin)
    targets, metadata_keys, clear_xmp = normalize_config(cfg)
    original = fitz.open(str(cfg["input"]))
    output = fitz.open(str(cfg["output"]))
    _, remaining = find_remaining(output, targets)
    metadata = dict(output.metadata or {})
    metadata_failures = {key: metadata.get(key, "") for key in metadata_keys
                         if metadata.get(key, "")}
    xmp_present = bool(output.get_xml_metadata())
    loss = token_loss_summary(all_text(original), all_text(output),
                              [target["text"] for target in targets])
    result = {
        "ok": original.page_count == output.page_count and not any(remaining.values())
              and not metadata_failures and not (clear_xmp and xmp_present),
        "page_count_before": original.page_count,
        "page_count_after": output.page_count,
        "remaining_eligible_matches": remaining,
        "metadata_not_cleared": metadata_failures,
        "xmp_metadata_present": xmp_present,
        "content_preservation_warning": loss,
        "note": "Review visually; token loss is heuristic and not evidence that discovery was complete."
    }
    original.close()
    output.close()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(2)
