#!/usr/bin/env python3
"""Compare packaged business cards for one proposed USD purchase.

Reads one JSON object from stdin and emits one JSON object to stdout. This is
informational only; it never opens or changes a card account.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "business_rewards_catalog.json"


def fail(errors):
    return {"ok": False, "errors": errors}


def decimal_value(value, field, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number, not a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return result


def iso_date(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD")


def boolean_or_unknown(payload, key, default=None):
    value = payload.get(key, default)
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{key} must be true, false, or omitted")
    return value


def money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def points_and_cash(amount, rate_percent):
    # rate% * amount gives dollars; rewards are stored as 100 points per dollar.
    raw_points = amount * rate_percent
    points = int(raw_points.to_integral_value(rounding=ROUND_FLOOR))
    return points, Decimal(points) / Decimal("100")


def underwriting(card, personal_score, paydex, established):
    results = []
    required_personal = card["personal_credit_min"]
    if personal_score is None:
        results.append({"criterion": "personal_credit_score", "required_minimum": required_personal, "status": "unknown"})
    else:
        results.append({"criterion": "personal_credit_score", "required_minimum": required_personal,
                        "provided": personal_score, "status": "passes" if personal_score >= required_personal else "does_not_pass"})
    if established is True:
        required_paydex = card["business_paydex_min_established"]
        if paydex is None:
            results.append({"criterion": "business_paydex_for_established_business", "required_minimum": required_paydex, "status": "unknown"})
        else:
            results.append({"criterion": "business_paydex_for_established_business", "required_minimum": required_paydex,
                            "provided": paydex, "status": "passes" if paydex >= required_paydex else "does_not_pass"})
    elif established is None:
        results.append({"criterion": "business_status", "status": "unknown", "note": "PAYDEX threshold applies to established businesses."})
    else:
        results.append({"criterion": "business_paydex_for_established_business", "status": "not_screened", "note": "Business marked as not established."})
    statuses = [item["status"] for item in results]
    overall = "does_not_pass" if "does_not_pass" in statuses else ("unknown" if "unknown" in statuses else "passes")
    return {"status": overall, "criteria": results}


def fee_assessment(card, open_date, new_customer, good_standing):
    standard = Decimal(card["standard_annual_fee"])
    waiver = card.get("fee_waiver")
    result = {"standard_annual_fee_dollars": money(standard), "first_year_fee_status": "standard_fee_applies", "first_year_fee_dollars": money(standard)}
    if not waiver:
        return result
    if waiver.get("requires_confirmation"):
        result["first_year_fee_status"] = "requires_offer_confirmation"
        result["first_year_fee_dollars"] = None
        result["condition"] = "Documented new-customer waiver material should be confirmed against the applicable offer terms."
        return result
    if open_date is None:
        result["first_year_fee_status"] = "promotion_date_unknown"
        result["first_year_fee_dollars"] = None
        return result
    start = date.fromisoformat(waiver["start_date"])
    end = date.fromisoformat(waiver["end_date"])
    if not start <= open_date <= end:
        result["first_year_fee_status"] = "outside_documented_promotion_window"
        return result
    conditions_unknown = (waiver.get("requires_new_customer") and new_customer is None) or (waiver.get("requires_good_standing") and good_standing is None)
    conditions_fail = (waiver.get("requires_new_customer") and new_customer is False) or (waiver.get("requires_good_standing") and good_standing is False)
    if conditions_fail:
        result["first_year_fee_status"] = "promotion_conditions_not_met"
    elif conditions_unknown:
        result["first_year_fee_status"] = "promotion_conditions_unconfirmed"
        result["first_year_fee_dollars"] = None
    else:
        result["first_year_fee_status"] = "documented_waiver_conditions_met"
        result["first_year_fee_dollars"] = money(Decimal(waiver["first_year_fee"]))
    return result


def main(payload):
    if not isinstance(payload, dict):
        return fail(["Top-level input must be a JSON object."])
    try:
        amount = decimal_value(payload.get("purchase_amount"), "purchase_amount", positive=True)
        requested_limit = decimal_value(payload.get("requested_credit_limit", amount), "requested_credit_limit", positive=True)
        category_raw = payload.get("purchase_category")
        if not isinstance(category_raw, str) or not category_raw.strip():
            raise ValueError("purchase_category must be a nonempty string")
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        category = category_raw.strip().lower()
        category = catalog.get("category_aliases", {}).get(category, category)
        all_categories = set(catalog.get("category_aliases", {}).values())
        for card in catalog["cards"]:
            all_categories.update(card["bonus_rates_percent"].keys())
        if category not in all_categories:
            raise ValueError("purchase_category is not represented by the packaged card catalog")
        coding_confirmed = boolean_or_unknown(payload, "merchant_coding_confirmed", False)
        eligible_purchase = boolean_or_unknown(payload, "eligible_purchase", True)
        if eligible_purchase is False:
            raise ValueError("The proposed transaction is marked ineligible for rewards; do not calculate card rewards")
        current = iso_date(payload.get("current_date"), "current_date")
        open_date = iso_date(payload.get("account_open_date"), "account_open_date") or current
        new_customer = boolean_or_unknown(payload, "new_customer")
        good_standing = boolean_or_unknown(payload, "account_in_good_standing")
        established = boolean_or_unknown(payload, "established_business")
        personal = payload.get("personal_credit_score")
        paydex = payload.get("business_paydex")
        if personal is not None:
            personal = decimal_value(personal, "personal_credit_score", positive=True)
        if paydex is not None:
            paydex = decimal_value(paydex, "business_paydex", positive=True)
    except (ValueError, TypeError) as exc:
        return fail([str(exc)])

    options = []
    for card in catalog["cards"]:
        bonus_rate = card["bonus_rates_percent"].get(category)
        rate = Decimal(bonus_rate if bonus_rate is not None else card["base_rate_percent"])
        points, cash = points_and_cash(amount, rate)
        documented_limit_max = Decimal(card["limit_max"])
        capacity_status = "within_documented_maximum" if requested_limit <= documented_limit_max else "exceeds_documented_maximum"
        if bonus_rate is not None:
            reward_status = "confirmed_bonus_rate" if coding_confirmed else "conditional_on_eligible_merchant_coding"
        else:
            reward_status = "base_rate_for_non_bonus_category"
        option = {
            "card": card["name"],
            "purchase_category": category,
            "rate_percent": format(rate, "f"),
            "reward_status": reward_status,
            "reward_points": points,
            "cash_back_dollars": money(cash),
            "capacity_screen": {
                "requested_credit_limit_dollars": money(requested_limit),
                "documented_limit_minimum_dollars": money(Decimal(card["limit_min"])),
                "documented_limit_maximum_dollars": money(documented_limit_max),
                "status": capacity_status,
                "note": "A documented maximum is not approved or available credit."
            },
            "underwriting_screen": underwriting(card, personal, paydex, established),
            "annual_fee": fee_assessment(card, open_date, new_customer, good_standing),
            "sources": card["sources"]
        }
        options.append(option)

    # Capacity comes first; then highest modeled cash back. Ties preserve catalog order.
    options.sort(key=lambda item: (item["capacity_screen"]["status"] != "within_documented_maximum", -item["reward_points"]))
    viable = [o for o in options if o["capacity_screen"]["status"] == "within_documented_maximum"]
    best = None
    if viable:
        candidate = viable[0]
        blockers = []
        if candidate["reward_status"] == "conditional_on_eligible_merchant_coding":
            blockers.append("eligible merchant category coding is not confirmed")
        underwriting_status = candidate["underwriting_screen"]["status"]
        if underwriting_status != "passes":
            blockers.append("underwriting criteria are " + underwriting_status)
        best = {"card": candidate["card"], "status": "conditional" if blockers else "screened_leading_option", "conditions": blockers}

    warnings = [
        "Cash back is calculated on net purchases; returns and credits reduce rewards.",
        "Cash-back rewards are represented as points worth $0.01 each; fractional points are rounded down per purchase.",
        "Merchant coding, approval, and available credit must be confirmed separately from this comparison."
    ]
    return {
        "ok": True,
        "input": {
            "purchase_amount_dollars": money(amount), "purchase_category": category,
            "merchant_coding_confirmed": coding_confirmed, "account_open_date": open_date.isoformat() if open_date else None
        },
        "options": options,
        "best_option": best,
        "warnings": warnings
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        output = main(raw)
    except json.JSONDecodeError as exc:
        output = fail([f"Invalid JSON input: {exc.msg}"])
    except Exception as exc:  # Keep the stdin/stdout contract stable for the executor.
        output = fail([f"Unexpected calculation error: {exc}"])
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
