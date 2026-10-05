#!/usr/bin/env python3
"""Deterministic reward-review helper.

Reads a JSON object from stdin and writes a JSON object to stdout. See SKILL.md
for the input and output contracts. The program is read-only: it calculates
review findings and never calls banking tools.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

FINAL_STATUSES = {"COMPLETED", "POSTED"}
BUSINESS_BONUS = {"travel", "software", "media"}
SILVER_BONUS = {"travel", "software"}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number or numeric string")
    text = str(value).strip().replace(",", "").replace("$", "")
    text = re.sub(r"\s*points?\s*$", "", text, flags=re.I)
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return amount


def whole_points(amount, percent):
    # amount is dollars; one point has a $0.01 statement-credit value.
    raw_points = amount * percent
    return int(raw_points.to_integral_value(rounding=ROUND_DOWN))


def as_money(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def contains_partner(merchant):
    merchant = norm(merchant)
    return any(partner in merchant for partner in ECO_EV_PARTNERS)


def is_ev_merchant(merchant):
    merchant = norm(merchant)
    return "charg" in merchant or "supercharger" in merchant


def eco_rate(category, merchant):
    category = norm(category)
    merchant_normalized = norm(merchant)
    if any(excluded == merchant_normalized or merchant_normalized.startswith(excluded + " ")
           for excluded in ECO_EXCLUDED_MERCHANTS):
        return Decimal("1"), "explicit EcoCard merchant exclusion"
    if is_ev_merchant(merchant) and not contains_partner(merchant):
        return Decimal("1"), "non-certified EV charging receives EcoCard standard rate"
    if category in {"green", "sustainable"}:
        return Decimal("5"), "qualifying Green/Sustainable category"
    return Decimal("1"), "EcoCard standard rate for non-green purchase"


def configured_rate(transaction, silver_base_rate):
    """Return (rate percent, reason, determination) or (None, reason, state)."""
    override = transaction.get("rate_override_percent")
    if override is not None:
        rate = decimal_value(override, "rate_override_percent")
        return rate, "verified supplied rate override", "determinable"

    card = norm(transaction.get("card_type"))
    category = norm(transaction.get("category"))
    merchant = transaction.get("merchant_name", "")

    if card == "crypto cash back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate", "determinable"
    if card == "business platinum rewards card":
        if category in {"cash equivalent", "cash equivalents", "balance transfer", "fee", "fees"}:
            return Decimal("0"), "Business Platinum excluded transaction type", "determinable"
        if category in BUSINESS_BONUS:
            return Decimal("4"), "Business Platinum Travel, Software, or Media rate", "determinable"
        return Decimal("1.5"), "Business Platinum other-purchase rate", "determinable"
    if card == "silver rewards card":
        if category in SILVER_BONUS:
            return Decimal("4"), "Silver Travel or Software rate", "determinable"
        if silver_base_rate is not None:
            return silver_base_rate, "supplied exact Silver base rate", "determinable"
        return None, "Silver non-bonus exact base rate is not supplied", "minimum_only"
    if card == "ecocard":
        rate, reason = eco_rate(category, merchant)
        return rate, reason, "determinable"
    return None, "no documented rate rule for this card", "unsupported"


def result_base(tx, recorded):
    return {
        "transaction_id": tx["transaction_id"],
        "card_type": tx["card_type"],
        "merchant_name": tx["merchant_name"],
        "category": tx["category"],
        "transaction_amount": str(tx["transaction_amount"]),
        "recorded_rewards_points": str(recorded),
        "recorded_rewards_dollars": as_money(recorded),
    }


def review_one(tx, silver_base_rate):
    required = ["transaction_id", "card_type", "merchant_name", "category",
                "transaction_amount", "rewards_earned", "status"]
    missing = [key for key in required if key not in tx or tx[key] in (None, "")]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))

    amount = decimal_value(tx["transaction_amount"], "transaction_amount")
    recorded_decimal = decimal_value(tx["rewards_earned"], "rewards_earned")
    if recorded_decimal != recorded_decimal.to_integral_value():
        raise ValueError("rewards_earned must be whole-number points")
    recorded = int(recorded_decimal)
    output = result_base(tx, recorded)

    if norm(tx["status"]).upper() not in {norm(s) for s in FINAL_STATUSES}:
        output.update({"state": "not_final", "reason": "transaction is not completed or posted"})
        return output

    if tx.get("reward_eligible") is False:
        output.update({
            "state": "ineligible_with_rewards" if recorded else "matches",
            "reason": "transaction independently marked ineligible for rewards",
            "applicable_rate_percent": "0",
            "expected_rewards_points": "0",
            "expected_rewards_dollars": "0.00",
        })
        if recorded:
            output["recommended_new_rewards_earned"] = "0 points"
        return output

    rate, reason, determination = configured_rate(tx, silver_base_rate)
    if determination == "unsupported":
        output.update({"state": "unsupported_card", "reason": reason})
        return output

    if determination == "minimum_only":
        minimum = whole_points(amount, Decimal("1"))
        output.update({
            "applicable_rate_percent": "at least 1",
            "minimum_rewards_points": str(minimum),
            "minimum_rewards_dollars": as_money(minimum),
            "reason": reason,
        })
        if recorded < minimum:
            output["state"] = "under_credited"
            output["recommended_new_rewards_earned"] = f"{minimum} points"
        else:
            output["state"] = "needs_rate_confirmation"
        return output

    expected = whole_points(amount, rate)
    output.update({
        "applicable_rate_percent": format(rate, "f"),
        "expected_rewards_points": str(expected),
        "expected_rewards_dollars": as_money(expected),
        "reason": reason,
    })
    if recorded == expected:
        output["state"] = "matches"
    elif recorded < expected:
        output["state"] = "under_credited"
        output["recommended_new_rewards_earned"] = f"{expected} points"
    else:
        output["state"] = "over_credited"
        output["recommended_new_rewards_earned"] = f"{expected} points"
    return output


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")

        silver_base_rate = None
        if payload.get("silver_base_rate_percent") is not None:
            silver_base_rate = decimal_value(
                payload["silver_base_rate_percent"], "silver_base_rate_percent"
            )

        results, errors = [], []
        seen_ids = set()
        for index, tx in enumerate(transactions):
            if not isinstance(tx, dict):
                errors.append({"index": index, "error": "transaction must be an object"})
                continue
            transaction_id = tx.get("transaction_id")
            if transaction_id in seen_ids:
                errors.append({"index": index, "transaction_id": transaction_id,
                               "error": "duplicate transaction_id"})
                continue
            seen_ids.add(transaction_id)
            try:
                results.append(review_one(tx, silver_base_rate))
            except (ValueError, KeyError) as exc:
                errors.append({"index": index, "transaction_id": transaction_id,
                               "error": str(exc)})

        counts = {}
        for item in results:
            counts[item["state"]] = counts.get(item["state"], 0) + 1
        output = {
            "results": results,
            "summary": {
                "input_transaction_count": len(transactions),
                "reviewed_transaction_count": len(results),
                "state_counts": counts,
                "calculation": "whole points are truncated toward zero",
                "point_value_dollars": "0.01",
            },
            "errors": errors,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"results": [], "summary": {}, "errors": [{"error": str(exc)}]}))
        sys.exit(2)


if __name__ == "__main__":
    main()
