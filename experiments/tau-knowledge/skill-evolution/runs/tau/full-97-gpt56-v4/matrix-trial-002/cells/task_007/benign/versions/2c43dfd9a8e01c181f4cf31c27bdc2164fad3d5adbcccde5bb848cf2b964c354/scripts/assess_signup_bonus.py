#!/usr/bin/env python3
"""Assess documented personal-card cash-back/points sign-up offers.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the input schema. No external dependencies are required.
"""
import json
import os
import sys
from datetime import date


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "references", "documented_offers.json"), encoding="utf-8") as fh:
    DATA = json.load(fh)


def parse_date(value):
    """Return an ISO date from an ISO-leading timestamp, or None if unavailable."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def yes_no_unknown(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def main(payload):
    offer = DATA["ecocard"]
    today = parse_date(payload.get("current_time"))
    start = date.fromisoformat(offer["offer_start"])
    end = date.fromisoformat(offer["offer_end"])
    active = today is not None and start <= today <= end
    new_customer = payload.get("is_new_customer")
    capacity = payload.get("can_spend_5000_in_one_month")
    scope_ok = payload.get("personal_bonus_only")

    value = offer["bonus_points"] * offer["point_redemption_value_usd"]
    offer_result = {
        "card": offer["card_name"],
        "documented": True,
        "active": active,
        "offer_window": {"start": offer["offer_start"], "end": offer["offer_end"]},
        "bonus_points": offer["bonus_points"],
        "documented_redemption_value_usd": value,
        "spend_requirement_usd": offer["spend_requirement_usd"],
        "spend_period": offer["spend_period"],
        "new_customer_status": yes_no_unknown(new_customer),
        "spend_capacity_status": yes_no_unknown(capacity)
    }

    limitations = [
        "The available documentation establishes no personal cash-back or points sign-up bonus for Silver Rewards Card or Platinum Rewards Card. Their documented APR or ongoing-reward features are not sign-up bonuses.",
        "The documentation is not a complete inventory of every possible card offer, so no bank-wide 'best bonus' claim can be made."
    ]
    if today is None:
        limitations.insert(0, "A valid current date was not supplied, so offer-window status cannot be confirmed.")

    lines = []
    if scope_ok is False:
        lines.append("This assessment is limited to the documented personal cash-back or points sign-up offers; other promotion types were not evaluated.")

    if active:
        lines.append(
            "The only documented personal cash-back or points sign-up offer is the EcoCard promotion, active from "
            f"{offer['offer_start']} through {offer['offer_end']}."
        )
        lines.append(
            f"It offers {offer['bonus_points']:,} sustainability points after at least ${offer['spend_requirement_usd']:,} in eligible purchases within the {offer['spend_period']}. "
            f"At the documented $0.01-per-point redemption value, that is ${value:,.2f} in redemption value—not ${offer['bonus_points']:,} in cash."
        )
        lines.append(
            "It also requires that you be a new customer and that the account be open and in good standing when the bonus is awarded. "
            + offer["eligible_spend_notes"]
        )
        if new_customer is False:
            lines.append("Because you are not a new customer, you would not meet this documented offer's new-customer requirement.")
        elif capacity is False:
            lines.append(
                f"Because you said you cannot spend ${offer['spend_requirement_usd']:,} in eligible purchases within one month, this sign-up bonus would not be attainable for you under its documented terms."
            )
        elif new_customer is None or capacity is None:
            missing = []
            if new_customer is None:
                missing.append("whether you are a new Rho-Bank credit-card customer")
            if capacity is None:
                missing.append(f"whether you can spend ${offer['spend_requirement_usd']:,} in eligible purchases in one month")
            lines.append("To determine whether you qualify, please confirm " + " and ".join(missing) + ".")
        else:
            lines.append("Based on the supplied answers, you appear able to meet the stated new-customer and spending conditions; final qualification also depends on eligible purchases and the account being open and in good standing at award time.")
        lines.append(offer["posting"] + f" The documented annual fee is ${offer['annual_fee_usd']:,.2f}.")
    elif today is not None:
        lines.append(
            "No currently active documented personal cash-back or points sign-up bonus can be confirmed from these materials: the EcoCard offer window was "
            f"{offer['offer_start']} through {offer['offer_end']}, and the supplied date is {today.isoformat()}."
        )
    else:
        lines.append(
            "The documented personal cash-back or points sign-up offer is EcoCard, but its current availability cannot be confirmed without a valid current date. "
            f"Its stated window is {offer['offer_start']} through {offer['offer_end']}."
        )

    return {"response": "\n\n".join(lines), "offers": [offer_result], "limitations": limitations}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "response": "Unable to assess the documented offers because the input was invalid."}))
        sys.exit(1)
