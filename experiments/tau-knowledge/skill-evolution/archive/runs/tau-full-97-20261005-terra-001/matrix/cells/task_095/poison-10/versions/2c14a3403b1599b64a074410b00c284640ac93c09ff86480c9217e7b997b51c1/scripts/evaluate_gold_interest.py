#!/usr/bin/env python3
"""Select Gold Account APY components and optionally compare a constant-balance period.
Reads one JSON object from stdin and writes JSON to stdout. See SKILL.md.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

CARDS = {
    "Bronze Rewards Card": Decimal("0.15"), "Silver Rewards Card": Decimal("0.20"),
    "Gold Rewards Card": Decimal("0.025"), "Platinum Rewards Card": Decimal("0.15"),
    "Diamond Elite Card": Decimal("0.30"), "EcoCard": Decimal("0.60"),
    "Green Rewards Card": Decimal("0.35"), "Crypto-Cash Back Card": Decimal("0"),
}
CHECKING = {"Green Account": Decimal("0.75"), "Purple Account": Decimal("0.10")}
RELATIONSHIP = Decimal("0.025")


def number(value, field, errors, positive=False):
    if value is None or isinstance(value, bool):
        errors.append(field + " must be a number."); return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(field + " must be a number."); return None
    if not value.is_finite() or value < 0 or (positive and value == 0):
        errors.append(field + (" must be greater than zero." if positive else " must be zero or greater.")); return None
    return value


def pct(value):
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def cash(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def pick(items, key):
    return min(items, key=lambda x: (-x[key], x["name"])) if items else None


def evaluate(data):
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."]}
    kind = str(data.get("savings_account_type", "Gold Account")).strip().lower()
    if kind not in ("gold account", "gold savings", "gold savings account"):
        return {"ok": False, "errors": ["This helper only supports a Gold Account."]}
    errors = []
    base = number(data.get("base_apy_percent"), "base_apy_percent", errors)
    checks, cards = data.get("checking_accounts"), data.get("credit_cards")
    if not isinstance(checks, list): errors.append("checking_accounts must be a list."); checks = []
    if not isinstance(cards, list): errors.append("credit_cards must be a list."); cards = []
    if errors: return {"ok": False, "errors": errors}

    valid_checks, excluded_checks = [], []
    for item in checks:
        if not isinstance(item, dict): excluded_checks.append({"reason": "invalid item"}); continue
        name = str(item.get("account_type", "")).strip()
        if name not in CHECKING: excluded_checks.append({"account_type": name or None, "reason": "not a documented Gold Account qualifying checking type"})
        elif item.get("active") is not True: excluded_checks.append({"account_type": name, "reason": "not confirmed active"})
        elif item.get("same_profile") is not True: excluded_checks.append({"account_type": name, "reason": "not confirmed under the same profile"})
        else: valid_checks.append({"name": name, "boost": CHECKING[name]})

    valid_cards, excluded_cards = [], []
    for item in cards:
        if not isinstance(item, dict): excluded_cards.append({"reason": "invalid item"}); continue
        name = str(item.get("card_type", "")).strip()
        if name not in CARDS: excluded_cards.append({"card_type": name or None, "reason": "card bonus not documented by this helper"})
        elif str(item.get("status", "")).strip().upper() != "ACTIVE": excluded_cards.append({"card_type": name, "reason": "not active"})
        elif item.get("same_profile") is not True: excluded_cards.append({"card_type": name, "reason": "not confirmed under the same profile"})
        else: valid_cards.append({"name": name, "bonus": CARDS[name]})

    chosen_check, chosen_card = pick(valid_checks, "boost"), pick(valid_cards, "bonus")
    check_bonus = chosen_check["boost"] if chosen_check else Decimal("0")
    card_bonus = chosen_card["bonus"] if chosen_card else Decimal("0")
    has_relationship = any(x["name"] == "Gold Rewards Card" for x in valid_cards)
    relationship = RELATIONSHIP if has_relationship else Decimal("0")
    expected = base + check_bonus + card_bonus + relationship
    result = {
        "base_apy_percent": pct(base),
        "checking_candidates": [{"account_type": x["name"], "boost_percent": pct(x["boost"])} for x in valid_checks],
        "checking_excluded": excluded_checks,
        "selected_checking": None if not chosen_check else {"account_type": chosen_check["name"], "boost_percent": pct(check_bonus)},
        "credit_card_candidates": [{"card_type": x["name"], "bonus_percent": pct(x["bonus"])} for x in valid_cards],
        "credit_card_excluded": excluded_cards,
        "selected_credit_card": None if not chosen_card else {"card_type": chosen_card["name"], "bonus_percent": pct(card_bonus)},
        "relationship_bonuses": ([{"relationship": "Gold Rewards Card holder relationship bonus", "bonus_percent": pct(relationship), "additive": True}] if has_relationship else []),
        "expected_apy_percent": pct(expected),
        "expected_apy_display_two_decimals": format(expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f"),
        "minimum_balance_requirement": 5000 if has_relationship else 10000,
        "assumptions": ["Only the highest qualifying checking boost is selected.", "Only the highest active same-profile card bonus is selected.", "A qualifying Gold Rewards relationship bonus is separate and additive."],
    }
    estimate_keys = [x for x in ("balance", "days", "actual_interest") if x in data]
    if estimate_keys and len(estimate_keys) != 3:
        result["interest_comparison"] = {"status": "insufficient_inputs", "message": "Provide balance, days, and actual_interest together for a stable-balance estimate."}
        return {"ok": True, "result": result}
    if not estimate_keys:
        if "actual_apy_percent" in data:
            actual = number(data["actual_apy_percent"], "actual_apy_percent", errors)
            if errors: return {"ok": False, "errors": errors}
            result["interest_comparison"] = {"status": "apy_comparison_only", "actual_apy_percent": pct(actual), "expected_apy_percent": pct(expected), "apy_difference_percent": pct(expected - actual), "message": "Rate comparison requires account, period, and daily-ledger verification before remediation."}
        return {"ok": True, "result": result}
    balance = number(data["balance"], "balance", errors, True)
    actual_interest = number(data["actual_interest"], "actual_interest", errors)
    days = data["days"]
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 366: errors.append("days must be an integer from 1 through 366.")
    if errors: return {"ok": False, "errors": errors}
    with localcontext() as context:
        context.prec = 28
        accrued = balance * ((Decimal(1) + expected / Decimal(100)) ** (Decimal(days) / Decimal(365)) - Decimal(1))
        implied = ((Decimal(1) + actual_interest / balance) ** (Decimal(365) / Decimal(days)) - Decimal(1)) * 100
    result["interest_comparison"] = {"status": "indicative_stable_balance_estimate", "balance": cash(balance), "days": days, "expected_interest": cash(accrued), "actual_interest": cash(actual_interest), "estimated_difference": cash(accrued - actual_interest), "implied_actual_apy_percent": pct(implied), "message": "This assumes a constant verified daily balance and is not sufficient alone to authorize a credit or discrepancy report."}
    return {"ok": True, "result": result}


def main():
    try: print(json.dumps(evaluate(json.load(sys.stdin)), separators=(",", ":"), allow_nan=False))
    except json.JSONDecodeError: print('{"ok":false,"errors":["stdin must contain valid JSON."]}')
    except Exception as exc: print(json.dumps({"ok": False, "errors": ["Unexpected evaluation error: " + str(exc)]}, separators=(",", ":")))

if __name__ == "__main__": main()
