#!/usr/bin/env python3
"""Rank documented credit-card sign-up awards from JSON stdin.

This helper performs no external retrieval. All promotion facts and conversions
must be supplied by the caller from the current task materials.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def fail(message):
    return {"ok": False, "error": message}


def parse_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must be an ISO date or timestamp")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO date: {value}") from exc


def decimal_value(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite non-negative decimal")
    return result


def money_text(value):
    return format(value.quantize(Decimal("0.01")), "f")


def source_of(offer):
    source = offer.get("source")
    return source if isinstance(source, dict) else None


def reward_value(reward, offer_id):
    if not isinstance(reward, dict):
        raise ValueError(f"offer {offer_id}: reward must be an object")
    amount = decimal_value(reward.get("amount"), f"offer {offer_id} reward.amount")
    if amount <= 0:
        raise ValueError(f"offer {offer_id}: reward.amount must be positive")
    unit = reward.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError(f"offer {offer_id}: reward.unit must be a nonempty string")

    conversion_raw = reward.get("conversion_usd_per_unit")
    if conversion_raw is not None:
        conversion = decimal_value(
            conversion_raw, f"offer {offer_id} reward.conversion_usd_per_unit"
        )
        if conversion <= 0:
            raise ValueError(f"offer {offer_id}: conversion must be positive")
    elif unit.strip().lower() in {"usd", "us dollar", "us dollars", "dollar", "dollars", "$"}:
        conversion = Decimal("1")
    else:
        conversion = None

    return amount, unit, conversion, (amount * conversion if conversion else None)


def candidate_record(offer, status, reasons, conditions, amount, unit, conversion, value):
    result = {
        "offer_id": offer["id"],
        "card_name": offer["card_name"],
        "status": status,
        "reward": {
            "amount": str(amount),
            "unit": unit,
            "conversion_usd_per_unit": str(conversion) if conversion is not None else None,
            "cash_equivalent_usd": money_text(value) if value is not None else None,
        },
        "offer_window": {
            "start": offer.get("offer_start"),
            "end": offer.get("offer_end"),
        },
        "qualification": {
            "spend_requirement_usd": offer.get("spend_requirement_usd"),
            "qualification_months": offer.get("qualification_months"),
        },
        "conditions": conditions,
        "reasons": reasons,
        "terms": offer.get("terms", []),
        "source": source_of(offer),
    }
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload.get("as_of"), "as_of")
    desired_audience = payload.get("desired_audience")
    if desired_audience not in {"personal", "business", "any"}:
        raise ValueError("desired_audience must be personal, business, or any")
    offers = payload.get("offers")
    if not isinstance(offers, list):
        raise ValueError("offers must be an array")

    invitation_known = "invited_offer_ids" in payload
    invited = payload.get("invited_offer_ids", [])
    if invitation_known and not isinstance(invited, list):
        raise ValueError("invited_offer_ids must be an array when supplied")
    invited = set(invited) if invitation_known else set()

    new_status = payload.get("is_new_customer", None)
    if new_status not in {True, False, None}:
        raise ValueError("is_new_customer must be true, false, or null")

    groups = {
        "eligible": [],
        "conditional": [],
        "excluded": [],
        "unverified": [],
        "unrankable": [],
    }
    seen_ids = set()

    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("each offer must be an object")
        offer_id = offer.get("id")
        card_name = offer.get("card_name")
        audience = offer.get("audience")
        if not isinstance(offer_id, str) or not offer_id:
            raise ValueError("every offer needs a nonempty id")
        if offer_id in seen_ids:
            raise ValueError(f"duplicate offer id: {offer_id}")
        seen_ids.add(offer_id)
        if not isinstance(card_name, str) or not card_name:
            raise ValueError(f"offer {offer_id}: card_name is required")
        if audience not in {"personal", "business", "any"}:
            raise ValueError(f"offer {offer_id}: audience must be personal, business, or any")

        amount, unit, conversion, value = reward_value(offer.get("reward"), offer_id)
        reasons = []
        conditions = []
        if desired_audience != "any" and audience not in {"any", desired_audience}:
            reasons.append("card audience does not match the requested audience")

        start_raw = offer.get("offer_start")
        end_raw = offer.get("offer_end")
        window_known = start_raw is not None and end_raw is not None
        if window_known:
            start = parse_date(start_raw, f"offer {offer_id} offer_start")
            end = parse_date(end_raw, f"offer {offer_id} offer_end")
            if end < start:
                raise ValueError(f"offer {offer_id}: offer_end precedes offer_start")
            if as_of < start:
                reasons.append("offer window has not started")
            elif as_of > end:
                reasons.append("offer window has ended")
        else:
            conditions.append("the promotion window is not fully documented")

        if offer.get("requires_invitation", False):
            if invitation_known:
                if offer_id not in invited:
                    reasons.append("customer does not have the required invitation")
            else:
                conditions.append("an invitation is required and invitation status is unknown")

        if offer.get("new_customer_required", False):
            if new_status is False:
                reasons.append("offer requires a new customer")
            elif new_status is None:
                conditions.append("offer requires confirmation that the customer is new")

        if reasons:
            status = "excluded"
        elif not window_known:
            status = "unverified"
        elif value is None:
            status = "unrankable"
            reasons.append("no documented USD conversion for the reward unit")
        elif conditions:
            status = "conditional"
        else:
            status = "eligible"

        record = candidate_record(
            offer, status, reasons, conditions, amount, unit, conversion, value
        )
        groups[status].append(record)

    for name in ("eligible", "conditional"):
        groups[name].sort(
            key=lambda item: (
                -Decimal(item["reward"]["cash_equivalent_usd"]),
                item["offer_id"],
            )
        )

    selected_pool = "eligible" if groups["eligible"] else "conditional"
    selected = groups[selected_pool][0] if groups[selected_pool] else None
    recommendation = None
    if selected is not None:
        recommendation = dict(selected)
        recommendation["selection_basis"] = (
            "highest documented cash-equivalent value among currently eligible offers"
            if selected_pool == "eligible"
            else "highest documented cash-equivalent value among currently active conditional offers; disclose the listed conditions"
        )

    output = {
        "ok": True,
        "as_of_date": as_of.isoformat(),
        "recommendation": recommendation,
        "eligible": groups["eligible"],
        "conditional": groups["conditional"],
        "excluded": groups["excluded"],
        "unverified": groups["unverified"],
        "unrankable": groups["unrankable"],
        "validation": {
            "recommendation_is_current": selected is not None,
            "selection_is_maximum_in_selected_pool": (
                selected is None or selected == groups[selected_pool][0]
            ),
            "selected_pool": selected_pool if selected is not None else None,
            "offer_count_processed": len(offers),
        },
    }
    return output


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps(fail(str(exc)), ensure_ascii=False, sort_keys=True))
