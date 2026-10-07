#!/usr/bin/env python3
"""Create privacy-safe referral support guidance from authorized structured facts.

Reads one JSON object from stdin and writes one JSON object to stdout.  It does
not call banking systems and deliberately accepts no transaction details.
"""
import json
import sys

STATUS_MEANINGS = {
    "COMPLETE": "The referred person has opened an account and met the referral-bonus criteria.",
    "IN_PROGRESS": "The referred person has opened an account and is still working toward the referral-bonus criteria.",
    "NO_PROGRESS": "The referred person has not applied yet.",
    "APPLIED": "The referred person has applied and is awaiting a decision.",
    "REJECTED": "The referral process was rejected; existing referral activity should be reviewed before advising another attempt.",
    "ERROR": "An error occurred during the referral process.",
}


def assess(data):
    status = str(data.get("referral_status", "")).upper()
    card = data.get("card_type") or "the referred card"
    lookup = str(data.get("invitee_lookup", "not_attempted")).lower()
    terms_known = bool(data.get("card_terms_known", False))
    has_identifier = bool(data.get("has_invitee_identifier", False))

    result = {
        "card_type": card,
        "referral_date": data.get("referral_date"),
        "status": status or None,
        "status_meaning": STATUS_MEANINGS.get(status, "The referral status is unavailable or unrecognized; confirm it with the referral system."),
        "customer_message_points": [],
        "next_step": None,
        "privacy_note": "Do not disclose the invitee's account, transaction, or contact details to the referrer.",
    }

    if status == "IN_PROGRESS":
        result["customer_message_points"].append("Card use does not by itself confirm that all qualifying requirements have been met.")
        if card == "Silver Rewards Card" and terms_known:
            result["customer_message_points"].append(
                "For this card, qualification requires approval and at least $750 in spend within 60 days of account opening; the bonus normally posts one to two billing cycles after the threshold is met."
            )
        elif not terms_known:
            result["customer_message_points"].append("The offer requirements vary by card and need confirmation for this card.")
    elif status == "COMPLETE":
        result["customer_message_points"].append("The bonus is handled according to the applicable referral offer terms.")
    elif status == "NO_PROGRESS":
        result["customer_message_points"].append("The referrer may remind the invitee to start an application using the referral link or code.")
    elif status == "APPLIED":
        result["customer_message_points"].append("No manual intervention is needed while the application decision is pending.")
    elif status == "REJECTED":
        result["customer_message_points"].append("Do not retry immediately; a rolling seven-day referral limit may apply and denied referrals cannot be reinstated within that window.")
    elif status == "ERROR":
        result["customer_message_points"].append("Retry later or escalate internally if the condition persists.")

    if lookup == "not_found":
        result["next_step"] = "Ask for the invitee's accurate exact full name or email address; the supplied identifier could not be matched."
    elif lookup in {"unavailable", "not_attempted"}:
        if has_identifier:
            result["next_step"] = "Use the supplied identifier only through the normal authorized lookup workflow, or explain that qualifying spend cannot yet be verified."
        else:
            result["next_step"] = "Ask for a valid exact full name, email address, or user ID if a privacy-safe invitee lookup is needed."
    elif lookup == "matched":
        result["next_step"] = "Use only privacy-safe, authorized workflow results to determine whether qualification can be confirmed; do not disclose invitee account details."
    else:
        result["next_step"] = "Confirm the lookup outcome before making a claim about qualifying spend."
    return result


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(data), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
