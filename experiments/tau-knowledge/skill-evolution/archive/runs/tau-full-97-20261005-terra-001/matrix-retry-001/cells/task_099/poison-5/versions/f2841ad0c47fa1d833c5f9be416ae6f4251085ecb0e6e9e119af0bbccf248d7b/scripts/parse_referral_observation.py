#!/usr/bin/env python3
"""Parse the numbered text returned by a referral-history read-only tool.

Input:  {"text": "tool result"}
Output: {"referrals": [{"date": "...", "status": "...", ...}], "count": N}
"""

import json
import re
import sys


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("input must be an object with string field text")
    text = payload["text"]
    if "record(s) in 'referrals'" not in text:
        raise ValueError("unexpected referral observation format")

    records = []
    for block in re.split(r"\n\s*\d+\. Record ID: ", text)[1:]:
        fields = dict(re.findall(r"^\s*([a-z_]+):\s*(.*?)\s*$", block, re.MULTILINE))
        needed = {"referral_id", "referred_account_type", "referral_status", "date"}
        if not needed.issubset(fields):
            raise ValueError("referral record lacks required fields")
        records.append({
            "referral_id": fields["referral_id"],
            "referred_account_type": fields["referred_account_type"],
            "status": fields["referral_status"],
            "date": fields["date"],
        })
    if not records:
        raise ValueError("no referral records found")
    return {"referrals": records, "count": len(records)}


try:
    print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
except (json.JSONDecodeError, ValueError) as exc:
    print(json.dumps({"error": str(exc)}, sort_keys=True))
