#!/usr/bin/env python3
"""Calculate a Platinum Rewards annual-fee rebate review from supplied records.

The program is read-only.  It reads one JSON object from stdin and emits one
JSON result on stdout; it never calls a banking service or changes an account.
"""

import calendar
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
# These are transaction classifications, not merchant-name keywords.  In
# particular, a merchant such as "Coffee Shop" must not be rejected merely
# because its name happens to contain the letters in "fee".
EXCLUDED_PHRASES = (
    "fee", "interest", "adjustment", "cash advance", "cash equivalent",
    "balance transfer", "money order", "traveler check", "travellers check",
    "person to person", "p2p", "funding transaction",
)
REDUCTION_PHRASES = ("return", "refund", "credit")
COMPLETED_WORDS = ("completed", "posted", "cleared", "settled")


def parse_date(value):
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD, MM/DD/YYYY, or YYYY/MM/DD")


def add_months(anchor, months):
    """Add months from the original anniversary anchor without cumulative drift."""
    raw_month = anchor.month - 1 + months
    year = anchor.year + raw_month // 12
    month = raw_month % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def parse_money(value):
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("transaction_amount must be a numeric currency value") from exc


def money(value):
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


def normalized_classification(record):
    """Return only fields that can classify a transaction; never merchant text."""
    values = [record.get(key, "") for key in
              ("category", "transaction_type", "type", "description")]
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(v).lower()).strip() for v in values)


def has_phrase(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def is_reduction(record):
    text = normalized_classification(record)
    return any(has_phrase(text, phrase) for phrase in REDUCTION_PHRASES)


def record_is_eligible(record):
    """Decide inclusion using supplied flags, status, and classification fields."""
    if record.get("eligible") is False or record.get("is_disputed") is True:
        return False
    status = str(record.get("status", "")).strip().lower()
    if status and not any(word in status for word in COMPLETED_WORDS):
        return False
    text = normalized_classification(record)
    if "dispute" in text and "resolved" not in text:
        return False
    return not any(has_phrase(text, phrase) for phrase in EXCLUDED_PHRASES)


def contribution(record, amount):
    """Return the net-purchase contribution after applying a posted credit/return."""
    # Feeds sometimes represent credits as positive absolute dollars.  A record
    # explicitly classified as a return/refund/credit always reduces spend;
    # signed ordinary purchase records retain their source sign.
    return -abs(amount) if is_reduction(record) else amount


def transaction_date(record):
    for key in ("posting_date", "transaction_date", "posted_date", "date"):
        if record.get(key) not in (None, ""):
            return parse_date(record[key])
    raise ValueError("transaction has no posting or transaction date")


def latest_completed_year(opened, as_of, fee_waived_first_year=False):
    """Return the latest closed fee-billed year start offset, if any."""
    if as_of < opened:
        return None
    offset = 12 if fee_waived_first_year else 0
    latest = None
    while add_months(opened, offset + 12) <= as_of:
        latest = offset
        offset += 12
    return latest


def main(payload):
    required = ("account_open_date", "as_of_date", "transactions")
    missing = [key for key in required if key not in payload]
    if missing:
        return {"assessment_status": "insufficient_input", "error": "missing required input: " + ", ".join(missing)}
    try:
        opened = parse_date(payload["account_open_date"])
        as_of = parse_date(payload["as_of_date"])
        threshold = parse_money(payload.get("monthly_threshold", "7500.00"))
        rebate = parse_money(payload.get("rebate_amount", "150.00"))
    except (ValueError, TypeError) as exc:
        return {"assessment_status": "insufficient_input", "error": str(exc)}
    if threshold < 0 or rebate < 0:
        return {"assessment_status": "insufficient_input", "error": "threshold and rebate amount must not be negative"}
    if not isinstance(payload["transactions"], list):
        return {"assessment_status": "insufficient_input", "error": "transactions must be a JSON array"}
    waived = payload.get("fee_waived_first_year", False)
    if not isinstance(waived, bool):
        return {"assessment_status": "insufficient_input", "error": "fee_waived_first_year must be true or false when supplied"}

    year_offset = latest_completed_year(opened, as_of, waived)
    if year_offset is None:
        return {"assessment_status": "not_yet_assessable", "account_open_date": opened.isoformat(),
                "as_of_date": as_of.isoformat(),
                "reason": "No complete fee-billed 12-month cardmember year had closed as of the review date."}

    starts = [add_months(opened, year_offset + i) for i in range(13)]
    totals = [Decimal("0.00") for _ in range(12)]
    included = [0 for _ in range(12)]
    excluded = ignored_other_card = malformed = 0
    desired_card_type = payload.get("card_type")

    for record in payload["transactions"]:
        if not isinstance(record, dict):
            malformed += 1
            continue
        if desired_card_type and record.get("credit_card_type") not in (None, "", desired_card_type):
            ignored_other_card += 1
            continue
        try:
            posted = transaction_date(record)
            amount = parse_money(record.get("transaction_amount", record.get("amount")))
        except (ValueError, TypeError):
            malformed += 1
            continue
        if not (starts[0] <= posted < starts[12]):
            continue
        index = next(i for i in range(12) if starts[i] <= posted < starts[i + 1])
        if record_is_eligible(record):
            totals[index] += contribution(record, amount)
            included[index] += 1
        else:
            excluded += 1

    windows = []
    for i in range(12):
        total = totals[i].quantize(MONEY)
        shortfall = max(Decimal("0.00"), threshold - total).quantize(MONEY)
        windows.append({"window_number": i + 1, "start_date": starts[i].isoformat(),
                        "end_date": (starts[i + 1] - timedelta(days=1)).isoformat(),
                        "eligible_net_purchase_total": money(total), "monthly_threshold": money(threshold),
                        "shortfall": money(shortfall), "meets_threshold": total >= threshold,
                        "included_transaction_count": included[i]})

    eligible = all(window["meets_threshold"] for window in windows)
    return {"assessment_status": "eligible" if eligible else "not_eligible", "eligible": eligible,
            "rebate_amount_if_eligible": money(rebate), "fee_waived_first_year": waived, "account_open_date": opened.isoformat(),
            "as_of_date": as_of.isoformat(), "cardmember_year_start": starts[0].isoformat(),
            "cardmember_year_end": (starts[12] - timedelta(days=1)).isoformat(),
            "monthly_threshold": money(threshold), "monthly_windows": windows,
            "failed_window_numbers": [w["window_number"] for w in windows if not w["meets_threshold"]],
            "excluded_transaction_count_in_reviewed_year": excluded,
            "ignored_other_card_transaction_count": ignored_other_card,
            "malformed_or_unusable_transaction_count": malformed,
            "data_note": "Result is based only on supplied records and their supplied posting/status/classification fields."}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"assessment_status": "insufficient_input", "error": str(exc)}, sort_keys=True))
