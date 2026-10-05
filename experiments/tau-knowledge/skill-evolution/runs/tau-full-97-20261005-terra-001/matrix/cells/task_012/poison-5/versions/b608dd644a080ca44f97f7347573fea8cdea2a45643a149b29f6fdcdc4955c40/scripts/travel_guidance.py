#!/usr/bin/env python3
"""Draft evidence-bounded international-travel card guidance from JSON stdin."""
import json
import sys

VALID_STATUSES = {"not_checked", "found", "not_found", "out_of_scope"}


def text_or(value, fallback=""):
    """Return a stripped string value, or a safe fallback."""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def support_message():
    return (
        "If you can't find an International Use or Travel Notification setting, contact "
        "Rho-Bank customer service, use in-app chat, or visit rhobank.com/help for an "
        "account-specific review of possible international restrictions or fraud holds. "
        "Use the same support path if your card is declined abroad or overseas despite "
        "available credit."
    )


def build_message(destination, dates_known, status, include_fee_note):
    place = destination or "your destination"
    parts = []

    if not dates_known:
        parts.append(
            f"You can prepare your Platinum Rewards Card for {place} before your exact "
            "dates are final. If the control you find asks for dates, enter them once confirmed."
        )

    if status in {"not_checked", "out_of_scope"}:
        parts.append(
            "In the app or online account, open your Platinum Rewards Card and look under "
            "Card Controls first. Then check Security or Alerts for International Use, "
            "International Alerts, Travel Alerts, or Travel Notification. These are labels "
            "to look for; available options may vary."
        )
        parts.append(
            "If you find an international-use or travel control, follow the fields shown "
            "and review its confirmation before relying on it."
        )
        parts.append(support_message())
    elif status == "found":
        parts.append(
            "Use the international-use or travel control you found and complete only the "
            "fields shown. If it requests dates, use the dates once confirmed, then review "
            "the confirmation displayed by the app or website."
        )
        parts.append(
            "If your card is declined abroad or overseas despite available credit, contact "
            "Rho-Bank customer service, use in-app chat, or visit rhobank.com/help for an "
            "account-specific review of possible international restrictions or fraud holds."
        )
    else:  # not_found
        parts.append(support_message())

    parts.append(
        "Also enable transaction and international-use alerts, keep your phone number and "
        "email current, and respond to fraud-verification prompts within 17 minutes. "
        "Reachable contact details help you receive and handle those time-sensitive prompts."
    )
    parts.append("Carry a backup payment method and retain receipts for travel purchases.")

    if include_fee_note:
        parts.append(
            "Your Platinum Rewards Card has a 0% Rho-Bank foreign transaction fee on "
            "international purchases."
        )

    return " ".join(parts)


def main(payload):
    destination = text_or(payload.get("destination"), "your Japan trip")
    timing = text_or(payload.get("trip_timing"))
    dates_known = bool(payload.get("dates_known", False))
    status = text_or(payload.get("latest_lookup_status"), "not_checked").lower()
    include_fee_note = bool(payload.get("include_fee_note", True))
    issues = []

    if status not in VALID_STATUSES:
        issues.append(
            "latest_lookup_status must be not_checked, found, not_found, or out_of_scope"
        )
        status = "not_checked"
    if dates_known and not timing:
        issues.append(
            "dates_known is true but trip_timing is blank; do not state unprovided dates"
        )

    if status in {"not_checked", "out_of_scope"}:
        next_action = (
            "Open the Platinum Rewards Card and look under Card Controls first for an "
            "international-use or travel option."
        )
    elif status == "found":
        next_action = "Complete only the fields displayed by the travel or international-use control."
    else:
        next_action = "Contact Rho-Bank customer service, in-app chat, or rhobank.com/help."

    return {
        "recommended_message": build_message(
            destination, dates_known, status, include_fee_note
        ),
        "next_customer_action": next_action,
        "support_needed_if": (
            "The customer can't find the setting, the card is declined abroad or overseas, "
            "or an international restriction or fraud hold needs account-specific review."
        ),
        "validation": {"valid": not issues, "issues": issues},
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "error": str(exc),
            "validation": {"valid": False, "issues": [str(exc)]},
        }))
        sys.exit(1)
