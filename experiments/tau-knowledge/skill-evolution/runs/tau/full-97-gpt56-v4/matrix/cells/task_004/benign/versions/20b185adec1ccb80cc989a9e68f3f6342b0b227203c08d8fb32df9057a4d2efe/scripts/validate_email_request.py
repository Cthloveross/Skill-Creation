#!/usr/bin/env python3
"""Validate a proposed replacement email from JSON stdin; emit JSON stdout."""
import json
import re
import sys

# Deliberately conservative basic syntax check, not a mailbox/ownership check.
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate(value):
    if not isinstance(value, str):
        return {"ok": False, "normalized_email": None, "reason": "new_email is required"}
    email = value.strip()
    if not email:
        return {"ok": False, "normalized_email": None, "reason": "new_email is required"}
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return {"ok": False, "normalized_email": None, "reason": "new_email has invalid format"}
    return {"ok": True, "normalized_email": email, "reason": None}


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps({"ok": False, "normalized_email": None, "reason": "input must be a JSON object"}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "normalized_email": None, "reason": "input must be a JSON object"}))
        return
    print(json.dumps(validate(payload.get("new_email")), ensure_ascii=False))


if __name__ == "__main__":
    main()
