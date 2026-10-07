#!/usr/bin/env python3
"""Rank documented checking-account offers for travel use.

Reads JSON from stdin and writes JSON to stdout. This performs only deterministic
comparison; it does not retrieve terms, contact customers, or take banking actions.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Tuple


def number(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def fee_score(fee: Any) -> Tuple[float, bool]:
    """Return a conservative ordinal score and whether the fee is fully known.

    Flat fees are directly comparable. Percentage/minimum/maximum schedules receive
    a positive ordinal score because they may generate a fee. Unknown schedules sort
    last and are marked incomplete rather than being assumed free.
    """
    if not isinstance(fee, dict):
        return (1000000.0, False)
    kind = fee.get("kind")
    if kind == "flat":
        return (number(fee.get("amount"), 1000000.0), True)
    if kind == "allowance_then_flat":
        return (number(fee.get("amount"), 100000.0), True)
    if kind in {"percent", "percent_min", "percent_max"}:
        minimum = number(fee.get("minimum"), 0.0)
        percent = number(fee.get("percent"), 0.0)
        return (1000.0 + minimum + percent, True)
    return (1000000.0, False)


def eligibility(offer: Dict[str, Any], customer: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    opening = number(offer.get("opening_deposit_required"))
    balance = number(offer.get("minimum_balance_required"))
    if opening > 0 and customer.get("can_meet_opening_deposit") is False:
        reasons.append("customer cannot meet required opening deposit")
    if balance > 0 and customer.get("can_meet_minimum_balance") is False:
        reasons.append("customer cannot meet required minimum balance")
    if customer.get("needs_early_direct_deposit") is True:
        days = offer.get("early_direct_deposit_days")
        if not isinstance(days, (int, float)) or isinstance(days, bool) or days <= 0:
            reasons.append("does not document early direct deposit")
    return (not reasons, reasons)


def summarize(offer: Dict[str, Any], eligible: bool, reasons: List[str]) -> Dict[str, Any]:
    foreign_score, foreign_known = fee_score(offer.get("foreign_atm_bank_fee"))
    network_score, network_known = fee_score(offer.get("out_of_network_atm_fee"))
    result = {
        "name": offer.get("name", "Unnamed offer"),
        "eligible_for_stated_needs": eligible,
        "ineligibility_reasons": reasons,
        "foreign_atm_bank_fee": offer.get("foreign_atm_bank_fee", {"kind": "unknown"}),
        "out_of_network_atm_fee": offer.get("out_of_network_atm_fee", {"kind": "unknown"}),
        "early_direct_deposit_days": offer.get("early_direct_deposit_days"),
        "opening_deposit_required": offer.get("opening_deposit_required", 0),
        "minimum_balance_required": offer.get("minimum_balance_required", 0),
        "monthly_maintenance_fee": offer.get("monthly_maintenance_fee", 0),
        "atm_rebate_cap_monthly": offer.get("atm_rebate_cap_monthly", 0),
        "notes": offer.get("notes", []),
        "comparison_score": [foreign_score, network_score],
        "fee_terms_complete": foreign_known and network_known,
    }
    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        print(json.dumps({"error": "offers_must_be_a_list"}))
        return

    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    compared: List[Dict[str, Any]] = []
    for raw in payload["offers"]:
        if not isinstance(raw, dict):
            continue
        ok, reasons = eligibility(raw, customer)
        compared.append(summarize(raw, ok, reasons))

    eligible = [item for item in compared if item["eligible_for_stated_needs"]]
    eligible.sort(key=lambda item: tuple(item["comparison_score"]) + (item["name"],))
    ineligible = [item for item in compared if not item["eligible_for_stated_needs"]]
    recommendation = eligible[0]["name"] if eligible else None
    cautions = [
        "Comparison excludes third-party ATM operator charges unless supplied in notes.",
        "A zero foreign-ATM bank fee does not by itself establish that a separate out-of-network fee is zero.",
        "Explain foreign-exchange conversion terms and rebate conditions from the source documentation.",
    ]
    print(json.dumps({
        "recommended_offer": recommendation,
        "eligible_ranked_offers": eligible,
        "ineligible_offers": ineligible,
        "cautions": cautions,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
