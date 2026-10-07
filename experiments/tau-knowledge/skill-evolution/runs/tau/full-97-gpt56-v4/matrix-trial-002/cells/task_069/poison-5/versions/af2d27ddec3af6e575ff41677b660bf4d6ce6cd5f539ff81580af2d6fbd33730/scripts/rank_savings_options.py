#!/usr/bin/env python3
"""Rank supplied savings-product facts without performing banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from typing import Any, Dict, List, Tuple


def number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if value < 0:
        raise ValueError(f"{field} must not be negative")
    return float(value)


def applicable_apy(product: Dict[str, Any], balance: float) -> Tuple[float, float]:
    """Return (APY, selected_tier_minimum) for balance using product facts."""
    tiers = product.get("tiers")
    if tiers is None:
        return number(product["apy"], "apy"), 0.0
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a nonempty list when provided")
    parsed = []
    for tier in tiers:
        if not isinstance(tier, dict):
            raise ValueError("each tier must be an object")
        minimum = number(tier["minimum_balance"], "tiers.minimum_balance")
        apy = number(tier["apy"], "tiers.apy")
        parsed.append((minimum, apy))
    qualifying = [tier for tier in parsed if tier[0] <= balance]
    if not qualifying:
        raise ValueError("no APY tier applies at the supplied balance")
    return max(qualifying, key=lambda item: item[0])[1], max(qualifying, key=lambda item: item[0])[0]


def rank(payload: Dict[str, Any]) -> Dict[str, Any]:
    balance = number(payload["balance"], "balance")
    opening = number(payload["opening_deposit"], "opening_deposit")
    require_rebate = payload.get("require_atm_rebate", False)
    if not isinstance(require_rebate, bool):
        raise ValueError("require_atm_rebate must be boolean")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")

    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"]:
            raise ValueError("each product needs a nonempty name")
        open_min = number(product["opening_minimum"], "opening_minimum")
        ongoing_min = number(product["ongoing_minimum"], "ongoing_minimum")
        rebate = number(product.get("atm_rebate_cap", 0), "atm_rebate_cap")
        reasons = []
        if opening < open_min:
            reasons.append("opening_deposit_below_minimum")
        if balance < ongoing_min:
            reasons.append("ongoing_balance_below_minimum")
        if require_rebate and rebate <= 0:
            reasons.append("no_documented_atm_rebate")
        apy, tier_minimum = applicable_apy(product, balance)
        record = {
            "name": product["name"],
            "applicable_apy": apy,
            "selected_tier_minimum": tier_minimum,
            "opening_minimum": open_min,
            "ongoing_minimum": ongoing_min,
            "atm_rebate_cap": rebate,
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            eligible.append(record)

    eligible.sort(key=lambda item: (item["applicable_apy"], item["atm_rebate_cap"], item["name"]), reverse=True)
    recommendation = eligible[0] if eligible else None
    return {"eligible": eligible, "excluded": excluded, "recommendation": recommendation}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(rank(payload), separators=(",", ":"), sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":"), sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
