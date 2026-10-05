#!/usr/bin/env python3
"""Calculate documented business-card reward scenarios for one USD purchase.

Reads one JSON object from stdin and writes one JSON object to stdout. It is
informational only and cannot apply for, open, or alter a card account.
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


def parse_date(value, field):
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


def reward(amount, rate_percent):
    # A rate expressed as a percentage produces this many points per dollar.
    points = int((amount * rate_percent).to_integral_value(rounding=ROUND_FLOOR))
    return points, Decimal(points) / Decimal("100")


def underwriting(card, personal_score, paydex, established):
    criteria = []
    personal_min = card["personal_credit_min"]
    if personal_score is None:
        criteria.append({"criterion": "personal_credit_score", "required_minimum": personal_min, "status": "unknown"})
    else:
        criteria.append({"criterion": "personal_credit_score", "required_minimum": personal_min, "provided": str(personal_score), "status": "passes" if personal_score >= personal_min else "does_not_pass"})
    if established is True:
        paydex_min = card["business_paydex_min_established"]
        if paydex is None:
            criteria.append({"criterion": "business_paydex_for_established_business", "required_minimum": paydex_min, "status": "unknown"})
        else:
            criteria.append({"criterion": "business_paydex_for_established_business", "required_minimum": paydex_min, "provided": str(paydex), "status": "passes" if paydex >= paydex_min else "does_not_pass"})
    elif established is None:
        criteria.append({"criterion": "business_status", "status": "unknown", "note": "The PAYDEX threshold applies to established businesses."})
    else:
        criteria.append({"criterion": "business_paydex_for_established_business", "status": "not_screened", "note": "Business is marked not established."})
    statuses = [entry["status"] for entry in criteria]
    status = "does_not_pass" if "does_not_pass" in statuses else ("unknown" if "unknown" in statuses else "passes")
    return {"status": status, "criteria": criteria}


def fee_assessment(card, account_open_date, new_customer, good_standing):
    standard = Decimal(card["standard_annual_fee"])
    result = {"standard_annual_fee_dollars": money(standard), "first_year_fee_status": "standard_fee_applies", "first_year_fee_dollars": money(standard)}
    waiver = card.get("fee_waiver")
    if not waiver:
        return result
    if waiver.get("requires_confirmation"):
        result.update({"first_year_fee_status": "requires_offer_confirmation", "first_year_fee_dollars": None, "condition": "Confirm the applicable new-customer waiver terms before treating the first-year fee as waived."})
        return result
    if account_open_date is None:
        result.update({"first_year_fee_status": "account_open_date_unknown", "first_year_fee_dollars": None})
        return result
    start, end = date.fromisoformat(waiver["start_date"]), date.fromisoformat(waiver["end_date"])
    if not start <= account_open_date <= end:
        result["first_year_fee_status"] = "outside_documented_promotion_window"
        return result
    failed = (waiver.get("requires_new_customer") and new_customer is False) or (waiver.get("requires_good_standing") and good_standing is False)
    unknown = (waiver.get("requires_new_customer") and new_customer is None) or (waiver.get("requires_good_standing") and good_standing is None)
    if failed:
        result["first_year_fee_status"] = "promotion_conditions_not_met"
    elif unknown:
        result.update({"first_year_fee_status": "promotion_conditions_unconfirmed", "first_year_fee_dollars": None})
    else:
        result.update({"first_year_fee_status": "documented_waiver_conditions_met", "first_year_fee_dollars": money(Decimal(waiver["first_year_fee"]))})
    return result


def promotion_scenario(card, amount, normal_rate, current_date, account_open_date, purchase_date, new_customer):
    promo = card.get("reward_promotion")
    if not promo:
        return None
    start, end = date.fromisoformat(promo["start_date"]), date.fromisoformat(promo["end_date"])
    rate = normal_rate * Decimal(promo["multiplier"])
    points, cash = reward(amount, rate)
    conditions = []
    if current_date is None:
        conditions.append("current date was not supplied to assess the dated offer")
    elif not start <= current_date <= end:
        conditions.append("current date is outside the documented promotion window")
    if account_open_date is None:
        conditions.append("account opening date is unconfirmed")
    elif not start <= account_open_date <= end:
        conditions.append("account must be opened during the documented promotion window")
    if promo.get("requires_new_customer") and new_customer is None:
        conditions.append("new-customer status is unconfirmed")
    elif promo.get("requires_new_customer") and new_customer is False:
        conditions.append("offer is limited to new customers")
    if purchase_date is None:
        conditions.append("purchase timing within the first six months after opening is unconfirmed")
    elif account_open_date is not None:
        # Six calendar months is described in the terms; without a calendar-month
        # dependency, this conservative 184-day screen only identifies clear late dates.
        if (purchase_date - account_open_date).days < 0 or (purchase_date - account_open_date).days > 184:
            conditions.append("purchase date is not within the documented first-six-month period")
    status = "documented_conditions_screened" if not conditions else "conditional"
    return {
        "description": f"{promo['multiplier']}x cash back on {promo['applies_to']} for {promo['duration_months_after_opening']} months after opening",
        "promotion_start_date": promo["start_date"],
        "promotion_end_date": promo["end_date"],
        "modeled_rate_percent": format(rate, "f"),
        "modeled_reward_points": points,
        "modeled_cash_back_dollars": money(cash),
        "status": status,
        "conditions": conditions
    }


def main(payload):
    if not isinstance(payload, dict):
        return fail(["Top-level input must be a JSON object."])
    try:
        amount = decimal_value(payload.get("purchase_amount"), "purchase_amount", positive=True)
        requested_limit = decimal_value(payload.get("requested_credit_limit", amount), "requested_credit_limit", positive=True)
        raw_category = payload.get("purchase_category")
        if not isinstance(raw_category, str) or not raw_category.strip():
            raise ValueError("purchase_category must be a nonempty string")
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        category = catalog.get("category_aliases", {}).get(raw_category.strip().lower(), raw_category.strip().lower())
        recognized = set(catalog.get("category_aliases", {}).values())
        for card in catalog["cards"]:
            recognized.update(card["bonus_rates_percent"].keys())
        if category not in recognized:
            raise ValueError("purchase_category is not represented by the packaged card catalog")
        coding_confirmed = boolean_or_unknown(payload, "merchant_coding_confirmed", False)
        if boolean_or_unknown(payload, "eligible_purchase", True) is False:
            raise ValueError("The proposed transaction is marked ineligible for rewards; do not calculate card rewards")
        current_date = parse_date(payload.get("current_date"), "current_date")
        account_open_date = parse_date(payload.get("account_open_date"), "account_open_date")
        purchase_date = parse_date(payload.get("purchase_date"), "purchase_date")
        new_customer = boolean_or_unknown(payload, "new_customer")
        good_standing = boolean_or_unknown(payload, "account_in_good_standing")
        established = boolean_or_unknown(payload, "established_business")
        personal = None if payload.get("personal_credit_score") is None else decimal_value(payload["personal_credit_score"], "personal_credit_score", positive=True)
        paydex = None if payload.get("business_paydex") is None else decimal_value(payload["business_paydex"], "business_paydex", positive=True)
    except (ValueError, TypeError) as exc:
        return fail([str(exc)])

    options = []
    for card in catalog["cards"]:
        bonus = card["bonus_rates_percent"].get(category)
        rate = Decimal(bonus if bonus is not None else card["base_rate_percent"])
        points, cash = reward(amount, rate)
        limit_max = Decimal(card["limit_max"])
        capacity = "within_documented_maximum" if requested_limit <= limit_max else "exceeds_documented_maximum"
        reward_status = "base_rate_for_non_bonus_category" if bonus is None else ("confirmed_bonus_rate" if coding_confirmed else "conditional_on_eligible_merchant_coding")
        option = {
            "card": card["name"], "purchase_category": category,
            "rate_percent": format(rate, "f"), "reward_status": reward_status,
            "reward_points": points, "cash_back_dollars": money(cash),
            "capacity_screen": {"requested_credit_limit_dollars": money(requested_limit), "documented_limit_minimum_dollars": money(Decimal(card["limit_min"])), "documented_limit_maximum_dollars": money(limit_max), "status": capacity, "note": "A documented maximum is not approved or available credit."},
            "underwriting_screen": underwriting(card, personal, paydex, established),
            "annual_fee": fee_assessment(card, account_open_date, new_customer, good_standing),
            "promotion_scenario": promotion_scenario(card, amount, rate, current_date, account_open_date, purchase_date, new_customer),
            "sources": card["sources"]
        }
        options.append(option)

    # Rank definite normal rewards, after documented capacity. Promotional scenarios
    # remain separately conditional and therefore do not replace the normal ranking.
    options.sort(key=lambda item: (item["capacity_screen"]["status"] != "within_documented_maximum", -item["reward_points"]))
    viable = [item for item in options if item["capacity_screen"]["status"] == "within_documented_maximum"]
    best = None
    if viable:
        candidate = viable[0]
        conditions = []
        if candidate["reward_status"] == "conditional_on_eligible_merchant_coding":
            conditions.append("eligible merchant category coding is unconfirmed")
        if candidate["underwriting_screen"]["status"] != "passes":
            conditions.append("underwriting criteria are " + candidate["underwriting_screen"]["status"])
        best = {"card": candidate["card"], "status": "conditional" if conditions else "screened_leading_normal_option", "conditions": conditions}

    return {"ok": True, "input": {"purchase_amount_dollars": money(amount), "purchase_category": category, "merchant_coding_confirmed": coding_confirmed, "current_date": current_date.isoformat() if current_date else None, "account_open_date": account_open_date.isoformat() if account_open_date else None}, "options": options, "best_option": best, "warnings": ["Cash back is calculated on net purchases; returns and credits reduce rewards.", "Cash-back rewards are represented as points worth $0.01 each; fractional points are rounded down per purchase.", "Merchant coding, promotion eligibility, approval, and available credit must be confirmed separately from this comparison."]}


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = fail([f"Invalid JSON input: {exc.msg}"])
    except Exception as exc:
        output = fail([f"Unexpected calculation error: {exc}"])
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
