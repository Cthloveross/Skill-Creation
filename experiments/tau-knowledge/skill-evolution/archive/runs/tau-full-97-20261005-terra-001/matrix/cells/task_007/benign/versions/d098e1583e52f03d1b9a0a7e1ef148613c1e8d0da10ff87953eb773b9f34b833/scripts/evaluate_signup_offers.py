#!/usr/bin/env python3
"""Filter and rank extracted documented welcome offers from JSON on stdin."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def decimal_value(value, field, nullable=False, positive=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f"{field} has an invalid value")
    return result


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    as_of = parse_date(data.get("as_of"), "as_of")
    audience = data.get("desired_audience")
    if audience not in {"personal", "business", "any"}:
        raise ValueError("desired_audience must be personal, business, or any")
    new_customer = data.get("is_new_customer")
    if new_customer not in {True, False, None}:
        raise ValueError("is_new_customer must be true, false, or null")

    invitation_status_known = "invited_offer_ids" in data
    invited = data.get("invited_offer_ids", [])
    if not isinstance(invited, list) or not all(isinstance(item, str) for item in invited):
        raise ValueError("invited_offer_ids must be an array of strings")
    invited = set(invited)

    offers = data.get("offers")
    if not isinstance(offers, list):
        raise ValueError("offers must be an array")

    groups = {"eligible": [], "conditional": [], "excluded": [], "unverified": []}
    seen_ids = set()
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("each offer must be an object")
        offer_id = offer.get("id")
        card_name = offer.get("card_name")
        if not isinstance(offer_id, str) or not offer_id or offer_id in seen_ids:
            raise ValueError("offer ids must be nonempty and unique")
        if not isinstance(card_name, str) or not card_name.strip():
            raise ValueError(f"offer {offer_id} needs card_name")
        seen_ids.add(offer_id)

        offer_audience = offer.get("audience")
        if offer_audience not in {"personal", "business", "any"}:
            raise ValueError(f"offer {offer_id} has invalid audience")
        reward_amount = decimal_value(offer.get("reward_amount"), f"offer {offer_id} reward_amount", positive=True)
        reward_unit = offer.get("reward_unit")
        if not isinstance(reward_unit, str) or not reward_unit.strip():
            raise ValueError(f"offer {offer_id} needs reward_unit")
        rate = decimal_value(
            offer.get("usd_per_reward_unit"),
            f"offer {offer_id} usd_per_reward_unit",
            nullable=True,
            positive=True,
        )

        exclusions, unresolved = [], []
        if audience != "any" and offer_audience not in {"any", audience}:
            exclusions.append("audience does not match")

        start, end = offer.get("start"), offer.get("end")
        if start is None or end is None:
            unresolved.append("promotion window is incomplete")
        else:
            start_date = parse_date(start, f"offer {offer_id} start")
            end_date = parse_date(end, f"offer {offer_id} end")
            if end_date < start_date:
                raise ValueError(f"offer {offer_id} ends before it starts")
            if as_of < start_date:
                exclusions.append("offer has not started")
            elif as_of > end_date:
                exclusions.append("offer has ended")

        if offer.get("requires_invitation", False):
            if invitation_status_known and offer_id not in invited:
                exclusions.append("required invitation is not held")
            elif not invitation_status_known:
                unresolved.append("invitation status is unknown")
        if offer.get("new_customer_required", False):
            if new_customer is False:
                exclusions.append("requires a new customer")
            elif new_customer is None:
                unresolved.append("new-customer status is unknown")

        cash_value = reward_amount * rate if rate is not None else None
        record = {
            "offer_id": offer_id,
            "card_name": card_name.strip(),
            "reward_amount": str(reward_amount),
            "reward_unit": reward_unit.strip(),
            "start": start,
            "end": end,
            "cash_equivalent_usd": (format(cash_value.quantize(Decimal("0.01")), "f") if cash_value is not None else None),
            "spend_requirement_usd": offer.get("spend_requirement_usd"),
            "qualification_period": offer.get("qualification_period"),
            "annual_fee_usd": offer.get("annual_fee_usd"),
            "conditions": offer.get("conditions", []),
            "reasons": exclusions,
            "unresolved_conditions": unresolved,
        }
        if exclusions:
            groups["excluded"].append(record)
        elif unresolved:
            groups["conditional"].append(record)
        elif cash_value is None:
            record["unresolved_conditions"].append("no documented common USD value")
            groups["unverified"].append(record)
        else:
            groups["eligible"].append(record)

    for group in ("eligible", "conditional"):
        groups[group].sort(
            key=lambda item: (
                -Decimal(item["cash_equivalent_usd"]) if item["cash_equivalent_usd"] is not None else Decimal(0),
                item["offer_id"],
            )
        )
    selected_pool = "eligible" if groups["eligible"] else "conditional"
    selected = groups[selected_pool][0] if groups[selected_pool] else None
    return {
        "ok": True,
        "as_of_date": as_of.isoformat(),
        **groups,
        "recommendation": selected,
        "validation": {
            "selected_pool": selected_pool if selected else None,
            "recommendation_is_current": selected is not None,
            "offer_count_processed": len(offers),
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
