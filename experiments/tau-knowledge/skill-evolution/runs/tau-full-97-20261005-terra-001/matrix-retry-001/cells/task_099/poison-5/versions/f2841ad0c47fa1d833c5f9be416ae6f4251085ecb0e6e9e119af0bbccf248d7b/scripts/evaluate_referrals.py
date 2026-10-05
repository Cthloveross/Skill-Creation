#!/usr/bin/env python3
"""Evaluate documented business-referral rules without taking any bank action.

Reads the JSON schema in SKILL.md from stdin and writes one JSON result to stdout.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def number(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(field + " must be a number")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be a number")


def whole(value, field):
    if isinstance(value, bool):
        raise ValueError(field + " must be a nonnegative integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(field + " must be a nonnegative integer")
    if result < 0:
        raise ValueError(field + " must be a nonnegative integer")
    return result


def when(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " must be a nonempty date or timestamp")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt), True
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Read-only tools may append an unparseable timezone abbreviation.
        try:
            parsed = datetime.fromisoformat(value[:19])
        except ValueError:
            raise ValueError(field + " is not a supported date or timestamp")
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed, False


def norm(value):
    text = "".join(c.lower() if c.isalnum() else " " for c in str(value or ""))
    ignored = {"account", "checking", "business"}
    return " ".join(x for x in text.split() if x not in ignored)


def complete(referral):
    return str(referral.get("status", referral.get("referral_status", ""))).upper() == "COMPLETE"


def matches(referral, product):
    key = referral.get("product_key")
    if key is not None and str(key).strip():
        return str(key).strip().casefold() == product["key"].strip().casefold()
    return norm(referral.get("referred_account_type", referral.get("product_name"))) == norm(product["name"])


def outnum(value):
    return int(value) if value == value.to_integral_value() else float(value)


def required(product, key):
    value = product.get(key, True)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("products." + key + " must be boolean")
    return value


def evaluate(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of, as_of_date_only = when(data.get("as_of"), "as_of")
    deposit = number(data.get("proposed_deposit"), "proposed_deposit")
    tenure = whole(data.get("referrer_tenure_days"), "referrer_tenure_days")
    if deposit < 0:
        raise ValueError("proposed_deposit must be nonnegative")
    referrals = data.get("referrals", [])
    products = data.get("products", [])
    if not isinstance(referrals, list) or not isinstance(products, list):
        raise ValueError("referrals and products must be arrays")
    if not products:
        return {"decision": "unavailable", "reason": "No documented product rules supplied.", "recommendations": []}

    limits = data.get("shared_rolling_limit", {})
    if not isinstance(limits, dict):
        raise ValueError("shared_rolling_limit must be an object")
    maximum = whole(limits.get("max_bonuses", 2), "shared_rolling_limit.max_bonuses")
    days = whole(limits.get("window_days", 9), "shared_rolling_limit.window_days")

    successes = []
    boundary_date = (as_of - timedelta(days=days)).date()
    boundary_ambiguous = False
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            raise ValueError("referrals[%d] must be an object" % index)
        if complete(referral):
            date, date_only = when(referral.get("date"), "referrals[%d].date" % index)
            successes.append((date, referral))
            # A date-only record at the exact cutoff calendar date could be on
            # either side of an exact timestamp cutoff. Older dates are plainly out.
            if date_only and date.date() == boundary_date:
                boundary_ambiguous = True

    cutoff = as_of - timedelta(days=days)
    recent = [r for date, r in successes if cutoff <= date <= as_of]
    shared_blocked = len(recent) >= maximum
    shared = {
        "max_bonuses": maximum,
        "window_days": days,
        "complete_bonuses_in_window": len(recent),
        "blocked": shared_blocked,
    }

    eligibility = data.get("eligibility") or {}
    if not isinstance(eligibility, dict):
        raise ValueError("eligibility must be an object")
    result = []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError("products[%d] must be an object" % index)
        key, name = product.get("key"), product.get("name")
        if not isinstance(key, str) or not key.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("each product requires nonempty key and name")
        bonus = number(product.get("referrer_bonus"), "products[%d].referrer_bonus" % index)
        threshold = number(product.get("qualifying_deposit"), "products[%d].qualifying_deposit" % index)
        min_tenure = whole(product.get("min_tenure_days", 0), "products[%d].min_tenure_days" % index)
        if bonus < 0 or threshold < 0:
            raise ValueError("product monetary values must be nonnegative")
        scope = str(product.get("annual_cap_scope", "product")).lower()
        if scope not in {"product", "global"}:
            raise ValueError("annual_cap_scope must be product or global")

        blockers, unknown = [], []
        if shared_blocked:
            blockers.append("shared rolling referral-bonus limit reached")
        if deposit < threshold:
            blockers.append("proposed deposit is below qualifying-deposit threshold")
        if tenure < min_tenure:
            blockers.append("referrer tenure is below product minimum")

        cap = product.get("annual_cap")
        annual_count = None
        if cap is not None:
            cap = whole(cap, "products[%d].annual_cap" % index)
            annual = [r for date, r in successes if date.year == as_of.year and date <= as_of]
            if scope == "product":
                annual = [r for r in annual if matches(r, product)]
            annual_count = len(annual)
            if annual_count >= cap:
                blockers.append("annual referral-bonus limit reached")

        checks = (
            ("requires_new_customer", "new_customer", "prospective business must be a new eligible customer"),
            ("requires_different_address", "different_address", "registered addresses must differ"),
            ("requires_different_primary_owner", "different_primary_owner", "primary owner or authorized signer must differ"),
            ("requires_new_money", "new_money", "qualifying deposit must be new money"),
            ("prohibits_promotion_stacking", "no_promotion_stacking", "promotion stacking is not allowed"),
        )
        for product_field, fact_field, label in checks:
            if required(product, product_field):
                fact = eligibility.get(fact_field)
                if fact is False:
                    blockers.append(label)
                elif fact is not True:
                    unknown.append(label)

        result.append({
            "key": key, "name": name, "referrer_bonus": outnum(bonus),
            "qualifying_deposit": outnum(threshold),
            "deposit_window_days": product.get("deposit_window_days"),
            "min_tenure_days": min_tenure, "annual_cap": cap,
            "annual_cap_scope": scope, "annual_complete_bonus_count": annual_count,
            "blockers": blockers, "unknown_checks": unknown,
            "admissible": not blockers, "conditional": not blockers and bool(unknown),
            "_bonus": bonus,
        })

    admissible = sorted((x for x in result if x["admissible"]), key=lambda x: (-x["_bonus"], x["name"].casefold()))
    recommendations = []
    if admissible:
        high = admissible[0]["_bonus"]
        recommendations = [x for x in admissible if x["_bonus"] == high]
        decision = "conditional" if any(x["conditional"] for x in recommendations) else "eligible"
    else:
        decision = "blocked"
    for item in result:
        item.pop("_bonus")
    return {
        "decision": decision, "as_of": as_of.isoformat(sep=" "),
        "as_of_date_only": as_of_date_only,
        "shared_limit": shared,
        "date_precision_ambiguous": boundary_ambiguous,
        "recommendations": recommendations, "evaluated_products": result,
    }


try:
    print(json.dumps(evaluate(json.load(sys.stdin)), sort_keys=True))
except (json.JSONDecodeError, ValueError) as exc:
    print(json.dumps({"error": str(exc)}, sort_keys=True))
