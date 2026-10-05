#!/usr/bin/env python3
"""Draft evidence-bounded international-travel card guidance from JSON stdin."""
import json
import sys

VALID_STATUSES = {"not_checked", "found", "not_found", "out_of_scope"}


def text_or(value, fallback=""):
    """Return a stripped text value or the supplied fallback."""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def boolean_or(value, fallback, field_name, issues):
    """Accept only JSON booleans, recording invalid supplied values."""
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    issues.append(f"{field_name} must be a JSON boolean")
    return fallback


def support_message():
    return (
        "If you can't find an International Use or Travel Notification setting, contact "
        "Rho-Bank customer service, use in-app chat, or visit rhobank.com/help for an "
        "account-specific review of possible international restrictions or fraud holds. "
        "Use the same support path if your card is declined abroad despite available credit."
    )


def build_message(card_name, destination, dates_known, status, include_fee_note):
    place = destination or "your destination"
    card = card_name or "your card"
    parts = []

    if not dates_known:
        parts.append(
            f"You can prepare your {card} for {place} before your exact dates are final. "
            "Enter dates once your dates are confirmed, and only if a displayed control asks for them."
        )

    if status in {"not_checked", "out_of_scope"}:
        parts.append(
            f"In the app or online account, open your {card} and look under Card Controls first. "
            "Then check Security or Alerts for International Use, International Alerts, Travel "
            "Alerts, or Travel Notification. These are labels to look for; available options may vary."
        )
        parts.append(
            "If you find one, follow the fields shown and review the displayed confirmation before relying on it."
        )
        parts.append(support_message())
    elif status == "found":
        parts.append(
            "If you find the international-use or travel control, follow the fields shown and "
            "review the displayed confirmation before relying on it."
        )
        if dates_known:
            parts.append(
                "Use only the confirmed dates and only if the displayed control requests dates."
            )
        else:
            parts.append(
                "If it requests dates, enter them once your dates are confirmed."
            )
        parts.append(
            "If your card is declined abroad despite available credit, contact Rho-Bank customer "
            "service, use in-app chat, or visit rhobank.com/help for an account-specific review of "
            "possible international restrictions or fraud holds."
        )
    else:  # not_found
        parts.append(support_message())

    parts.append(
        "Also enable transaction and international-use alerts, keep your phone number and email "
        "current, and respond to fraud-verification prompts within 17 minutes. Current contact "
        "details help you receive and handle those time-sensitive verification prompts."
    )
    parts.append("Carry a backup payment method and retain receipts for travel purchases.")

    if include_fee_note and card_name.lower() == "platinum rewards card":
        parts.append(
            "The Platinum Rewards Card has a 0% Rho-Bank foreign transaction fee on international purchases."
        )

    return " ".join(parts)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    issues = []
    card_name = text_or(payload.get("card_name"), "your card")
    destination = text_or(payload.get("destination"), "your destination")
    timing = text_or(payload.get("trip_timing"))
    dates_known = boolean_or(payload.get("dates_known"), False, "dates_known", issues)
    include_fee_note = boolean_or(
        payload.get("include_fee_note"), True, "include_fee_note", issues
    )
    status = text_or(payload.get("latest_lookup_status"), "not_checked").lower()

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
            f"Open your {card_name} in the app or online account and look under Card Controls first."
        )
    elif status == "found":
        next_action = "Follow only the fields shown by the international-use or travel control."
    else:
        next_action = "Contact Rho-Bank customer service, in-app chat, or rhobank.com/help."

    return {
        "recommended_message": build_message(
            card_name, destination, dates_known, status, include_fee_note
        ),
        "next_customer_action": next_action,
        "support_needed_if": (
            "The customer can't find the setting, the card is declined abroad despite available "
            "credit, or an international restriction or fraud hold needs account-specific review."
        ),
        "validation": {"valid": not issues, "issues": issues},
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "error": str(exc),
            "validation": {"valid": False, "issues": [str(exc)]},
        }))
        sys.exit(1)
