#!/usr/bin/env python3
"""Calculate expected transaction rewards for the documented card programs.

Input and output are JSON objects on stdin/stdout. This script performs no network
or banking actions. See SKILL.md for the full schema and interpretation.
"""
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CARD_DIAMOND = "Diamond Elite Card"
CARD_BPLAT = "Business Platinum Rewards Card"
CARD_BSILVER = "Business Silver Rewards Card"
CARD_ECO = "EcoCard"
SUPPORTED = {CARD_DIAMOND, CARD_BPLAT, CARD_BSILVER, CARD_ECO}

SILVER_EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
ECO_STANDARD_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
BPLAT_ZERO_CATEGORIES = {"cash equivalent", "cash equivalents", "balance transfer", "balance transfers", "fee", "fees"}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def norm(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def parse_decimal(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal amount: %r" % value) from exc


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be an integer")
    decimal_value = parse_decimal(value)
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError("rewards_earned must be a whole number")
    return int(decimal_value)


def parse_date(value):
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid date: %r" % value)


def add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    month_days = (date(year + (month == 12), (month % 12) + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(start.day, month_days))


def merchant_matches(merchant, options):
    value = norm(merchant)
    return any(value == item or value.startswith(item + " ") for item in options)


def silver_promotion(account_open, audit_day, transaction_day):
    """Return (multiplier, status). The promotion is evaluated from known terms."""
    if account_open is None or audit_day is None:
        return Decimal("1"), "needs_review_missing_account_open_or_audit_date"
    if not (PROMO_START <= account_open <= PROMO_END):
        return Decimal("1"), "not_eligible_account_not_opened_during_offer"
    promo_through = add_months(account_open, 6)
    if transaction_day < account_open:
        return Decimal("1"), "not_eligible_before_account_open"
    if transaction_day > promo_through:
        return Decimal("1"), "not_eligible_outside_six_month_window"
    return Decimal("2"), "eligible_double_rewards"


def expected_for(txn, open_dates, audit_day):
    card = str(txn["credit_card_type"])
    category = norm(txn.get("category", ""))
    merchant = str(txn.get("merchant_name", ""))
    amount = parse_decimal(txn["transaction_amount"])
    txn_day = parse_date(txn["transaction_date"])
    metadata = {"promotion_status": "not_applicable"}

    if card == CARD_DIAMOND:
        rate, basis = Decimal("5"), "5 points per dollar on eligible purchases"
    elif card == CARD_BPLAT:
        if category in BPLAT_ZERO_CATEGORIES:
            rate, basis = Decimal("0"), "excluded cash equivalent, balance transfer, or fee"
        elif category in {"travel", "software", "media"}:
            rate, basis = Decimal("4"), "4 points per dollar in Business Platinum bonus category"
        else:
            rate, basis = Decimal("1.5"), "1.5 points per dollar outside Business Platinum bonus categories"
    elif card == CARD_BSILVER:
        if category in {"travel", "software"} and not merchant_matches(merchant, SILVER_EXCLUSIONS):
            rate, basis = Decimal("10"), "10 points per dollar in Business Silver bonus category"
        elif category in {"travel", "software"}:
            rate, basis = Decimal("1"), "1 point per dollar due to Business Silver merchant exclusion"
        else:
            rate, basis = Decimal("1"), "1 point per dollar outside Business Silver bonus categories"
        multiplier, promo_status = silver_promotion(open_dates.get(card), audit_day, txn_day)
        rate *= multiplier
        metadata["promotion_status"] = promo_status
        if multiplier == 2:
            basis += "; eligible 2x promotion applied"
        elif promo_status.startswith("needs_review"):
            metadata["needs_review"] = "Business Silver promotion eligibility cannot be fully evaluated"
    elif card == CARD_ECO:
        excluded = merchant_matches(merchant, ECO_STANDARD_MERCHANTS)
        merchant_norm = norm(merchant)
        ev_indicated = "charg" in merchant_norm or "ev " in (merchant_norm + " ")
        ev_partner = merchant_matches(merchant, ECO_EV_PARTNERS)
        if category in {"green", "sustainable"} and not excluded and (not ev_indicated or ev_partner):
            rate, basis = Decimal("5"), "5 sustainability points per dollar for qualifying Green/Sustainable purchase"
        elif category in {"green", "sustainable"} and ev_indicated and not ev_partner:
            rate, basis = Decimal("1"), "1 point per dollar for non-partner EV charging"
        elif excluded:
            rate, basis = Decimal("1"), "1 point per dollar at an EcoCard excluded merchant"
        else:
            rate, basis = Decimal("1"), "1 point per dollar for a non-qualifying purchase"
    else:
        raise ValueError("unsupported credit_card_type: %s" % card)

    # Decimal ROUND_DOWN truncates toward zero, which preserves the sign for reversals.
    points = int((amount * rate).to_integral_value(rounding=ROUND_DOWN))
    return points, rate, basis, metadata


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["input must be a JSON object"]}
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return {"ok": False, "errors": ["transactions must be an array"]}

    errors = []
    open_dates = {}
    accounts = payload.get("accounts", [])
    if accounts is not None and not isinstance(accounts, list):
        errors.append("accounts must be an array when supplied")
        accounts = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append("accounts[%d] must be an object" % index)
            continue
        card = account.get("card_type")
        opened = account.get("date_of_account_open")
        if card == CARD_BSILVER and opened:
            try:
                parsed = parse_date(opened)
                if card in open_dates and open_dates[card] != parsed:
                    errors.append("multiple Business Silver account opening dates; promotion cannot be mapped uniquely")
                    open_dates.pop(card, None)
                elif card not in open_dates:
                    open_dates[card] = parsed
            except ValueError as exc:
                errors.append("accounts[%d]: %s" % (index, exc))

    audit_day = None
    if payload.get("audit_date") is not None:
        try:
            audit_day = parse_date(payload["audit_date"])
        except ValueError as exc:
            errors.append("audit_date: %s" % exc)
    if errors:
        return {"ok": False, "errors": errors}

    include_non_completed = bool(payload.get("include_non_completed", False))
    findings, review_required, skipped = [], [], []
    seen_ids = set()
    per_card = {}

    required = {"transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "transaction_date", "category", "status", "rewards_earned"}
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            errors.append("transactions[%d] must be an object" % index)
            continue
        missing = sorted(required - set(txn))
        if missing:
            errors.append("transactions[%d] missing: %s" % (index, ", ".join(missing)))
            continue
        txn_id = str(txn["transaction_id"])
        if not txn_id or txn_id in seen_ids:
            errors.append("duplicate or empty transaction_id at transactions[%d]" % index)
            continue
        seen_ids.add(txn_id)
        if txn["credit_card_type"] not in SUPPORTED:
            review_required.append({"transaction_id": txn_id, "reason": "unsupported card type", "credit_card_type": txn["credit_card_type"]})
            continue
        if str(txn["status"]).upper() != "COMPLETED" and not include_non_completed:
            skipped.append({"transaction_id": txn_id, "reason": "non-completed transaction", "status": txn["status"]})
            continue
        try:
            actual = parse_points(txn["rewards_earned"])
            expected, rate, basis, metadata = expected_for(txn, open_dates, audit_day)
        except (ValueError, KeyError) as exc:
            errors.append("transactions[%d] (%s): %s" % (index, txn_id, exc))
            continue
        difference = expected - actual
        result = {
            "transaction_id": txn_id,
            "credit_card_type": txn["credit_card_type"],
            "merchant_name": txn["merchant_name"],
            "transaction_date": txn["transaction_date"],
            "category": txn["category"],
            "transaction_amount": str(parse_decimal(txn["transaction_amount"])),
            "rate_points_per_dollar": str(rate),
            "calculation_basis": basis,
            "expected_points": expected,
            "actual_points": actual,
            "point_difference": difference,
            "direction": "match" if difference == 0 else ("potential_under_award" if difference > 0 else "potential_over_award"),
            **metadata,
        }
        if txn["credit_card_type"] != CARD_ECO:
            result["indicative_cash_difference_dollars"] = str((Decimal(difference) / Decimal("100")).quantize(Decimal("0.01")))
        if "needs_review" in metadata:
            review_required.append({**result, "reason": metadata["needs_review"]})
        elif difference != 0:
            findings.append(result)
        card_summary = per_card.setdefault(txn["credit_card_type"], {"transactions_calculated": 0, "matches": 0, "potential_discrepancies": 0, "net_point_difference": 0})
        card_summary["transactions_calculated"] += 1
        card_summary["net_point_difference"] += difference
        if difference == 0:
            card_summary["matches"] += 1
        else:
            card_summary["potential_discrepancies"] += 1

    if errors:
        return {"ok": False, "errors": errors}
    return {
        "ok": True,
        "errors": [],
        "summary": {
            "input_transactions": len(transactions),
            "transactions_calculated": sum(v["transactions_calculated"] for v in per_card.values()),
            "matches": sum(v["matches"] for v in per_card.values()),
            "potential_discrepancies": len(findings),
            "review_required": len(review_required),
            "skipped": len(skipped),
            "by_card": per_card,
        },
        "findings": findings,
        "review_required": review_required,
        "skipped": skipped,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["invalid JSON input: %s" % exc]}))
    except Exception as exc:  # Defensive JSON error for callers; no side effects occurred.
        print(json.dumps({"ok": False, "errors": ["unexpected audit failure: %s" % exc]}))
