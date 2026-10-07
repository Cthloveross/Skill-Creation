#!/usr/bin/env python3
"""Evaluate documented APY candidates supplied as JSON on stdin.

The program is intentionally advisory: it performs no banking operations and
never reads customer accounts. Rates are percentage points (e.g. 5.5 for 5.5%).
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value, field, candidate_id):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"candidate '{candidate_id}' has invalid {field}")
    if number < 0:
        raise ValueError(f"candidate '{candidate_id}' has negative {field}")
    return number


def fmt(value):
    rendered = format(value.normalize(), "f")
    return "0" if rendered in ("", "-0") else rendered


def rate_list(value, field, candidate_id):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"candidate '{candidate_id}' field {field} must be a list")
    return [decimal_value(item, field, candidate_id) for item in value]


def evaluate(candidate, balance, requirements):
    candidate_id = str(candidate.get("id", ""))
    if not candidate_id:
        raise ValueError("each candidate requires a nonempty id")
    reasons = []
    eligible_flag = candidate.get("eligible")
    if eligible_flag is not True:
        reasons.append("product eligibility is unconfirmed or unmet")

    minimum_balance = decimal_value(candidate.get("minimum_balance", 0), "minimum_balance", candidate_id)
    opening_minimum = decimal_value(candidate.get("opening_deposit_minimum", 0), "opening_deposit_minimum", candidate_id)
    if balance < minimum_balance:
        reasons.append("balance is below the ongoing minimum")
    if balance < opening_minimum:
        reasons.append("balance is below the opening minimum")

    required_days = requirements.get("min_early_direct_deposit_days")
    if required_days is not None:
        required_days = decimal_value(required_days, "min_early_direct_deposit_days", "requirements")
        provided_days = decimal_value(candidate.get("early_direct_deposit_days", 0), "early_direct_deposit_days", candidate_id)
        if provided_days < required_days:
            reasons.append("early direct deposit does not meet the requested lead time")

    if requirements.get("travel_insurance_required") is True and candidate.get("travel_insurance_documented") is not True:
        reasons.append("required travel insurance is not documented for this candidate")

    if reasons:
        return None, {"id": candidate_id, "reasons": reasons}

    base = decimal_value(candidate.get("base_apy"), "base_apy", candidate_id)
    checking = max(rate_list(candidate.get("checking_boost_rates", []), "checking_boost_rates", candidate_id), default=Decimal("0"))
    card = max(rate_list(candidate.get("card_bonus_rates", []), "card_bonus_rates", candidate_id), default=Decimal("0"))
    other = sum(rate_list(candidate.get("other_confirmed_bonus_rates", []), "other_confirmed_bonus_rates", candidate_id), Decimal("0"))
    total = base + checking + card + other
    result = {
        "id": candidate_id,
        "base_apy_percent": fmt(base),
        "selected_checking_boost_percent": fmt(checking),
        "selected_card_bonus_percent": fmt(card),
        "other_confirmed_bonus_percent": fmt(other),
        "total_apy_percent": fmt(total),
        "formula": f"{fmt(base)} + {fmt(checking)} + {fmt(card)} + {fmt(other)} = {fmt(total)}%",
        "notes": candidate.get("notes", []),
    }
    return result, None


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        balance = decimal_value(payload.get("balance"), "balance", "input")
        requirements = payload.get("requirements", {})
        candidates = payload.get("candidates")
        if not isinstance(requirements, dict) or not isinstance(candidates, list):
            raise ValueError("requirements must be an object and candidates must be a list")

        eligible, excluded = [], []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("each candidate must be an object")
            result, exclusion = evaluate(candidate, balance, requirements)
            if result is None:
                excluded.append(exclusion)
            else:
                eligible.append(result)
        eligible.sort(key=lambda item: (Decimal(item["total_apy_percent"]), item["id"]), reverse=True)
        print(json.dumps({
            "ranked_eligible": eligible,
            "excluded": excluded,
            "best": eligible[0] if eligible else None,
        }, separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
        sys.exit(2)


if __name__ == "__main__":
    main()
