#!/usr/bin/env python3
"""End-to-end entrypoint: document JSON in; active-offer analysis and response draft out."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from extract_promotions import main as extract
from compose_offer_response import main as compose


def main(payload):
    extracted = extract(payload)
    if not extracted.get("ok"):
        return extracted
    result = compose({"as_of": extracted.get("as_of"), "offers": extracted.get("offers", [])})
    result["warnings"] = extracted.get("warnings", []) + result.get("warnings", [])
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
