#!/usr/bin/env python3
"""Evaluate documented card terms supplied as JSON; reads stdin and writes JSON."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def norm(value):
    return " ".join(str(value).strip().casefold().split())


def dec(value, field):
    try:
        answer = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not answer.is_finite():
        raise ValueError(f"{field} must be finite")
    return answer


def render(value):
    # JSON numbers are avoided so currency/points precision cannot be lost.
    return format(value, "f")


def parse_date(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must begin with a valid YYYY-MM-DD") from exc


def add_months(start, months):
    # Calendar-month anniversary, clamped to the last day of the target month.
    month_index = start.month - 1 + int(months)
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(start.day, month_lengths[month - 1]))


def in_window(day, offer):
    return parse_date(offer["start"], "offer.start") <= day <= parse_date(offer["end"], "offer.end")


def condition_state(offer, opening, new_customer, as_of, is_reward=False):
    """Return qualified, conditional, or unavailable and human-readable conditions."""
    conditions = []
    if opening is None:
        return "conditional", ["account-opening date is needed"]
    if offer.get("requires_open_during", False) or (not is_reward and "start" in offer):
        if not in_window(opening, offer):
            return "unavailable", ["account opening is outside the offer window"]
    if offer.get("requires_new_customer", False):
        if new_customer is not True:
            if new_customer is False:
                return "unavailable", ["offer is for new customers only"]
            conditions.append("new-customer status must be confirmed")
    if offer.get("requires_good_standing", False):
        conditions.append("account must remain in good standing")
    if is_reward:
        if not in_window(opening, offer) and offer.get("requires_open_during", False):
            return "unavailable", ["account opening is outside the offer window"]
        duration = offer.get("duration_months")
        if duration is not None:
            duration_value = int(duration)
            if duration_value < 0:
                raise ValueError("duration_months must not be negative")
            if as_of >= add_months(opening, duration_value):
                return "unavailable", ["promotion duration from account opening has ended"]
        elif not in_window(as_of, offer):
            return "unavailable", ["promotion is not active on the comparison date"]
    return ("conditional" if conditions else "qualified"), conditions


def points_for_amounts(amounts, rate_percent, multiplier=Decimal("1")):
    # rate percent cash back -> points at one point per $0.01; floor each charge.
    rate = rate_percent * multiplier / Decimal("100")
    total = 0
    for amount in amounts:
        total += int((amount * rate * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
    return total


def scenario(label, rate, amounts, multiplier=Decimal("1"), conditions=None):
    points = points_for_amounts(amounts, rate, multiplier)
    return {
        "label": label,
        "rate_percent": render(rate * multiplier),
        "points": points,
        "cash_value": render(Decimal(points) / Decimal("100")),
        "conditions": conditions or []
    }


def fee_result(product, opening, new_customer):
    standard = dec(product["annual_fee"], "annual_fee")
    results = [{"status": "standard", "first_year_fee": render(standard), "conditions": []}]
    for offer in product.get("first_year_fee_offers", []):
        state, conditions = condition_state(offer, opening, new_customer, None, False)
        if state != "unavailable":
            results.append({
                "status": state,
                "first_year_fee": render(dec(offer["fee"], "first_year_fee_offers.fee")),
                "conditions": conditions
            })
    return results


def evaluate_product(product, amounts, category, merchant, as_of, opening, new_customer, target):
    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each product needs a nonempty name")
    default_rate = dec(product["default_rate_percent"], f"{name}.default_rate_percent")
    if default_rate < 0:
        raise ValueError(f"{name}.default_rate_percent must not be negative")
    limit = product.get("credit_limit") or {}
    maximum = dec(limit.get("max"), f"{name}.credit_limit.max")
    minimum = dec(limit["min"], f"{name}.credit_limit.min") if limit.get("min") is not None else None
    if maximum < 0 or (minimum is not None and minimum < 0):
        raise ValueError(f"{name}.credit limits must not be negative")

    if target > maximum:
        limit_status = "exceeds_published_maximum"
    elif minimum is not None and target <= minimum:
        limit_status = "at_or_below_published_minimum_if_approved"
    else:
        limit_status = "within_published_range_if_approved"

    base_label = "documented default rate"
    base_rate = default_rate
    confirmed = category is not None
    override = None
    if merchant:
        for rule in product.get("merchant_rate_overrides", []):
            merchants = {norm(x) for x in rule.get("merchants", [])}
            if norm(merchant) in merchants:
                override = rule
                break
    if override is not None:
        base_rate = dec(override["rate_percent"], f"{name}.merchant override rate")
        base_label = override.get("label", "documented merchant-specific rate")
        confirmed = True
    elif category is not None:
        for rule in product.get("reward_rules", []):
            if norm(category) in {norm(x) for x in rule.get("categories", [])}:
                base_rate = dec(rule["rate_percent"], f"{name}.reward rule rate")
                base_label = rule.get("label", "documented category rate")
                break

    multipliers = [(Decimal("1"), "base rewards", [])]
    for offer in product.get("reward_promotions", []):
        state, conditions = condition_state(offer, opening, new_customer, as_of, True)
        if state != "unavailable":
            extra = list(conditions)
            if state == "conditional":
                extra.append("promotion availability is conditional")
            multipliers.append((dec(offer["multiplier"], f"{name}.promotion.multiplier"),
                                "promotional rewards", extra))

    scenarios = []
    for multiplier, kind, conditions in multipliers:
        scenarios.append(scenario(f"{base_label} ({kind})", base_rate, amounts, multiplier, conditions))

    # When category is unknown, show each distinct enhanced rate as explicitly conditional.
    if category is None and override is None:
        seen = {base_rate}
        for rule in product.get("reward_rules", []):
            rate = dec(rule["rate_percent"], f"{name}.reward rule rate")
            if rate in seen:
                continue
            seen.add(rate)
            label = rule.get("label", "documented enhanced category rate")
            for multiplier, kind, promo_conditions in multipliers:
                conditions = ["merchant category must match: " + ", ".join(map(str, rule.get("categories", [])))] + promo_conditions
                scenarios.append(scenario(f"possible {label} ({kind})", rate, amounts, multiplier, conditions))

    eligibility = product.get("eligibility", {})
    return {
        "name": name,
        "purchase_category_confirmed": confirmed,
        "credit_limit_assessment": {
            "status": limit_status,
            "published_min": render(minimum) if minimum is not None else None,
            "published_max": render(maximum),
            "note": "Published limits are subject to underwriting and the assigned approved credit line."
        },
        "eligibility": eligibility,
        "reward_scenarios": scenarios,
        "first_year_fee_options": fee_result(product, opening, new_customer)
    }


def main(payload):
    amounts = [dec(x, "purchase_amounts item") for x in payload.get("purchase_amounts", [])]
    if not amounts or any(x <= 0 for x in amounts):
        raise ValueError("purchase_amounts must be a nonempty list of positive amounts")
    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    opening = parse_date(payload.get("opening_date"), "opening_date", allow_none=True)
    new_customer = payload.get("new_customer")
    if new_customer not in (True, False, None):
        raise ValueError("new_customer must be true, false, or null")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")
    category = payload.get("purchase_category")
    merchant = payload.get("merchant_name")
    target = sum(amounts, Decimal("0"))
    output = {
        "purchase_total": render(target),
        "as_of_date": as_of.isoformat(),
        "rounding_policy": "Each purchase is converted to points and fractional points are rounded down.",
        "cash_back_point_conversion": "1 point = $0.01",
        "options": [],
        "validation_errors": []
    }
    for product in products:
        try:
            output["options"].append(evaluate_product(product, amounts, category, merchant, as_of, opening, new_customer, target))
        except (KeyError, TypeError, ValueError) as exc:
            output["validation_errors"].append({"product": product.get("name", "unknown") if isinstance(product, dict) else "unknown", "error": str(exc)})
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        sys.exit(2)
