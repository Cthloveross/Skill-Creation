#!/usr/bin/env python3
"""Rank documented savings/card combinations by static one-year net return.

Reads one JSON object from stdin and emits one JSON object to stdout. No network,
filesystem, banking, or tool actions are performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def decimal_value(value, field, candidate_id=None):
    label = field if candidate_id is None else f"{candidate_id}.{field}"
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a number or decimal string")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a number or decimal string")
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    return format(value.normalize(), "f")


def reject(candidate_id, reason, notes):
    return {"id": candidate_id, "reason": reason, "notes": notes}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = decimal_value(payload.get("deposit"), "deposit")
    if deposit <= 0:
        raise ValueError("deposit must be greater than zero")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")

    ranked = []
    rejected = []
    seen_ids = set()
    required = ("id", "base_apy_pct", "annual_card_fee", "opening_minimum", "ongoing_minimum", "eligible")

    for raw in candidates:
        if not isinstance(raw, dict):
            raise ValueError("each candidate must be an object")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError("candidate missing required field(s): " + ", ".join(missing))
        candidate_id = raw["id"]
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("candidate.id must be a nonempty string")
        if candidate_id in seen_ids:
            raise ValueError(f"duplicate candidate id: {candidate_id}")
        seen_ids.add(candidate_id)
        if not isinstance(raw["eligible"], bool):
            raise ValueError(f"{candidate_id}.eligible must be boolean")
        notes = raw.get("notes", [])
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            raise ValueError(f"{candidate_id}.notes must be an array of strings")

        base = decimal_value(raw["base_apy_pct"], "base_apy_pct", candidate_id)
        fee = decimal_value(raw["annual_card_fee"], "annual_card_fee", candidate_id)
        opening_minimum = decimal_value(raw["opening_minimum"], "opening_minimum", candidate_id)
        ongoing_minimum = decimal_value(raw["ongoing_minimum"], "ongoing_minimum", candidate_id)
        bonuses_raw = raw.get("card_bonus_pcts", [])
        if not isinstance(bonuses_raw, list):
            raise ValueError(f"{candidate_id}.card_bonus_pcts must be an array")
        bonuses = [decimal_value(value, "card_bonus_pcts", candidate_id) for value in bonuses_raw]

        if min(base, fee, opening_minimum, ongoing_minimum, *(bonuses or [Decimal(0)])) < 0:
            raise ValueError(f"{candidate_id} contains a negative rate, fee, or minimum")
        if not raw["eligible"]:
            rejected.append(reject(candidate_id, "mandatory eligibility condition is not satisfied", notes))
            continue
        if deposit < opening_minimum:
            rejected.append(reject(candidate_id, "deposit is below documented opening minimum", notes))
            continue
        if deposit < ongoing_minimum:
            rejected.append(reject(candidate_id, "deposit is below documented ongoing minimum", notes))
            continue

        # Policy: card APY bonuses do not stack; choose the single highest bonus.
        selected_bonus = max(bonuses) if bonuses else Decimal(0)
        total_apy = base + selected_bonus
        projected_interest = deposit * total_apy / Decimal(100)
        net_return = projected_interest - fee
        ranked.append({
            "id": candidate_id,
            "base_apy_pct": percent(base),
            "selected_card_bonus_pct": percent(selected_bonus),
            "combined_apy_pct": percent(total_apy),
            "annual_card_fee": money(fee),
            "projected_interest": money(projected_interest),
            "projected_net_return": money(net_return),
            "notes": notes,
        })

    ranked.sort(key=lambda item: (
        Decimal(item["projected_net_return"]),
        Decimal(item["combined_apy_pct"]),
        item["id"],
    ), reverse=True)
    return {
        "deposit": money(deposit),
        "assumption": "Static balance for one year; APY is treated as annualized yield; only the highest card bonus is used.",
        "ranked": ranked,
        "rejected": rejected,
        "best": ranked[0] if ranked else None,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":"), sort_keys=True))
        sys.exit(1)
