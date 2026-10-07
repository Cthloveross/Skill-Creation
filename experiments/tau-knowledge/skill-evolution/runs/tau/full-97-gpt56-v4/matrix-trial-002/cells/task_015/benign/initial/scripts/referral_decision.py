#!/usr/bin/env python3
"""Classify whether referral-link instructions may be provided.

Reads one JSON object from stdin and writes one JSON object to stdout. This
program is deliberately side-effect free and cannot validate a program itself.
"""
import json
import sys


def fail(message: str) -> None:
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: %s" % exc.msg)

    required = ("card_name", "program_documented", "terms_match", "automatic_rejection_reason")
    missing = [key for key in required if key not in payload]
    if missing:
        fail("missing required field(s): " + ", ".join(missing))

    card_name = payload["card_name"]
    if not isinstance(card_name, str) or not card_name.strip():
        fail("card_name must be a non-empty string")
    if not isinstance(payload["program_documented"], bool):
        fail("program_documented must be boolean")
    if not isinstance(payload["terms_match"], bool):
        fail("terms_match must be boolean")
    rejection = payload["automatic_rejection_reason"]
    if rejection is not None and (not isinstance(rejection, str) or not rejection.strip()):
        fail("automatic_rejection_reason must be null or a non-empty string")

    if not payload["program_documented"]:
        result = {
            "eligible_to_offer_user_tool": False,
            "reason_code": "program_not_documented",
            "next_step": "Explain that an active documented referral program for the exact card could not be confirmed; do not provide or generate a link and do not transfer solely for this reason.",
        }
    elif not payload["terms_match"]:
        result = {
            "eligible_to_offer_user_tool": False,
            "reason_code": "terms_unverified_or_mismatched",
            "next_step": "Explain that the claimed terms do not match, or cannot be matched to, the documented offer; do not provide or generate a link and do not transfer solely for this reason.",
        }
    elif rejection is not None:
        result = {
            "eligible_to_offer_user_tool": False,
            "reason_code": "automatic_rejection_expected",
            "next_step": "Explain the known automatic-rejection reason; do not provide or generate a link and do not transfer solely for this reason.",
        }
    else:
        result = {
            "eligible_to_offer_user_tool": True,
            "reason_code": "verified",
            "next_step": "Restate the documented terms and give the customer—not the agent—the get_referral_link(user_id, card_name) tool using the exact card name.",
        }

    result["card_name"] = card_name
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
