#!/usr/bin/env python3
"""Calculate independently earned Silver Rewards Card points.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON.  This
script deliberately does not call banking tools and does not authorize changes:
a caller supplies IDs already supported by approved disputes.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

ENHANCED_CATEGORIES = {"travel", "software"}
POSTED_STATUSES = {"completed", "posted"}
DEFAULT_EXCLUDED = {
    "gift card", "gift cards", "person-to-person payment", "p2p", "fee",
    "fees", "interest", "insurance premium", "bank insurance premium",
    "return", "returned", "refund", "refunded",
}


def fail(message):
    print(json.dumps({"error": message}, separators=(",", ":")))
    raise SystemExit(2)


def text(value):
    return str(value).strip()


def parse_amount(value):
    raw = text(value).replace(",", "")
    if raw.startswith("$"):
        raw = raw[1:].strip()
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("transaction_amount is not a valid decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a nonnegative finite amount")
    return amount


def parse_points(value):
    match = re.fullmatch(r"\s*(\d+)\s*(?:points?)?\s*", text(value), re.I)
    if not match:
        raise ValueError("rewards_earned must be a nonnegative whole point value")
    return int(match.group(1))


def category_is_excluded(category, excluded):
    normalized = text(category).casefold()
    return normalized in excluded


def calculate(transaction, excluded):
    required = ("transaction_id", "transaction_amount", "category", "status", "rewards_earned")
    missing = [key for key in required if key not in transaction or text(transaction[key]) == ""]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    txn_id = text(transaction["transaction_id"])
    if not txn_id:
        raise ValueError("transaction_id must not be empty")
    amount = parse_amount(transaction["transaction_amount"])
    category = text(transaction["category"])
    status = text(transaction["status"])
    stored = parse_points(transaction["rewards_earned"])
    normalized_category = category.casefold()
    normalized_status = status.casefold()

    # This is deliberately a review result rather than a correction candidate
    # when a final posted reward cannot be determined from the supplied record.
    if normalized_status not in POSTED_STATUSES:
        return {
            "transaction_id": txn_id,
            "reviewable": False,
            "reason": "transaction is not posted or completed",
            "status": status,
            "category": category,
            "stored_rewards_earned": f"{stored} points",
        }
    if category_is_excluded(category, excluded):
        return {
            "transaction_id": txn_id,
            "reviewable": False,
            "reason": "excluded transaction category requires reversal/dispute handling",
            "status": status,
            "category": category,
            "stored_rewards_earned": f"{stored} points",
        }

    rate = Decimal("0.04") if normalized_category in ENHANCED_CATEGORIES else Decimal("0.01")
    # A point is one cent of cash back, so dollar amount * cash-back rate * 100.
    points = int((amount * rate * Decimal("100")).to_integral_value(rounding=ROUND_DOWN))
    return {
        "transaction_id": txn_id,
        "reviewable": True,
        "status": status,
        "category": category,
        "amount": format(amount, "f"),
        "rate_percent": format(rate * 100, "f"),
        "calculated_rewards_earned": f"{points} points",
        "stored_rewards_earned": f"{stored} points",
        "discrepancy": points != stored,
        "new_rewards_earned": f"{points} points",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("input must be a JSON object: " + str(exc))
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        fail("transactions must be an array")
    approved = payload.get("approved_transaction_ids", [])
    if not isinstance(approved, list) or not all(isinstance(x, str) and x.strip() for x in approved):
        fail("approved_transaction_ids must be an array of nonempty strings")
    approved = {x.strip() for x in approved}
    extras = payload.get("excluded_categories", [])
    if not isinstance(extras, list) or not all(isinstance(x, str) for x in extras):
        fail("excluded_categories must be an array of strings")
    excluded = DEFAULT_EXCLUDED | {x.strip().casefold() for x in extras if x.strip()}

    results = []
    seen = set()
    try:
        for item in payload["transactions"]:
            if not isinstance(item, dict):
                raise ValueError("each transaction must be an object")
            result = calculate(item, excluded)
            txn_id = result["transaction_id"]
            if txn_id in seen:
                raise ValueError("duplicate transaction_id: " + txn_id)
            seen.add(txn_id)
            results.append(result)
    except ValueError as exc:
        fail(str(exc))

    discrepancies = [r for r in results if r.get("reviewable") and r.get("discrepancy")]
    approved_updates = [
        {"transaction_id": r["transaction_id"], "new_rewards_earned": r["new_rewards_earned"]}
        for r in discrepancies if r["transaction_id"] in approved
    ]
    blocked = [
        {"transaction_id": r["transaction_id"], "new_rewards_earned": r["new_rewards_earned"],
         "reason": "no resolved approved cash-back dispute supplied for this transaction"}
        for r in discrepancies if r["transaction_id"] not in approved
    ]
    print(json.dumps({
        "results": results,
        "discrepancies": discrepancies,
        "approved_updates": approved_updates,
        "blocked_discrepancies": blocked,
    }, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
