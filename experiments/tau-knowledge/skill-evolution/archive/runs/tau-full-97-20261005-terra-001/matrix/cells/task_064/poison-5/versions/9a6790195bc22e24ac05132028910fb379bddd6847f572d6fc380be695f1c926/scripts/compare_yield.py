#!/usr/bin/env python3
"""Compare deposit-yield options. Reads one JSON object from stdin and writes one JSON object."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
VALID_STATES = {"met", "unknown", "failed"}


def decimal_value(value, field, index=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        where = f" in option {index}" if index is not None else ""
        raise ValueError(f"{field}{where} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def main(payload):
    deposit = decimal_value(payload.get("deposit"), "deposit")
    years = decimal_value(payload.get("term_years", 1), "term_years")
    if deposit < 0 or years <= 0:
        raise ValueError("deposit must be nonnegative and term_years must be positive")
    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a nonempty array")

    results = []
    for i, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"option {i} must be an object")
        account = option.get("savings_account")
        if not isinstance(account, str) or not account.strip():
            raise ValueError(f"option {i} requires savings_account")
        base = decimal_value(option.get("base_apy"), "base_apy", i)
        card_bonus = decimal_value(option.get("card_apy_bonus", 0), "card_apy_bonus", i)
        other_bonus = decimal_value(option.get("other_apy_bonus", 0), "other_apy_bonus", i)
        opening_min = decimal_value(option.get("opening_minimum", 0), "opening_minimum", i)
        ongoing_min = decimal_value(option.get("ongoing_minimum", 0), "ongoing_minimum", i)
        card_fee = decimal_value(option.get("annual_card_fee", 0), "annual_card_fee", i)
        maintenance_fee = decimal_value(option.get("maintenance_fee_annual", 0), "maintenance_fee_annual", i)
        values = (base, card_bonus, other_bonus, opening_min, ongoing_min, card_fee, maintenance_fee)
        if any(v < 0 for v in values):
            raise ValueError(f"option {i} contains a negative value")

        eligibility = option.get("eligibility", {})
        if not isinstance(eligibility, dict):
            raise ValueError(f"eligibility in option {i} must be an object")
        unknown = []
        failed = []
        for requirement, state in eligibility.items():
            if state not in VALID_STATES:
                raise ValueError(f"eligibility state for {requirement!r} in option {i} is invalid")
            if state == "unknown":
                unknown.append(requirement)
            elif state == "failed":
                failed.append(requirement)
        if deposit < opening_min:
            failed.append("opening minimum")
        if deposit < ongoing_min:
            failed.append("ongoing minimum")
        status = "ineligible" if failed else ("conditional" if unknown else "eligible")
        effective_apy = base + card_bonus + other_bonus
        estimated_interest = money(deposit * (effective_apy / HUNDRED) * years)
        total_fees = money((card_fee + maintenance_fee) * years)
        net = money(estimated_interest - total_fees)
        results.append({
            "savings_account": account,
            "card": option.get("card"),
            "status": status,
            "effective_apy": float(effective_apy),
            "estimated_interest": float(estimated_interest),
            "annual_card_fee": float(money(card_fee)),
            "annual_maintenance_fee_assumed": float(money(maintenance_fee)),
            "total_estimated_fees": float(total_fees),
            "net_estimated_value": float(net),
            "unresolved_requirements": sorted(unknown),
            "failed_requirements": sorted(set(failed)),
            "notes": option.get("notes", [])
        })

    rank = {"eligible": 0, "conditional": 1, "ineligible": 2}
    results.sort(key=lambda r: (rank[r["status"]], -r["net_estimated_value"], r["savings_account"], str(r["card"])))
    return {
        "deposit": float(money(deposit)),
        "term_years": float(years),
        "calculation_assumption": "Constant deposit balance; APY-based simple one-year estimate; stated annual fees deducted.",
        "ranked_options": results,
        "best_eligible_option": next((r for r in results if r["status"] == "eligible"), None),
        "best_conditional_option": next((r for r in results if r["status"] == "conditional"), None)
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
