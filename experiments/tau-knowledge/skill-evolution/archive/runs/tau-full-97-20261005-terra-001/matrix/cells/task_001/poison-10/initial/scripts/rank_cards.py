#!/usr/bin/env python3
"""Rank current, structured cash-back-card offers.

Reads one JSON object from stdin and writes one JSON object to stdout.  The
program is deliberately catalog-free: callers must provide product terms from
the current task, rather than relying on embedded card names or rates.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple


def error_result(messages: List[str]) -> Dict[str, Any]:
    return {"ok": False, "recommendations": [], "excluded": [], "errors": messages}


def as_decimal(value: Any, field: str, errors: List[str], minimum: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be a number, not a boolean")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number or null")
        return None
    if not number.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if minimum is not None and number < minimum:
        errors.append(f"{field} must be at least {minimum}")
        return None
    return number


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def requirement_status(
    requires: Dict[str, Any], confirmed: Dict[str, Any], offer_name: str, errors: List[str]
) -> Tuple[List[str], List[str]]:
    """Return (failed requirements, unresolved requirements)."""
    failed: List[str] = []
    unresolved: List[str] = []
    for key, required in requires.items():
        if not isinstance(key, str) or not key:
            errors.append(f"{offer_name}.requires keys must be nonempty strings")
            continue
        if not isinstance(required, bool):
            errors.append(f"{offer_name}.requires.{key} must be boolean")
            continue
        if not required:
            continue
        status = confirmed.get(key)
        if status is False:
            failed.append(key)
        elif status is not True:
            unresolved.append(key)
    return failed, unresolved


def main(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return error_result(["input must be a JSON object"])

    preferences = payload.get("preferences")
    offers = payload.get("offers")
    errors: List[str] = []
    if not isinstance(preferences, dict):
        errors.append("preferences must be an object")
    if not isinstance(offers, list) or not offers:
        errors.append("offers must be a nonempty array")
    if errors:
        return error_result(errors)

    personal_only = preferences.get("personal_only", True)
    simple_flat_rate = preferences.get("simple_flat_rate", False)
    if not isinstance(personal_only, bool):
        errors.append("preferences.personal_only must be boolean")
    if not isinstance(simple_flat_rate, bool):
        errors.append("preferences.simple_flat_rate must be boolean")

    max_fee = as_decimal(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors, Decimal("0"))
    monthly_spend = as_decimal(
        preferences.get("monthly_eligible_spend"),
        "preferences.monthly_eligible_spend",
        errors,
        Decimal("0"),
    )
    credit_score = as_decimal(preferences.get("credit_score"), "preferences.credit_score", errors, Decimal("0"))
    confirmed = preferences.get("confirmed_requirements", {})
    if not isinstance(confirmed, dict) or any(not isinstance(v, bool) for v in confirmed.values()):
        errors.append("preferences.confirmed_requirements must map strings to booleans")
        confirmed = {}
    if errors:
        return error_result(errors)

    candidates: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for index, offer in enumerate(offers):
        item_errors: List[str] = []
        label = f"offers[{index}]"
        if not isinstance(offer, dict):
            errors.append(f"{label} must be an object")
            continue
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a nonempty string")
            continue
        name = name.strip()
        personal = offer.get("personal", True)
        flat_rate = offer.get("flat_rate", False)
        if not isinstance(personal, bool):
            item_errors.append(f"{name}.personal must be boolean")
        if not isinstance(flat_rate, bool):
            item_errors.append(f"{name}.flat_rate must be boolean")
        rate = as_decimal(offer.get("cash_back_rate_percent"), f"{name}.cash_back_rate_percent", item_errors, Decimal("0"))
        fee = as_decimal(offer.get("annual_fee"), f"{name}.annual_fee", item_errors, Decimal("0"))
        minimum_score = as_decimal(offer.get("min_credit_score"), f"{name}.min_credit_score", item_errors, Decimal("0"))
        requires = offer.get("requires", {})
        if not isinstance(requires, dict):
            item_errors.append(f"{name}.requires must be an object")
            requires = {}
        if item_errors:
            errors.extend(item_errors)
            continue

        rejection_reasons: List[str] = []
        if personal_only and not personal:
            rejection_reasons.append("not a personal card")
        if max_fee is not None and fee is not None and fee > max_fee:
            rejection_reasons.append("annual fee exceeds the customer limit")

        failed_requirements, unresolved = requirement_status(requires, confirmed, name, errors)
        rejection_reasons.extend([f"required condition not met: {key}" for key in failed_requirements])
        if minimum_score is not None:
            if credit_score is None:
                unresolved.append("minimum credit score")
            elif credit_score < minimum_score:
                rejection_reasons.append("credit score is below the stated minimum")

        if rejection_reasons:
            excluded.append({"name": name, "reasons": rejection_reasons})
            continue

        annual_net: Optional[Decimal] = None
        if monthly_spend is not None and rate is not None and fee is not None:
            annual_net = monthly_spend * Decimal("12") * rate / Decimal("100") - fee

        candidates.append(
            {
                "name": name,
                "cash_back_rate_percent": float(rate),
                "annual_fee": money(fee),
                "flat_rate": flat_rate,
                "unresolved_conditions": sorted(set(unresolved)),
                "estimated_annual_net_rewards": money(annual_net) if annual_net is not None else None,
                "_sort_net": annual_net if annual_net is not None else rate,
            }
        )

    if errors:
        return error_result(errors)

    # Confirmed eligibility ranks before conditional eligibility. Within each
    # group, honor a requested flat rate, then maximize known net value/rate.
    candidates.sort(
        key=lambda card: (
            1 if card["unresolved_conditions"] else 0,
            0 if (not simple_flat_rate or card["flat_rate"]) else 1,
            -card["_sort_net"],
            card["annual_fee"],
            card["name"].casefold(),
        )
    )
    for card in candidates:
        del card["_sort_net"]

    return {
        "ok": True,
        "recommendations": candidates,
        "excluded": excluded,
        "errors": [],
        "interpretation": (
            "Rank order is decision support only. Unresolved conditions and underwriting "
            "requirements must be stated to the customer."
        ),
    }


def run() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(error_result([f"invalid JSON input: {exc.msg}"])) )
        return
    except Exception as exc:  # stdin failures should still have machine-readable output
        print(json.dumps(error_result([f"unable to read input: {exc}"])) )
        return
    print(json.dumps(main(payload), sort_keys=True))


if __name__ == "__main__":
    run()
