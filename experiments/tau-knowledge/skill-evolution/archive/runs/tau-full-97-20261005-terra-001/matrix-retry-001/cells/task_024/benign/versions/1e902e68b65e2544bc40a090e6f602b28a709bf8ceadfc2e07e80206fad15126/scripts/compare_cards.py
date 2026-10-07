#!/usr/bin/env python3
"""Compare catalog card rewards for one prospective purchase.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(ROOT, "references", "card_catalog.json")


def parse_date(value, field, errors, required=False):
    if value is None or value == "":
        if required:
            errors.append(field + " is required")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        errors.append(field + " must begin with YYYY-MM-DD")
        return None


def money_points(amount, rate):
    # A percent reward rate produces this many points (cents): amount * rate.
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def status_for_min(value, minimum, label):
    if value is None:
        return {"status": "unknown", "reason": label + " was not supplied"}
    if value >= minimum:
        return {"status": "meets_published_minimum", "reason": label + " meets the published minimum"}
    return {"status": "below_published_minimum", "reason": label + " is below the published minimum"}


def evaluate_eligibility(card, fico, paydex, industry):
    checks = [status_for_min(fico, card["personal_fico_min"], "personal FICO")]
    if card.get("paydex_required"):
        checks.append(status_for_min(paydex, card["paydex_min"], "business PAYDEX"))
    elif paydex is None:
        checks.append({"status": "not_required_or_not_supplied", "reason": "PAYDEX is not a stated requirement for this comparison"})
    else:
        checks.append(status_for_min(paydex, card["paydex_min"], "business PAYDEX"))
    needed = card.get("industry_required")
    if needed:
        if industry is None:
            checks.append({"status": "unknown", "reason": "business industry was not supplied; this product is designed for " + needed + " businesses"})
        elif needed.lower() in industry.lower():
            checks.append({"status": "meets_stated_industry", "reason": "supplied industry matches the stated target industry"})
        else:
            checks.append({"status": "may_not_fit_stated_industry", "reason": "this product is designed for " + needed + " businesses"})
    statuses = [x["status"] for x in checks]
    overall = "unknown"
    if any(s in ("below_published_minimum", "may_not_fit_stated_industry") for s in statuses):
        overall = "does_not_meet_or_may_not_fit"
    elif all(s in ("meets_published_minimum", "meets_stated_industry", "not_required_or_not_supplied") for s in statuses):
        overall = "meets_published_minima_only"
    return {"overall": overall, "checks": checks, "disclaimer": "Meeting published criteria does not guarantee approval."}


def limit_fit(card, amount):
    low, high = Decimal(str(card["credit_limit_min"])), Decimal(str(card["credit_limit_max"]))
    if amount > high:
        state = "purchase_exceeds_published_maximum"
    elif amount <= low:
        state = "within_published_range_at_or_below_minimum"
    else:
        state = "within_published_range_but_above_minimum"
    return {"status": state, "published_minimum": str(low), "published_maximum": str(high), "disclaimer": "Published ranges are subject to underwriting and do not promise an approved limit or merchant acceptance."}


def offer_active(offer, opening):
    return opening is not None and date.fromisoformat(offer["start"]) <= opening <= date.fromisoformat(offer["end"])


def offer_result(offer, opening, new_customer, posts_days, claimed, base_points, amount):
    active = offer_active(offer, opening)
    conditions = list(offer.get("conditions", []))
    blockers = []
    if not active:
        blockers.append("account opening date is outside the stated offer window or is unknown")
    if offer.get("new_customer_required") and new_customer is not True:
        blockers.append("new-customer status is not confirmed")
    if offer.get("claim_required") and claimed is not True:
        blockers.append("offer claim/activation is not confirmed")
    result = {"id": offer["id"], "type": offer["type"], "offer_window": {"start": offer["start"], "end": offer["end"]}, "conditions": conditions, "status": "conditional" if not blockers else "not_confirmed", "blockers": blockers}
    if offer["type"] == "rate_multiplier":
        result["multiplier"] = offer["multiplier"]
        result["duration_months"] = offer["duration_months"]
        result["promo_purchase_points"] = base_points * int(offer["multiplier"])
        result["incremental_points"] = result["promo_purchase_points"] - base_points
    elif offer["type"] == "statement_credit":
        threshold = Decimal(str(offer["threshold_amount"]))
        result["threshold_amount"] = str(threshold)
        result["credit_cents"] = offer["credit_cents"]
        if amount < threshold:
            result["status"] = "threshold_not_met_by_this_purchase"
        if posts_days is not None and posts_days > offer["posting_days_max"]:
            result["status"] = "posting_timing_not_met"
            result["blockers"].append("purchase is not expected to post within the stated qualifying window")
    return result


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: " + str(exc)]}))
        return
    errors = []
    try:
        amount = Decimal(str(data.get("purchase_amount")))
        if amount <= 0:
            errors.append("purchase_amount must be greater than zero")
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
        errors.append("purchase_amount must be numeric")
    current = parse_date(data.get("current_date"), "current_date", errors, required=True)
    opening = parse_date(data.get("account_open_date"), "account_open_date", errors)
    if opening is None:
        opening = current
    category = data.get("purchase_category")
    if category is not None:
        category = str(category).strip().lower()
    try:
        with open(CATALOG_PATH, encoding="utf-8") as fh:
            catalog = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": ["catalog could not be read: " + str(exc)]}))
        return
    if category and category not in catalog["category_names"]:
        errors.append("purchase_category is not a supported catalog category")
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return
    fico = data.get("personal_fico")
    paydex = data.get("business_paydex")
    try:
        fico = None if fico is None else Decimal(str(fico))
        paydex = None if paydex is None else Decimal(str(paydex))
    except InvalidOperation:
        print(json.dumps({"ok": False, "errors": ["personal_fico and business_paydex must be numeric when supplied"]}))
        return
    posts = data.get("purchase_posts_within_days")
    if posts is not None:
        try:
            posts = int(posts)
        except (TypeError, ValueError):
            print(json.dumps({"ok": False, "errors": ["purchase_posts_within_days must be an integer when supplied"]}))
            return
    cards = []
    for card in catalog["cards"]:
        base_rate = Decimal(str(card["base_rate_percent"]))
        base_points = money_points(amount, base_rate)
        applied_rate = Decimal(str(card["bonus_rates"].get(category, base_rate))) if category else None
        record = {
            "id": card["id"], "name": card["name"], "base_rate_percent": str(base_rate), "baseline_points": base_points,
            "purchase_category": category, "purchase_points": money_points(amount, applied_rate) if applied_rate is not None else None,
            "eligibility": evaluate_eligibility(card, fico, paydex, data.get("business_industry")),
            "credit_limit_fit": limit_fit(card, amount),
            "possible_bonus_outcomes": [{"category": k, "rate_percent": str(v), "points": money_points(amount, Decimal(str(v)))} for k, v in card["bonus_rates"].items()],
            "conditional_offers": []
        }
        rate_for_offer = applied_rate if applied_rate is not None else base_rate
        points_for_offer = money_points(amount, rate_for_offer)
        for offer in card.get("offers", []):
            record["conditional_offers"].append(offer_result(offer, opening, data.get("new_customer"), posts, data.get("promo_claimed"), points_for_offer, amount))
        cards.append(record)
    print(json.dumps({
        "ok": True,
        "purchase_amount": str(amount),
        "current_date": current.isoformat(),
        "assumed_account_open_date": opening.isoformat(),
        "point_value": "1 point = $0.01 cash back for these cash-back cards",
        "rounding": "points are floored to a whole number for this purchase",
        "category_notice": "Merchant category is processor-assigned; no item description was used to infer it." if category is None else "Calculation uses the supplied merchant category.",
        "cards": cards,
        "universal_conditions": ["The merchant must accept the card and the approved credit limit must cover the charge.", "Rewards are based on net purchases after returns or credits and generally post after the transaction posts and clears."]
    }, sort_keys=True))

if __name__ == "__main__":
    main()
