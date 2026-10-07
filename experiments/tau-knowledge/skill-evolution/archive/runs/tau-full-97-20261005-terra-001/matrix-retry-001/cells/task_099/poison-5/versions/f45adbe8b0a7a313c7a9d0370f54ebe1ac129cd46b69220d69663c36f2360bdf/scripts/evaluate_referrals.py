#!/usr/bin/env python3
"""Evaluate generic business checking referral programs.

Reads the JSON schema documented in SKILL.md from stdin and writes a single JSON
object to stdout. This program performs no network, banking, or file actions.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(0)


def as_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError("%s must be a number" % field)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be a number" % field)


def as_nonnegative_int(value, field):
    if isinstance(value, bool):
        raise ValueError("%s must be an integer" % field)
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be an integer" % field)
    if result < 0:
        raise ValueError("%s cannot be negative" % field)
    return result


def parse_datetime(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a nonempty ISO date or timestamp" % field)
    text = value.strip()
    # Date-only values are accepted, but the caller is warned for rolling limits.
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text), True
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            # Supports tool values such as 'YYYY-MM-DD HH:MM:SS EST' by retaining
            # the supplied local calendar timestamp when no offset is available.
            parsed = datetime.fromisoformat(text[:19])
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed, False
    except ValueError:
        raise ValueError("%s is not an ISO date or timestamp" % field)


def normalize(value):
    if not isinstance(value, str):
        return ""
    text = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    words = [word for word in text.split() if word not in {"account", "checking", "business"}]
    return " ".join(words)


def is_complete(record):
    return str(record.get("status", "")).strip().upper() == "COMPLETE"


def product_matches(record, product):
    record_key = record.get("product_key")
    if record_key is not None and str(record_key).strip():
        return str(record_key).strip().casefold() == str(product["key"]).strip().casefold()
    recorded_name = record.get("referred_account_type", record.get("product_name", ""))
    return normalize(recorded_name) == normalize(product["name"])


def json_number(decimal_value):
    # JSON numbers retain integer presentation where possible but avoid float math.
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)


def required_flag(product, field, default=True):
    value = product.get(field, default)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("product.%s must be boolean when supplied" % field)
    return value


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")

    as_of, as_of_date_only = parse_datetime(data.get("as_of"), "as_of")
    proposed_deposit = as_decimal(data.get("proposed_deposit"), "proposed_deposit")
    if proposed_deposit < 0:
        raise ValueError("proposed_deposit cannot be negative")
    tenure = as_nonnegative_int(data.get("referrer_tenure_days"), "referrer_tenure_days")

    referrals = data.get("referrals", [])
    products = data.get("products", [])
    if not isinstance(referrals, list) or not isinstance(products, list):
        raise ValueError("referrals and products must be arrays")
    if not products:
        return {"decision": "unavailable", "reason": "No product rules were supplied.", "recommendations": []}

    limit = data.get("shared_rolling_limit", {})
    if not isinstance(limit, dict):
        raise ValueError("shared_rolling_limit must be an object")
    max_bonuses = as_nonnegative_int(limit.get("max_bonuses", 2), "shared_rolling_limit.max_bonuses")
    window_days = as_nonnegative_int(limit.get("window_days", 9), "shared_rolling_limit.window_days")

    dated_complete = []
    date_only_seen = as_of_date_only
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            raise ValueError("referrals[%d] must be an object" % index)
        if is_complete(referral):
            when, date_only = parse_datetime(referral.get("date"), "referrals[%d].date" % index)
            date_only_seen = date_only_seen or date_only
            dated_complete.append((when, referral))

    window_start = as_of - timedelta(days=window_days)
    recent = [record for when, record in dated_complete if window_start <= when <= as_of]
    shared_blocked = len(recent) >= max_bonuses
    shared = {
        "max_bonuses": max_bonuses,
        "window_days": window_days,
        "window_start": window_start.isoformat(sep=" "),
        "complete_bonuses_in_window": len(recent),
        "blocked": shared_blocked,
    }

    eligibility = data.get("eligibility", {})
    if eligibility is None:
        eligibility = {}
    if not isinstance(eligibility, dict):
        raise ValueError("eligibility must be an object")

    evaluated = []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError("products[%d] must be an object" % index)
        key = product.get("key")
        name = product.get("name")
        if not isinstance(key, str) or not key.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("each product requires nonempty key and name")
        bonus = as_decimal(product.get("referrer_bonus"), "products[%d].referrer_bonus" % index)
        deposit_threshold = as_decimal(product.get("qualifying_deposit"), "products[%d].qualifying_deposit" % index)
        if bonus < 0 or deposit_threshold < 0:
            raise ValueError("product monetary amounts cannot be negative")
        minimum_tenure = as_nonnegative_int(product.get("min_tenure_days", 0), "products[%d].min_tenure_days" % index)
        scope = str(product.get("annual_cap_scope", "product")).strip().lower()
        if scope not in {"product", "global"}:
            raise ValueError("annual_cap_scope must be product or global")

        blockers = []
        unknown = []
        if shared_blocked:
            blockers.append("shared rolling referral-bonus limit reached")
        if proposed_deposit < deposit_threshold:
            blockers.append("proposed deposit is below qualifying-deposit threshold")
        if tenure < minimum_tenure:
            blockers.append("referrer tenure is below product minimum")

        annual_cap = product.get("annual_cap")
        annual_count = None
        if annual_cap is not None:
            annual_cap = as_nonnegative_int(annual_cap, "products[%d].annual_cap" % index)
            start_of_year = datetime(as_of.year, 1, 1)
            year_records = [r for when, r in dated_complete if start_of_year <= when <= as_of]
            if scope == "product":
                year_records = [r for r in year_records if product_matches(r, product)]
            annual_count = len(year_records)
            if annual_count >= annual_cap:
                blockers.append("annual referral-bonus limit reached")

        flag_requirements = [
            ("requires_new_customer", "new_customer", "prospective business must be a new eligible customer"),
            ("requires_different_address", "different_address", "registered addresses must differ"),
            ("requires_different_primary_owner", "different_primary_owner", "primary business owner/signer must differ"),
            ("requires_new_money", "new_money", "qualifying deposit must be new money"),
            ("prohibits_promotion_stacking", "no_promotion_stacking", "promotion stacking is not allowed"),
        ]
        for product_field, fact_field, label in flag_requirements:
            if not required_flag(product, product_field):
                continue
            fact = eligibility.get(fact_field)
            if fact is False:
                blockers.append(label)
            elif fact is not True:
                unknown.append(label)

        evaluated.append({
            "key": key,
            "name": name,
            "referrer_bonus": json_number(bonus),
            "qualifying_deposit": json_number(deposit_threshold),
            "deposit_window_days": product.get("deposit_window_days"),
            "min_tenure_days": minimum_tenure,
            "annual_cap": annual_cap,
            "annual_cap_scope": scope,
            "annual_complete_bonus_count": annual_count,
            "blockers": blockers,
            "unknown_checks": unknown,
            "admissible": not blockers,
            "conditional": not blockers and bool(unknown),
            "_bonus": bonus,
        })

    admissible = [item for item in evaluated if item["admissible"]]
    admissible.sort(key=lambda item: (-item["_bonus"], item["name"].casefold()))
    if admissible:
        top_bonus = admissible[0]["_bonus"]
        recommendations = [item for item in admissible if item["_bonus"] == top_bonus]
        decision = "conditional" if any(item["unknown_checks"] for item in recommendations) else "eligible"
    else:
        recommendations = []
        decision = "blocked"

    for item in evaluated:
        item.pop("_bonus", None)
    for item in recommendations:
        # Items are the same dictionaries as evaluated; no private fields remain.
        pass

    result = {
        "decision": decision,
        "as_of": as_of.isoformat(sep=" "),
        "shared_limit": shared,
        "recommendations": recommendations,
        "evaluated_products": evaluated,
    }
    if date_only_seen:
        result["time_precision_warning"] = (
            "At least one date is date-only. Obtain exact timestamps before relying on a rolling-window boundary."
        )
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError:
        fail("stdin must contain valid JSON")
    except ValueError as exc:
        fail(str(exc))
