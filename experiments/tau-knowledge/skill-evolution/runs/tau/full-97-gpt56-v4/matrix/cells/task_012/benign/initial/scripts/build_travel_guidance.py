#!/usr/bin/env python3
"""Create policy-bounded international travel card guidance from JSON stdin."""

import json
import sys


def require_bool(data, key, default):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def optional_text(data, key):
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def build(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")

    dates_finalized = require_bool(data, "dates_finalized", False)
    asks_setup_method = require_bool(data, "asks_setup_method", False)
    asks_timing = require_bool(data, "asks_timing", False)
    international_card = require_bool(data, "international_card", True)
    card_name = optional_text(data, "card_name")
    destination = optional_text(data, "destination")

    subject = card_name if card_name else "your card"
    place = f" for travel to {destination}" if destination else ""
    sentences = []
    unsupported = []

    if international_card:
        sentences.append(
            f"International restrictions can sometimes contribute to a decline when using {subject} abroad{place}."
        )

    if card_name.lower() == "platinum rewards card":
        sentences.append(
            "The Platinum Rewards Card has a 0% foreign transaction fee on international purchases."
        )

    if asks_setup_method:
        sentences.append(
            "The available policy does not confirm a self-service travel-notification option in the app or a form to complete."
        )
        unsupported.append("Whether a self-service app workflow or form exists")

    if asks_timing:
        sentences.append(
            "The available policy also does not specify how far in advance a travel notification must be arranged."
        )
        unsupported.append("Required advance-notice period")

    if not dates_finalized:
        sentences.append(
            "Once your itinerary is finalized, contact support to ask them to review any applicable international restrictions or fraud alerts."
        )
        next_step = "Finalize the itinerary, then contact support to review international-use restrictions."
    else:
        sentences.append(
            "Contact support with your finalized itinerary and ask them to review any applicable international restrictions or fraud alerts."
        )
        next_step = "Contact support with the finalized itinerary to review international-use restrictions."

    sentences.append(
        "You can reach support at 1-800-RHO-BANK, through mobile-app chat, or at rhobank.com/help."
    )

    return {
        "response": " ".join(sentences),
        "unsupported_details": unsupported,
        "next_step": next_step,
    }


def main():
    try:
        data = json.load(sys.stdin)
        print(json.dumps(build(data), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
