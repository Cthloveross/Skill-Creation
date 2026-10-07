#!/usr/bin/env python3
"""Classify and rank documented credit-card sign-up awards from JSON stdin.

The caller extracts offer facts from the current task's supplied documents. This
script performs no retrieval, account access, application, or banking action.
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
        raise ValueError(f"{field} is not a valid ISO date") from exc


def decimal_of(value, field, allow_none=False):
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


def usd(value):
    return format(value.quantize(Decimal("0.01")), "f")


def reward_details(offer):
    offer_id = offer["id"]
    reward = offer.get("reward")
    if not isinstance(reward, dict):
        raise ValueError(f"offer {offer_id}: reward must be an object")
    amount = decimal_of(reward.get("amount"), f"offer {offer_id} reward.amount")
    if amount <= 0:
        raise ValueError(f"offer {offer_id}: reward.amount must be positive")
    unit = reward.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError(f"offer {offer_id}: reward.unit must be a nonempty string")

    raw_conversion = reward.get("conversion_usd_per_unit")
    if raw_conversion is None:
        # Dollar-denominated awards require no separate conversion evidence.
        conversion = Decimal("1") if unit.strip().lower() in {
            "usd", "us dollar", "us dollars", "dollar", "dollars", "$"
        } else None
    else:
        conversion = decimal_of(raw_conversion, f"offer {offer_id} conversion_usd_per_unit")
        if conversion <= 0:
            raise ValueError(f"offer {offer_id}: conversion_usd_per_unit must be positive")
    return amount, unit, conversion, amount * conversion if conversion is not None else None


def make_record(offer, status, reasons, conditions, amount, unit, conversion, value):
    annual_fee = decimal_of(
        offer.get("annual_fee_usd"),
        f"offer {offer['id']} annual_fee_usd",
        allow_none=True,
    )
    source = offer.get("source")
    terms = offer.get("terms", [])
    if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
        raise ValueError(f"offer {offer['id']}: terms must be an array of strings")
    return {
        "offer_id": offer["id"],
        "card_name": offer["card_name"],
        "status": status,
        "reward": {
            "amount": str(amount),
            "unit": unit,
            "conversion_usd_per_unit": str(conversion) if conversion is not None else None,
            "cash_equivalent_usd": usd(value) if value is not None else None,
        },
        "offer_window": {"start": offer.get("offer_start"), "end": offer.get("offer_end")},
        "qualification": {
            "spend_requirement_usd": offer.get("spend_requirement_usd"),
            "qualification_months": offer.get("qualification_months"),
            "annual_fee_usd": usd(annual_fee) if annual_fee is not None else None,
        },
        "conditions": conditions,
        "reasons": reasons,
        "terms": terms,
        "source": source if isinstance(source, dict) else None,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload.get("as_of"), "as_of")
    requested = payload.get("desired_audience")
    if requested not in {"personal", "business", "any"}:
        raise ValueError("desired_audience must be personal, business, or any")
    offers = payload.get("offers")
    if not isinstance(offers, list):
        raise ValueError("offers must be an array")

    invitation_known = "invited_offer_ids" in payload
    invited = payload.get("invited_offer_ids", [])
    if invitation_known and (not isinstance(invited, list) or not all(isinstance(x, str) for x in invited)):
        raise ValueError("invited_offer_ids must be an array of strings when supplied")
    invited = set(invited) if invitation_known else set()
    new_customer = payload.get("is_new_customer")
    if new_customer not in {True, False, None}:
        raise ValueError("is_new_customer must be true, false, or null")

    groups = {key: [] for key in ("eligible", "conditional", "excluded", "unverified", "unrankable")}
    seen = set()
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("each offer must be an object")
        offer_id = offer.get("id")
        card_name = offer.get("card_name")
        audience = offer.get("audience")
        if not isinstance(offer_id, str) or not offer_id:
            raise ValueError("every offer needs a nonempty id")
        if offer_id in seen:
            raise ValueError(f"duplicate offer id: {offer_id}")
        seen.add(offer_id)
        if not isinstance(card_name, str) or not card_name:
            raise ValueError(f"offer {offer_id}: card_name is required")
        if audience not in {"personal", "business", "any"}:
            raise ValueError(f"offer {offer_id}: audience must be personal, business, or any")

        amount, unit, conversion, value = reward_details(offer)
        reasons, conditions = [], []
        if requested != "any" and audience not in {"any", requested}:
            reasons.append("card audience does not match the requested audience")

        start_raw, end_raw = offer.get("offer_start"), offer.get("offer_end")
        window_known = start_raw is not None and end_raw is not None
        if not window_known:
            conditions.append("the promotion window is not fully documented")
        else:
            start = parse_date(start_raw, f"offer {offer_id} offer_start")
            end = parse_date(end_raw, f"offer {offer_id} offer_end")
            if end < start:
                raise ValueError(f"offer {offer_id}: offer_end precedes offer_start")
            if as_of < start:
                reasons.append("offer window has not started")
            elif as_of > end:
                reasons.append("offer window has ended")

        if offer.get("requires_invitation", False):
            if invitation_known and offer_id not in invited:
                reasons.append("customer does not have the required invitation")
            elif not invitation_known:
                conditions.append("an invitation is required and invitation status is unknown")
        if offer.get("new_customer_required", False):
            if new_customer is False:
                reasons.append("offer requires a new customer")
            elif new_customer is None:
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
        groups[status].append(make_record(offer, status, reasons, conditions, amount, unit, conversion, value))

    for name in ("eligible", "conditional"):
        groups[name].sort(key=lambda item: (-Decimal(item["reward"]["cash_equivalent_usd"]), item["offer_id"]))
    pool = "eligible" if groups["eligible"] else "conditional"
    selected = groups[pool][0] if groups[pool] else None
    recommendation = None
    if selected is not None:
        recommendation = dict(selected)
        recommendation["selection_basis"] = (
            "highest documented cash-equivalent value among currently eligible offers"
            if pool == "eligible" else
            "highest documented cash-equivalent value among currently active conditional offers; disclose listed conditions"
        )

    return {
        "ok": True,
        "as_of_date": as_of.isoformat(),
        "recommendation": recommendation,
        **groups,
        "validation": {
            "recommendation_is_current": selected is not None,
            "selection_is_maximum_in_selected_pool": selected is None or selected == groups[pool][0],
            "selected_pool": pool if selected is not None else None,
            "offer_count_processed": len(offers),
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps(fail(str(exc)), ensure_ascii=False, sort_keys=True))
