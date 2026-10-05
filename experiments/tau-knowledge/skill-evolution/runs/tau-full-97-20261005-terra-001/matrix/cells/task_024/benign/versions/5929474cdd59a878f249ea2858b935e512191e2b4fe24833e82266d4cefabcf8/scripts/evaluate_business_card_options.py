#!/usr/bin/env python3
"""Evaluate supplied business-card terms. Reads one JSON object from stdin, writes JSON."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def normalize(value):
    return " ".join(str(value).strip().casefold().split())


def decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def text_number(value):
    return format(value, "f")


def parse_date(value, field, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must begin with valid YYYY-MM-DD") from exc


def in_window(day, offer, prefix="offer"):
    return (parse_date(offer["start"], prefix + ".start") <= day <=
            parse_date(offer["end"], prefix + ".end"))


def add_months(day, months):
    months = int(months)
    if months < 0:
        raise ValueError("duration months must not be negative")
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
               31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, lengths[month - 1]))


def offer_state(offer, opening, new_customer, requires_open=True):
    """Return (qualified|conditional|unavailable, conditions)."""
    if opening is None:
        return "conditional", ["account-opening date must be confirmed"]
    if requires_open and not in_window(opening, offer):
        return "unavailable", ["account opening is outside the offer window"]
    conditions = []
    if offer.get("requires_new_customer"):
        if new_customer is False:
            return "unavailable", ["offer is for new customers only"]
        if new_customer is None:
            conditions.append("new-customer status must be confirmed")
    if offer.get("requires_good_standing"):
        conditions.append("account must remain in good standing")
    return ("conditional" if conditions else "qualified"), conditions


def points(amounts, rate_percent, multiplier=Decimal("1")):
    # Cash back is represented as points worth $0.01. Floor each charge separately.
    rate = rate_percent * multiplier / Decimal("100")
    return sum(int((amount * rate * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
               for amount in amounts)


def reward_scenario(label, amounts, rate, multiplier=Decimal("1"), conditions=None):
    earned = points(amounts, rate, multiplier)
    return {
        "label": label,
        "rate_percent": text_number(rate * multiplier),
        "points": earned,
        "cash_value": text_number(Decimal(earned) / Decimal("100")),
        "conditions": conditions or []
    }


def fee_options(product, opening, new_customer):
    standard = decimal(product["annual_fee"], "annual_fee")
    choices = [{"status": "standard", "first_year_fee": text_number(standard), "conditions": []}]
    for offer in product.get("first_year_fee_offers", []):
        state, conditions = offer_state(offer, opening, new_customer)
        if state != "unavailable":
            choices.append({"status": state,
                            "first_year_fee": text_number(decimal(offer["fee"], "fee offer fee")),
                            "conditions": conditions})
    return choices


def statement_credit_options(product, purchase_total, opening, new_customer):
    results = []
    for offer in product.get("statement_credit_offers", []):
        state, conditions = offer_state(offer, opening, new_customer,
                                        offer.get("requires_open_during", True))
        if state == "unavailable":
            continue
        threshold = decimal(offer["net_purchase_threshold"], "statement-credit threshold")
        credit = decimal(offer["credit"], "statement-credit amount")
        met = purchase_total >= threshold
        terms = list(conditions)
        if offer.get("purchases_must_post"):
            terms.append("qualifying net purchases must post within the stated period")
        if offer.get("period_months") is not None:
            terms.append(f"qualifying period is first {int(offer['period_months'])} months after opening")
        if not met:
            terms.append("planned purchases do not meet the documented net-purchase threshold")
        results.append({"status": state,
                        "statement_credit": text_number(credit),
                        "net_purchase_threshold": text_number(threshold),
                        "threshold_met_by_planned_purchases": met,
                        "conditions": terms})
    return results


def promotion_multiplier(product, opening, new_customer, as_of):
    """Return non-base reward multipliers that have not expired by comparison date."""
    output = []
    for offer in product.get("reward_promotions", []):
        state, conditions = offer_state(offer, opening, new_customer,
                                        offer.get("requires_open_during", True))
        if state == "unavailable":
            continue
        if opening is not None and offer.get("duration_months") is not None:
            if as_of >= add_months(opening, offer["duration_months"]):
                continue
            conditions = list(conditions) + [
                f"promotion ends {add_months(opening, offer['duration_months']).isoformat()}"
            ]
        output.append((decimal(offer["multiplier"], "reward promotion multiplier"), state, conditions))
    return output


def evaluate_product(product, amounts, category, merchant, as_of, opening, new_customer, total):
    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("product name must be nonempty")
    default = decimal(product["default_rate_percent"], name + " default rate")
    fee = decimal(product["annual_fee"], name + " annual fee")
    limit = product.get("credit_limit") or {}
    maximum = decimal(limit.get("max"), name + " published maximum")
    minimum = decimal(limit["min"], name + " published minimum") if limit.get("min") is not None else None
    if min(default, fee, maximum) < 0 or (minimum is not None and minimum < 0):
        raise ValueError("rates, fees, and limits must not be negative")

    if total > maximum:
        limit_status = "exceeds_published_maximum"
    elif minimum is not None and total <= minimum:
        limit_status = "at_or_below_published_minimum_if_approved"
    else:
        limit_status = "within_published_range_if_approved"

    selected_rate, selected_label, override = default, "documented default rate", None
    if merchant:
        for rule in product.get("merchant_rate_overrides", []):
            if normalize(merchant) in {normalize(x) for x in rule.get("merchants", [])}:
                override = rule
                selected_rate = decimal(rule["rate_percent"], name + " merchant override")
                selected_label = rule.get("label", "documented merchant-specific rate")
                break
    if override is None and category is not None:
        for rule in product.get("reward_rules", []):
            if normalize(category) in {normalize(x) for x in rule.get("categories", [])}:
                selected_rate = decimal(rule["rate_percent"], name + " category rate")
                selected_label = rule.get("label", "documented category rate")
                break

    scenarios = [reward_scenario(selected_label, amounts, selected_rate)]
    if category is None and override is None:
        seen = {selected_rate}
        for rule in product.get("reward_rules", []):
            rate = decimal(rule["rate_percent"], name + " enhanced rate")
            if rate in seen:
                continue
            seen.add(rate)
            required = ", ".join(str(x) for x in rule.get("categories", []))
            scenarios.append(reward_scenario(
                "conditional " + rule.get("label", "enhanced category rate"), amounts, rate,
                conditions=["merchant category must be confirmed as: " + required]))

    for multiplier, state, conditions in promotion_multiplier(product, opening, new_customer, as_of):
        scenarios.append(reward_scenario("promotional " + selected_label, amounts, selected_rate,
                                         multiplier, list(conditions) +
                                         (["promotion availability is conditional"] if state == "conditional" else [])))

    fees = fee_options(product, opening, new_customer)
    base_value = Decimal(scenarios[0]["cash_value"])
    for choice in fees:
        choice["first_year_net_cash_value"] = text_number(base_value - Decimal(choice["first_year_fee"]))

    return {
        "name": name,
        "purchase_category_confirmed": category is not None or override is not None,
        "credit_limit_assessment": {
            "status": limit_status,
            "published_min": text_number(minimum) if minimum is not None else None,
            "published_max": text_number(maximum),
            "note": "Published limits are subject to underwriting; the assigned available line must cover the full charge."
        },
        "eligibility": product.get("eligibility", {}),
        "reward_scenarios": scenarios,
        "first_year_fee_options": fees,
        "statement_credit_options": statement_credit_options(product, total, opening, new_customer)
    }


def main(payload):
    amounts = [decimal(x, "purchase_amounts item") for x in payload.get("purchase_amounts", [])]
    if not amounts or any(x <= 0 for x in amounts):
        raise ValueError("purchase_amounts must be a nonempty list of positive amounts")
    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    opening = parse_date(payload.get("opening_date"), "opening_date", nullable=True)
    new_customer = payload.get("new_customer")
    if new_customer not in (True, False, None):
        raise ValueError("new_customer must be true, false, or null")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")

    total = sum(amounts, Decimal("0"))
    result = {"purchase_total": text_number(total), "as_of_date": as_of.isoformat(),
              "cash_back_point_conversion": "1 point = $0.01",
              "rounding_policy": "Fractional reward points are rounded down for each separate purchase.",
              "options": [], "validation_errors": []}
    for product in products:
        try:
            result["options"].append(evaluate_product(
                product, amounts, payload.get("purchase_category"), payload.get("merchant_name"),
                as_of, opening, new_customer, total))
        except (KeyError, TypeError, ValueError) as exc:
            name = product.get("name", "unknown") if isinstance(product, dict) else "unknown"
            result["validation_errors"].append({"product": name, "error": str(exc)})
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        sys.exit(2)
