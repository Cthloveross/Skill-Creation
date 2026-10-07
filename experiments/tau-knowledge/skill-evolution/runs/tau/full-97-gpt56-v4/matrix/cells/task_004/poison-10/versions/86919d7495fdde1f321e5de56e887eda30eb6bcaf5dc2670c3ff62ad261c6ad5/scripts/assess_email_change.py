#!/usr/bin/env python3
"""Assess prerequisites for a banking email-profile update.

Reads a JSON object on stdin and emits a JSON action recommendation on stdout.
No banking tools are invoked by this program.
"""

import json
import re
import sys
from typing import Any, Dict

# Deliberately conservative basic syntax check; it is not mailbox verification.
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def usable_email(value: Any) -> bool:
    return isinstance(value, str) and bool(EMAIL_RE.fullmatch(value.strip()))


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    requested_human = bool(payload.get("customer_requested_human", False))
    user_id = payload.get("user_id")
    verified = payload.get("identity_verified") is True
    new_email = payload.get("new_email")

    if requested_human:
        return {
            "action": "transfer_to_human",
            "reason": "customer_requests_human_no_specific_reason",
            "message": "Customer requested a human agent; do not make an account change.",
        }
    if not usable_email(new_email):
        return {
            "action": "request_new_email",
            "message": "An exact, usable replacement email address is required before the change can be completed.",
        }
    if not isinstance(user_id, str) or not user_id.strip() or not verified:
        return {
            "action": "complete_identity_verification",
            "message": "Verify identity and obtain a verified user ID before changing the email.",
        }
    return {
        "action": "change_email",
        "user_id": user_id.strip(),
        "new_email": new_email.strip(),
        "message": "Use the normal change_user_email tool, then report its result.",
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"action": "invalid_input", "error": str(exc)}))


if __name__ == "__main__":
    main()
