#!/usr/bin/env python3
"""Calculate disclosed ATM bank fees from JSON stdin; emit JSON stdout."""
import json
import math
import sys


def money(value):
    return round(value + 0.0, 2)


def nonnegative_number(value, label):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a non-negative finite number")
    return float(value)


def fee_for_withdrawal(amount, rule, ordinal):
    kind = rule.get("kind")
    if kind == "flat":
        return nonnegative_number(rule.get("fee"), "fee")
    if kind == "percentage_min_max":
        pct = nonnegative_number(rule.get("percentage"), "percentage")
        fee = amount * pct
        if rule.get("minimum") is not None:
            fee = max(fee, nonnegative_number(rule["minimum"], "minimum"))
        if rule.get("maximum") is not None:
            fee = min(fee, nonnegative_number(rule["maximum"], "maximum"))
        return fee
    if kind == "free_allowance_then_flat":
        free_count = rule.get("free_count")
        if not isinstance(free_count, int) or isinstance(free_count, bool) or free_count < 0:
            raise ValueError("free_count must be a non-negative integer")
        return 0.0 if ordinal <= free_count else nonnegative_number(rule.get("fee_after_free"), "fee_after_free")
    if kind == "tiered":
        tiers = rule.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("tiers must be a nonempty list")
        previous = -1.0
        for tier in tiers:
            if not isinstance(tier, dict):
                raise ValueError("each tier must be an object")
            ceiling = tier.get("up_to")
            if ceiling is not None:
                ceiling = nonnegative_number(ceiling, "tier up_to")
                if ceiling < previous:
                    raise ValueError("tier ceilings must be ordered")
                previous = ceiling
            fee = nonnegative_number(tier.get("fee"), "tier fee")
            if ceiling is None or amount <= ceiling:
                return fee
        raise ValueError("tiers need a final null up_to tier for amounts above the last ceiling")
    raise ValueError("unsupported fee_rule.kind")


def validate_months(value):
    if not isinstance(value, list):
        raise ValueError("withdrawals_by_month must be a list")
    months = []
    for i, month in enumerate(value, 1):
        if not isinstance(month, list):
            raise ValueError(f"month {i} must be a list")
        months.append([nonnegative_number(a, f"month {i} withdrawal") for a in month])
    return months


def evaluate_offer(offer, months):
    if not isinstance(offer, dict) or not isinstance(offer.get("name"), str) or not offer["name"].strip():
        raise ValueError("each offer requires a nonempty name")
    eligible = offer.get("eligible")
    if not isinstance(eligible, bool):
        raise ValueError(f"{offer['name']}: eligible must be boolean")
    if not eligible:
        return {"name": offer["name"], "eligible": False, "monthly_bank_fees": [], "trip_bank_fee": None}
    rule = offer.get("fee_rule")
    if not isinstance(rule, dict):
        raise ValueError(f"{offer['name']}: fee_rule must be an object")
    totals = []
    for month in months:
        total = sum(fee_for_withdrawal(amount, rule, n) for n, amount in enumerate(month, 1))
        totals.append(money(total))
    return {"name": offer["name"], "eligible": True, "monthly_bank_fees": totals, "trip_bank_fee": money(sum(totals))}


def main(data):
    try:
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        months = validate_months(data.get("withdrawals_by_month"))
        offers = data.get("offers")
        if not isinstance(offers, list) or not offers:
            raise ValueError("offers must be a nonempty list")
        results, errors = [], []
        for index, offer in enumerate(offers):
            try:
                results.append(evaluate_offer(offer, months))
            except (ValueError, KeyError, TypeError) as exc:
                name = offer.get("name", f"offer_{index + 1}") if isinstance(offer, dict) else f"offer_{index + 1}"
                errors.append({"name": name, "error": str(exc)})
        ranked = sorted(
            [r for r in results if r["eligible"] and r["trip_bank_fee"] is not None],
            key=lambda r: (r["trip_bank_fee"], r["name"]),
        )
        return {"offers": results, "invalid_offers": errors, "eligible_ranking": [r["name"] for r in ranked]}
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": str(exc), "offers": [], "invalid_offers": [], "eligible_ranking": []}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc.msg}", "offers": [], "invalid_offers": [], "eligible_ranking": []}))
        sys.exit(0)
    print(json.dumps(main(payload), separators=(",", ":")))
