#!/usr/bin/env python3
"""Filter extracted documented welcome offers. Reads one JSON object from stdin."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def as_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def numeric(value, field, nullable=False, positive=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not value.is_finite() or value < 0 or (positive and value == 0):
        raise ValueError(f"{field} has an invalid value")
    return value


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    today = as_date(data.get("as_of"), "as_of")
    audience = data.get("desired_audience")
    if audience not in {"personal", "business", "any"}:
        raise ValueError("desired_audience must be personal, business, or any")
    new_customer = data.get("is_new_customer")
    if new_customer not in {True, False, None}:
        raise ValueError("is_new_customer must be true, false, or null")
    invitation_status_known = "invited_offer_ids" in data
    invitations = data.get("invited_offer_ids", [])
    if not isinstance(invitations, list) or not all(isinstance(x, str) for x in invitations):
        raise ValueError("invited_offer_ids must be an array of strings")
    invitations = set(invitations)
    offers = data.get("offers")
    if not isinstance(offers, list):
        raise ValueError("offers must be an array")

    groups = {"eligible": [], "conditional": [], "excluded": [], "unverified": []}
    seen = set()
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("each offer must be an object")
        oid = offer.get("id")
        name = offer.get("card_name")
        if not isinstance(oid, str) or not oid or oid in seen:
            raise ValueError("offer ids must be nonempty and unique")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"offer {oid} needs card_name")
        seen.add(oid)
        offer_audience = offer.get("audience")
        if offer_audience not in {"personal", "business", "any"}:
            raise ValueError(f"offer {oid} has invalid audience")
        amount = numeric(offer.get("reward_amount"), f"offer {oid} reward_amount", positive=True)
        unit = offer.get("reward_unit")
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"offer {oid} needs reward_unit")
        rate = numeric(offer.get("usd_per_reward_unit"), f"offer {oid} usd_per_reward_unit", True, True)
        reasons, unresolved = [], []
        if audience != "any" and offer_audience not in {"any", audience}:
            reasons.append("audience does not match")
        start, end = offer.get("start"), offer.get("end")
        if start is None or end is None:
            unresolved.append("promotion window is incomplete")
        else:
            start_date, end_date = as_date(start, "start"), as_date(end, "end")
            if end_date < start_date:
                raise ValueError(f"offer {oid} ends before it starts")
            if today < start_date:
                reasons.append("offer has not started")
            elif today > end_date:
                reasons.append("offer has ended")
        if offer.get("requires_invitation", False):
            if invitation_status_known and oid not in invitations:
                reasons.append("required invitation is not held")
            elif not invitation_status_known:
                unresolved.append("invitation status is unknown")
        if offer.get("new_customer_required", False):
            if new_customer is False:
                reasons.append("requires a new customer")
            elif new_customer is None:
                unresolved.append("new-customer status is unknown")
        value = amount * rate if rate is not None else None
        record = {"offer_id": oid, "card_name": name.strip(), "reward_amount": str(amount),
                  "reward_unit": unit.strip(), "start": start, "end": end,
                  "cash_equivalent_usd": format(value.quantize(Decimal('0.01')), 'f') if value is not None else None,
                  "reasons": reasons, "unresolved_conditions": unresolved,
                  "spend_requirement_usd": offer.get("spend_requirement_usd"),
                  "qualification_period": offer.get("qualification_period"),
                  "annual_fee_usd": offer.get("annual_fee_usd"),
                  "conditions": offer.get("conditions", [])}
        if reasons:
            groups["excluded"].append(record)
        elif unresolved:
            groups["conditional"].append(record)
        elif value is None:
            record["unresolved_conditions"].append("no documented common USD value")
            groups["unverified"].append(record)
        else:
            groups["eligible"].append(record)

    for key in ("eligible", "conditional"):
        groups[key].sort(key=lambda x: (-Decimal(x["cash_equivalent_usd"]) if x["cash_equivalent_usd"] else Decimal(0), x["offer_id"]))
    pool = "eligible" if groups["eligible"] else "conditional"
    selected = groups[pool][0] if groups[pool] else None
    return {"ok": True, "as_of_date": today.isoformat(), **groups, "recommendation": selected,
            "validation": {"selected_pool": pool if selected else None,
                           "recommendation_is_current": selected is not None,
                           "offer_count_processed": len(offers)}}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
