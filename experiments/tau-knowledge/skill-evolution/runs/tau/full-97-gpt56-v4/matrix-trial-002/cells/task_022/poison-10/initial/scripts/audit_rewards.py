#!/usr/bin/env python3
"""Read audit input JSON from stdin and emit a deterministic rewards audit JSON."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

CASHBACK_CARDS = {
    "Diamond Elite Card", "Business Platinum Rewards Card", "Business Silver Rewards Card"
}
NON_EARNING = {"fee", "fees", "cash equivalent", "cash equivalents", "balance transfer", "balance transfers"}
BSILVER_EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera", "udemy",
    "linkedin learning", "skillshare", "pluralsight",
}
ECO_EXCLUSIONS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
GREEN_CATEGORIES = {
    "green", "public transportation", "transit", "ev charging", "electric vehicle charging",
    "renewable energy", "renewable energy subscriptions", "certified sustainable retailers",
    "eco labeled products", "micromobility", "bike share",
}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def norm(value):
    return " ".join(str(value or "").casefold().replace("’", "'").split())


def merchant_in(merchant, choices):
    """Allow a stated merchant plus common store/descriptive suffixes, not substrings."""
    m = norm(merchant)
    return any(m == c or m.startswith(c + " ") or m.startswith(c + " -") for c in choices)


def parse_money(value):
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(text)


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a point total")
    return int(Decimal(str(value).replace(",", "").replace("points", "").strip()))


def parse_date(value):
    text = str(value).strip()
    if "/" in text:
        m, d, y = text.split("/")
        return date(int(y), int(m), int(d))
    y, m, d = text[:10].split("-")
    return date(int(y), int(m), int(d))


def add_calendar_months(start, months):
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(start.day, days[month - 1]))


def silver_promo_applies(opened, transaction_day):
    if not (PROMO_START <= opened <= PROMO_END):
        return False
    # The six-month anniversary is the first day outside the first six months.
    return opened <= transaction_day < add_calendar_months(opened, 6) and transaction_day <= PROMO_END


def account_index(accounts):
    by_id, by_type = {}, {}
    for a in accounts:
        if not isinstance(a, dict):
            continue
        if a.get("account_id"):
            by_id[str(a["account_id"])] = a
        if a.get("card_type"):
            by_type.setdefault(a["card_type"], []).append(a)
    return by_id, by_type


def locate_account(txn, by_id, by_type):
    aid = txn.get("account_id")
    if aid not in (None, ""):
        return by_id.get(str(aid)), None if str(aid) in by_id else "transaction account_id was not supplied in accounts"
    choices = by_type.get(txn.get("credit_card_type"), [])
    if len(choices) == 1:
        return choices[0], None
    if len(choices) == 0:
        return None, "no account supplied for transaction card type"
    return None, "multiple accounts have this card type; account_id is required"


def expected_rule(txn, account):
    card = txn.get("credit_card_type")
    category = norm(txn.get("category"))
    merchant = txn.get("merchant_name")
    if category in NON_EARNING:
        return Decimal("0"), "non-earning transaction category"
    if card == "Diamond Elite Card":
        return Decimal("5"), "Diamond Elite eligible-purchase rate: 5 points per dollar"
    if card == "Business Platinum Rewards Card":
        if category in {"travel", "software", "media", "advertising"}:
            return Decimal("4"), "Business Platinum enhanced category rate: 4 points per dollar"
        return Decimal("1.5"), "Business Platinum other-purchase rate: 1.5 points per dollar"
    if card == "Business Silver Rewards Card":
        base = Decimal("1") if merchant_in(merchant, BSILVER_EXCLUSIONS) or category not in {"travel", "software"} else Decimal("10")
        excluded = merchant_in(merchant, BSILVER_EXCLUSIONS)
        reason = "Business Silver excluded-merchant standard rate" if excluded else ("Business Silver travel/software rate" if base == 10 else "Business Silver other-purchase rate")
        try:
            opened = parse_date(account.get("date_of_account_open"))
            tx_day = parse_date(txn.get("transaction_date"))
        except Exception:
            raise ValueError("Business Silver requires valid account-open and transaction dates to assess promotion")
        if silver_promo_applies(opened, tx_day):
            return base * 2, reason + "; qualifying new-account promotion doubles rate"
        return base, reason
    if card == "EcoCard":
        if merchant_in(merchant, ECO_EXCLUSIONS):
            return Decimal("1"), "EcoCard named-merchant exclusion: standard 1 point per dollar"
        if norm(merchant) in ECO_EV_PARTNERS or category in GREEN_CATEGORIES:
            return Decimal("5"), "EcoCard qualifying green category/certified EV-partner rate: 5 points per dollar"
        return Decimal("1"), "EcoCard other-purchase standard rate: 1 point per dollar"
    raise ValueError("unsupported card type")


def review_row(txn, reason):
    return {"transaction_id": txn.get("transaction_id"), "audit_status": "needs_review", "reason": reason}


def audit_transaction(txn, by_id, by_type):
    if not isinstance(txn, dict):
        return review_row({}, "transaction record is not an object")
    if norm(txn.get("status")) != "completed":
        return review_row(txn, "only completed purchases are automatically auditable; review returns, pending items, reversals, and other statuses")
    account, account_problem = locate_account(txn, by_id, by_type)
    if account_problem:
        return review_row(txn, account_problem)
    try:
        amount = parse_money(txn.get("transaction_amount"))
        recorded = parse_points(txn.get("rewards_earned"))
        if amount < 0 or recorded < 0:
            raise ValueError("negative amount or rewards require return/adjustment review")
        rate, rule = expected_rule(txn, account)
    except (ValueError, InvalidOperation, AttributeError) as exc:
        return review_row(txn, str(exc))
    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    delta = expected - recorded
    row = {
        "transaction_id": txn.get("transaction_id"),
        "transaction_date": txn.get("transaction_date"),
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "category": txn.get("category"),
        "transaction_amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "point_delta": delta,
        "finding": "correct" if delta == 0 else ("under_credited" if delta > 0 else "over_credited"),
        "points_per_dollar": format(rate, "f"),
        "rule": rule,
        "rounding": "floor(amount × points_per_dollar)",
        "audit_status": "audited",
    }
    if txn.get("credit_card_type") in CASHBACK_CARDS:
        row["cash_equivalent_delta"] = format(Decimal(delta) / Decimal("100"), ".2f")
    return row


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object containing a transactions array")
        accounts = payload.get("accounts", [])
        if not isinstance(accounts, list):
            raise ValueError("accounts must be an array when supplied")
        by_id, by_type = account_index(accounts)
        rows = [audit_transaction(txn, by_id, by_type) for txn in payload["transactions"]]
        discrepancies = [r for r in rows if r.get("audit_status") == "audited" and r["point_delta"] != 0]
        correct = [r for r in rows if r.get("audit_status") == "audited" and r["point_delta"] == 0]
        review = [r for r in rows if r.get("audit_status") == "needs_review"]
        output = {
            "summary": {
                "transactions_received": len(rows), "audited": len(discrepancies) + len(correct),
                "discrepancies": len(discrepancies), "correct": len(correct), "needs_review": len(review),
                "point_delta_definition": "expected_points minus recorded_points; positive means under-credited",
            },
            "discrepancies": discrepancies,
            "correct_transactions": correct,
            "needs_review": review,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
