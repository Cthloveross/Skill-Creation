#!/usr/bin/env python3
"""Create a deterministic posted-card-activity report from normalized card data.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")
DEFAULT_POSTED = {"COMPLETED", "POSTED"}
CENTS = Decimal("0.01")


def fail(message):
    return {"ok": False, "error": message}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_money(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} is required and must be monetary")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid monetary value") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount.quantize(CENTS)


def parse_points(value, field):
    if value is None:
        return None
    text = str(value).strip().lower().replace("points", "").replace(",", "").strip()
    try:
        points = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid point value") from exc
    if not points.is_finite() or points != points.to_integral_value():
        raise ValueError(f"{field} must be a whole finite number")
    return int(points)


def money_text(amount):
    return format(Decimal(amount).quantize(CENTS), ".2f")


def point_cash_value(points):
    return money_text(Decimal(points) / Decimal("100")) if points is not None else None


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type is required")
    card_type = card_type.strip()

    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return fail("accounts and transactions must both be arrays")
    matches = [item for item in accounts if isinstance(item, dict) and item.get("card_type") == card_type]
    if not matches:
        return fail("no account exactly matches the requested card_type")
    if len(matches) != 1:
        return fail("more than one account matches the requested card_type; an account identifier is needed")

    try:
        balance = parse_money(matches[0].get("current_balance"), "account.current_balance")
        account_points = parse_points(matches[0].get("reward_points"), "account.reward_points")
        recent_count = int(payload.get("recent_count", 10))
        if recent_count <= 0:
            raise ValueError("recent_count must be a positive integer")
        start = parse_date(payload["start_date"], "start_date") if payload.get("start_date") else None
        end = parse_date(payload["end_date"], "end_date") if payload.get("end_date") else None
        if start and end and start > end:
            return fail("start_date cannot be after end_date")
    except (TypeError, ValueError) as exc:
        return fail(str(exc))

    statuses_raw = payload.get("posted_statuses", sorted(DEFAULT_POSTED))
    if not isinstance(statuses_raw, list) or not all(isinstance(x, str) and x.strip() for x in statuses_raw):
        return fail("posted_statuses must be an array of nonempty strings")
    posted_statuses = {x.strip().upper() for x in statuses_raw}

    normalized = []
    for index, raw in enumerate(transactions):
        if not isinstance(raw, dict):
            return fail(f"transactions[{index}] must be an object")
        if raw.get("credit_card_type") != card_type:
            continue
        status = raw.get("status")
        if not isinstance(status, str) or status.strip().upper() not in posted_statuses:
            continue
        try:
            txn_date = parse_date(raw.get("transaction_date"), f"transactions[{index}].transaction_date")
            amount = parse_money(raw.get("transaction_amount"), f"transactions[{index}].transaction_amount")
            points = parse_points(raw.get("rewards_earned"), f"transactions[{index}].rewards_earned")
        except ValueError as exc:
            return fail(str(exc))
        if start and txn_date < start or end and txn_date > end:
            continue
        merchant = raw.get("merchant_name")
        category = raw.get("category")
        if not isinstance(merchant, str) or not merchant.strip():
            return fail(f"transactions[{index}].merchant_name is required")
        if category is not None and not isinstance(category, str):
            return fail(f"transactions[{index}].category must be a string when supplied")
        normalized.append({
            "transaction_id": raw.get("transaction_id"),
            "date_value": txn_date,
            "transaction_date": txn_date.isoformat(),
            "merchant_name": merchant.strip(),
            "amount_value": amount,
            "transaction_amount": money_text(amount),
            "category": category.strip() if isinstance(category, str) else None,
            "status": status.strip().upper(),
            "rewards_earned": points,
            "cash_back_value": point_cash_value(points) if card_type == "Silver Rewards Card" else None,
        })

    normalized.sort(key=lambda item: (item["date_value"], str(item["transaction_id"] or "")), reverse=True)
    selected = normalized if start or end else normalized[:recent_count]
    total = sum((item["amount_value"] for item in selected), Decimal("0.00"))

    flags = []
    if card_type == "Silver Rewards Card":
        for txn in selected:
            if (txn["category"] or "").casefold() not in {"travel", "software"} or txn["rewards_earned"] is None:
                continue
            reference_points = int((txn["amount_value"] * Decimal("4")).to_integral_value(rounding=ROUND_DOWN))
            if txn["rewards_earned"] < reference_points - 1:
                flags.append({
                    "transaction_id": txn["transaction_id"],
                    "transaction_date": txn["transaction_date"],
                    "merchant_name": txn["merchant_name"],
                    "category": txn["category"],
                    "recorded_points": txn["rewards_earned"],
                    "recorded_cash_back_value": point_cash_value(txn["rewards_earned"]),
                    "approximate_four_percent_points": reference_points,
                    "approximate_four_percent_cash_back_value": point_cash_value(reference_points),
                    "cash_back_conversion": "1 point = $0.01",
                    "message": "Recorded rewards are materially below a four-percent reference. This is a category/rewards review cue, not proof of an error.",
                })

    output_transactions = []
    for txn in selected:
        output_transactions.append({key: value for key, value in txn.items() if key not in {"date_value", "amount_value"}})
    date_range = None
    if selected:
        dates = [item["date_value"] for item in selected]
        date_range = {"from": min(dates).isoformat(), "through": max(dates).isoformat()}

    return {
        "ok": True,
        "card_type": card_type,
        "account": {
            "current_balance": money_text(balance),
            "reward_points": account_points,
            "cash_back_value": point_cash_value(account_points) if card_type == "Silver Rewards Card" else None,
            "cash_back_conversion": "1 point = $0.01" if card_type == "Silver Rewards Card" else None,
        },
        "transactions": output_transactions,
        "displayed_count": len(output_transactions),
        "displayed_total": money_text(total),
        "date_range": date_range,
        "rewards_review_flags": flags,
        "scope_note": "Total covers only the displayed posted/completed transactions and is not a reconciliation of the current balance.",
    }


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except json.JSONDecodeError:
        result = fail("stdin must contain valid JSON")
    except Exception as exc:
        result = fail(f"unable to summarize activity: {exc}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
