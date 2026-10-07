#!/usr/bin/env python3
"""Produce evidence-bounded international-travel card guidance from JSON stdin."""
import json
import sys

VALID_STATUSES = {"not_checked", "found", "not_found", "out_of_scope"}


def clean_text(value, fallback):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def build_message(destination, timing, dates_known, status, include_fee_note):
    destination_phrase = f" for {destination}" if destination else ""
    parts = []
    if not dates_known:
        parts.append(
            f"You can start preparing{destination_phrase} even before your exact dates are final. "
            "If a travel-related control asks for dates, enter them once they are confirmed."
        )

    if status in {"not_checked", "out_of_scope"}:
        parts.append(
            "In the app or online account, open your Platinum Rewards Card and check Card Controls first; "
            "then check Security or Alerts for an option labeled International Use, International Alerts, "
            "Travel Alerts, or Travel Notification. These are labels to look for, and the available options "
            "may vary."
        )
        parts.append(
            "If you find an international-use or travel option, follow the fields shown and confirm the "
            "information before saving."
        )
    elif status == "found":
        parts.append(
            "Use the international-use or travel option you found and complete only the fields displayed. "
            "Use your confirmed travel dates if the option requests them, then review the confirmation shown "
            "by the app or website."
        )
    else:  # not_found
        parts.append(
            "If you do not see an international-use or travel option in Card Controls, Security, or Alerts, "
            "there may not be a self-service setting available in your view. Contact customer service before "
            "departure so they can check for an international restriction or fraud-related hold."
        )

    parts.append(
        "Also enable transaction and international-use alerts, keep your phone and email current, and watch "
        "for verification prompts because unusual overseas activity can be flagged. Carry a backup payment "
        "method in case a merchant or network cannot process the card."
    )
    if include_fee_note:
        parts.append(
            "Your Platinum Rewards Card has a 0% Rho-Bank foreign transaction fee. Merchant conversion charges "
            "and network exchange rates are separate, so compare the total if a merchant offers currency conversion."
        )
    return " ".join(parts)


def main(payload):
    destination = clean_text(payload.get("destination"), "your destination")
    timing = clean_text(payload.get("trip_timing"), "")
    dates_known = bool(payload.get("dates_known", False))
    status = clean_text(payload.get("latest_lookup_status"), "not_checked").lower()
    include_fee_note = bool(payload.get("include_fee_note", True))

    issues = []
    if status not in VALID_STATUSES:
        issues.append("latest_lookup_status must be not_checked, found, not_found, or out_of_scope")
        status = "not_checked"
    if dates_known and not timing:
        issues.append("dates_known is true but no trip_timing was supplied; avoid stating dates in the response")

    message = build_message(destination, timing, dates_known, status, include_fee_note)
    if status in {"not_checked", "out_of_scope"}:
        next_action = "Open the Platinum Rewards Card and look under Card Controls first."
    elif status == "found":
        next_action = "Complete and review the fields that the displayed travel or international-use control provides."
    else:
        next_action = "Contact customer service to check for an international restriction or fraud-related hold."

    return {
        "recommended_message": message,
        "next_customer_action": next_action,
        "support_needed_if": (
            "The international-use/travel setting is unavailable, the card is declined, or the customer needs "
            "an account-specific restriction or fraud-alert review."
        ),
        "validation": {"valid": not issues, "issues": issues},
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "validation": {"valid": False, "issues": [str(exc)]}}))
        sys.exit(1)
