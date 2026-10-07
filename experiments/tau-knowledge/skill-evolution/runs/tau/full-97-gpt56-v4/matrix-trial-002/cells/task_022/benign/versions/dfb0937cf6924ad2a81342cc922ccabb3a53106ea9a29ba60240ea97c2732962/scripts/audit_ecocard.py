#!/usr/bin/env python3
"""Evidence-bounded EcoCard rewards auditor.

Reads one JSON object from stdin and writes one JSON report to stdout.  This tool
is intentionally conservative: it only calls a rate confirmed when published
rules or caller-supplied historical evidence establish the merchant's status.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

ECOCARD = "ecocard"
EXCLUDED = ("target", "walmart", "amazon", "thredup")
QUALIFYING_EV_NETWORKS = ("tesla supercharger", "chargepoint", "evgo")


def norm(value):
    """Normalize a merchant/card string for conservative name comparisons."""
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def parse_amount(value):
    """Parse a nonnegative currency amount without binary floating-point math."""
    if isinstance(value, bool):
        raise ValueError("transaction_amount must be a currency number or string")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount") from exc
    if amount < 0:
        raise ValueError("transaction_amount must not be negative")
    return amount


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be an integer")
    try:
        points = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("rewards_earned must be an integer") from exc
    if str(value).strip() not in (str(points), "+" + str(points)) and not isinstance(value, int):
        raise ValueError("rewards_earned must be an integer")
    return points


def truncated_points(amount, rate):
    return int((amount * Decimal(rate)).to_integral_value(rounding=ROUND_FLOOR))


def merchant_has_term(merchant, term):
    """Match a published merchant term as a word/phrase, not a substring."""
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", merchant) is not None


def merchant_basis(merchant, transaction_id, verified_ids, verified_merchants):
    """Return (rate, basis) or (None, reason) for an EcoCard transaction."""
    # Exclusions override a green-looking category, product line, or merchant claim.
    for excluded in EXCLUDED:
        if merchant_has_term(merchant, excluded):
            return 1, "published exclusion: " + excluded
    for network in QUALIFYING_EV_NETWORKS:
        if merchant_has_term(merchant, network):
            return 5, "published qualifying EV charging network: " + network
    if transaction_id in verified_ids:
        return 5, "historical green eligibility verified for transaction"
    if merchant in verified_merchants:
        return 5, "historical green eligibility verified for merchant"
    return None, "historic merchant eligibility not established by supplied evidence"


def common_fields(tx, amount, posted):
    result = {
        "transaction_id": tx["transaction_id"],
        "merchant_name": tx["merchant_name"],
        "transaction_amount": format(amount, ".2f"),
        "posted_points": posted,
    }
    for key in ("transaction_date", "category", "status"):
        if key in tx:
            result[key] = tx[key]
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")

    verified_ids_raw = payload.get("historical_green_transaction_ids", [])
    verified_merchants_raw = payload.get("historical_green_merchants", [])
    if not isinstance(verified_ids_raw, list) or not isinstance(verified_merchants_raw, list):
        raise ValueError("historical_green_transaction_ids and historical_green_merchants must be lists")
    verified_ids = {str(x) for x in verified_ids_raw}
    verified_merchants = {norm(x) for x in verified_merchants_raw}

    report = {
        "confirmed_findings": [],
        "needs_eligibility_verification": [],
        "provisional_standard_rate": [],
        "outside_published_bounds": [],
        "skipped_non_ecocard": [],
        "skipped_non_completed": [],
        "input_errors": [],
    }

    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "status", "rewards_earned")
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            report["input_errors"].append({"index": index, "error": "transaction must be an object"})
            continue
        missing = [key for key in required if key not in tx]
        if missing:
            report["input_errors"].append({"index": index, "error": "missing required fields", "fields": missing})
            continue
        try:
            amount = parse_amount(tx["transaction_amount"])
            posted = parse_points(tx["rewards_earned"])
        except ValueError as exc:
            report["input_errors"].append({"transaction_id": str(tx.get("transaction_id", index)), "error": str(exc)})
            continue

        card = norm(tx["credit_card_type"])
        status = norm(tx["status"])
        if card != ECOCARD:
            report["skipped_non_ecocard"].append({
                "transaction_id": str(tx["transaction_id"]),
                "credit_card_type": tx["credit_card_type"],
                "reason": "No published rate schedule for this card was supplied to this auditor.",
            })
            continue
        if status != "completed":
            report["skipped_non_completed"].append({
                "transaction_id": str(tx["transaction_id"]),
                "status": tx["status"],
                "reason": "Evaluate returns, refunds, reversals, and pending records at their original earn rate outside this completed-purchase audit.",
            })
            continue

        merchant = norm(tx["merchant_name"])
        transaction_id = str(tx["transaction_id"])
        base = common_fields(tx, amount, posted)
        rate, basis = merchant_basis(merchant, transaction_id, verified_ids, verified_merchants)
        standard = truncated_points(amount, 1)
        green = truncated_points(amount, 5)

        if rate is None:
            # A category field alone is deliberately not used as merchant proof.
            if posted < standard or posted > green:
                item = dict(base)
                item.update({
                    "published_point_range": {"standard_rate_points": standard, "green_rate_points": green},
                    "reason": "Posted points fall outside the published 1x-to-5x EcoCard purchase range; historic eligibility and posting records require review.",
                })
                report["outside_published_bounds"].append(item)
            elif posted == standard:
                item = dict(base)
                item.update({
                    "expected_standard_rate_points": standard,
                    "reason": "Posted at the standard rate, but the supplied data does not prove whether this merchant was historically green eligible.",
                })
                report["provisional_standard_rate"].append(item)
            else:
                item = dict(base)
                item.update({
                    "possible_points": {"standard_rate": standard, "green_rate": green},
                    "reason": basis,
                })
                report["needs_eligibility_verification"].append(item)
            continue

        expected = truncated_points(amount, rate)
        item = dict(base)
        item.update({
            "required_rate_points_per_dollar": rate,
            "expected_points": expected,
            "point_delta": expected - posted,
            "eligibility_basis": basis,
            "finding": "correct" if expected == posted else "discrepancy",
        })
        report["confirmed_findings"].append(item)

    report["summary"] = {
        "confirmed_discrepancy_count": sum(1 for x in report["confirmed_findings"] if x["finding"] == "discrepancy"),
        "confirmed_correct_count": sum(1 for x in report["confirmed_findings"] if x["finding"] == "correct"),
        "eligibility_dependent_count": len(report["needs_eligibility_verification"]),
        "provisional_standard_count": len(report["provisional_standard_rate"]),
        "out_of_range_count": len(report["outside_published_bounds"]),
    }
    return report


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
