#!/usr/bin/env python3
"""Rank runtime-supplied checking/savings products for an advisory conversation.

Input: JSON object documented in SKILL.md.
Output: JSON object with status, missing_inputs, rankings, and notes.
This program is deliberately read-only: it neither calls banking tools nor opens accounts.
"""
import json
import sys
from typing import Any, Dict, List, Optional


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def known_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"yes", "true"})


def missing_for(needs: Dict[str, Any], products: List[Dict[str, Any]]) -> List[str]:
    types = {str(p.get("type", "")).lower() for p in products}
    missing: List[str] = []
    if "checking" in types:
        if needs.get("expected_checking_balance") is None:
            missing.append("expected_checking_balance")
        if known_true(needs.get("uses_foreign_atms")) and needs.get("foreign_atm_withdrawals_per_travel_month") is None:
            missing.append("foreign_atm_withdrawals_per_travel_month")
    if "savings" in types:
        if needs.get("savings_balance") is None:
            missing.append("savings_balance")
        if not needs.get("savings_priority"):
            missing.append("savings_priority (maximize_yield or easy_access)")
        if needs.get("savings_withdrawals_per_month") is None:
            missing.append("savings_withdrawals_per_month")
    return missing


def checking_score(p: Dict[str, Any], needs: Dict[str, Any], notes: List[str]) -> float:
    score = 0.0
    if known_true(needs.get("travel_internationally")):
        ftx = number(p.get("foreign_transaction_fee_percent"))
        fatm = number(p.get("foreign_atm_fee"))
        score += 25 if ftx == 0 else (-10 if ftx is not None else 0)
        score += 20 if fatm == 0 else (-8 if fatm is not None else 0)
        if known_true(needs.get("uses_foreign_atms")):
            cap = number(p.get("atm_rebate_cap_monthly"))
            score += min(20, cap / 2) if cap is not None else 0
    if known_true(needs.get("wants_multi_currency_wallet")):
        currencies = number(p.get("wallet_currencies"))
        score += min(15, currencies / 2) if currencies else 0
    balance = number(needs.get("expected_checking_balance"))
    fee = number(p.get("monthly_fee"))
    waiver = number(p.get("monthly_fee_waiver_balance"))
    if fee and fee > 0:
        if balance is not None and waiver is not None:
            score += 8 if balance >= waiver else -min(25, fee)
        elif waiver is None:
            notes.append(f"{p.get('name', 'Unnamed checking product')}: monthly fee has no waiver condition in the runtime catalog.")
    return round(score, 3)


def savings_score(p: Dict[str, Any], needs: Dict[str, Any], notes: List[str]) -> float:
    score = 0.0
    balance = number(needs.get("savings_balance"))
    minimum = number(p.get("minimum_balance"))
    apy = number(p.get("apy_percent"))
    priority = str(needs.get("savings_priority", "")).lower()
    withdrawals = number(needs.get("savings_withdrawals_per_month"))
    if balance is not None and minimum is not None:
        score += 15 if balance >= minimum else -25
    if priority == "maximize_yield" and apy is not None:
        score += apy * 10
    if priority == "easy_access":
        free = number(p.get("withdrawals_free_per_month"))
        if withdrawals is not None and free is not None:
            score += 15 if withdrawals <= free else -10
    if withdrawals is not None:
        free = number(p.get("withdrawals_free_per_month"))
        excess = number(p.get("excess_withdrawal_fee"))
        if free is not None and withdrawals > free and excess is not None:
            score -= (withdrawals - free) * excess
    return round(score, 3)


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"Invalid JSON: {exc.msg}"}))
        return
    if not isinstance(raw, dict) or not isinstance(raw.get("products"), list):
        print(json.dumps({"status": "error", "error": "Expected an object containing a products array."}))
        return

    needs = raw.get("customer_needs") if isinstance(raw.get("customer_needs"), dict) else {}
    products = [p for p in raw["products"] if isinstance(p, dict) and p.get("name")]
    notes: List[str] = []
    if len(products) != len(raw["products"]):
        notes.append("Products without an object name were ignored.")
    missing = missing_for(needs, products)
    rankings: Dict[str, List[Dict[str, Any]]] = {"checking": [], "savings": []}

    for p in products:
        kind = str(p.get("type", "")).lower()
        if kind == "checking":
            rankings["checking"].append({"name": p["name"], "score": checking_score(p, needs, notes)})
        elif kind == "savings":
            rankings["savings"].append({"name": p["name"], "score": savings_score(p, needs, notes)})
        else:
            notes.append(f"{p['name']}: unsupported or missing type; expected checking or savings.")
    for entries in rankings.values():
        entries.sort(key=lambda item: (-item["score"], item["name"]))

    selection = raw.get("boost_selection")
    if selection and selection != "highest_only":
        notes.append("Boost selection is not 'highest_only'; verify the governing relationship-benefit policy before quoting a combined APY.")
    if raw.get("existing_checking_names") and any(p.get("linked_boosts") for p in products):
        notes.append("Linked boosts are not included in numeric scores unless eligibility and the governing boost-selection policy are confirmed.")

    result = {
        "status": "needs_clarification" if missing else "ready_for_advisory_review",
        "missing_inputs": missing,
        "rankings": rankings,
        "notes": notes,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
