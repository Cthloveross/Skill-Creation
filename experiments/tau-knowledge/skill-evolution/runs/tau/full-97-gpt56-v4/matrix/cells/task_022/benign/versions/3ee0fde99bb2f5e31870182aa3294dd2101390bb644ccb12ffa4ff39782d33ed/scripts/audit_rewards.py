#!/usr/bin/env python3
"""Audit supported credit-card transaction rewards.

Reads the JSON schema described in SKILL.md from stdin and emits JSON only.
Uses the standard library and Decimal so points are always floored exactly.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

D = Decimal
SUPPORTED = {
    "diamond elite card", "business platinum rewards card",
    "business silver rewards card", "ecocard",
}
SILVER_EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)
ECO_EXCLUSIONS = ("target", "walmart", "amazon", "thredup")
EV_PARTNERS = ("tesla supercharger", "chargepoint", "evgo")
DEFAULT_PROMO = {"start_date": "2024-11-14", "end_date": "2025-11-14"}


def clean_text(value):
    return " ".join(str(value or "").casefold().split())


def merchant_key(value):
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value)).strip()


def merchant_matches(merchant, names):
    """Match an explicit merchant label plus a safely separated store/product suffix."""
    key = merchant_key(merchant)
    return any(key == n or key.startswith(n + " ") for n in names)


def parse_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(field + " is missing or not numeric")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"(?i)\b(points?|pts?)\b", "", text)
    text = text.replace("$", "").strip()
    try:
        return D(text)
    except InvalidOperation as exc:
        raise ValueError(field + " is not a valid decimal") from exc


def parse_date(value, field):
    text = str(value or "").strip()
    for separator in ("-", "/"):
        parts = text.split(separator)
        if len(parts) != 3:
            continue
        try:
            if len(parts[0]) == 4:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            return date(int(parts[2]), int(parts[0]), int(parts[1]))
        except ValueError:
            pass
    raise ValueError(field + " must be YYYY-MM-DD or MM/DD/YYYY")


def add_months(value, months):
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(value.day, month_lengths[month - 1]))


def points(amount, rate):
    """Return whole earned points; a negative return reverses its original earn."""
    if amount < 0:
        return -int(((-amount * rate).to_integral_value(rounding=ROUND_FLOOR)))
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def category_is(category, *accepted):
    normalized = clean_text(category)
    return normalized in {clean_text(item) for item in accepted}


def silver_promo_applies(opened, transaction_date, promo):
    start = parse_date(promo["start_date"], "business_silver_promo.start_date")
    end = parse_date(promo["end_date"], "business_silver_promo.end_date")
    return start <= opened <= end and opened <= transaction_date <= add_months(opened, 6)


def expected_for(txn, openings, promo):
    card = clean_text(txn.get("credit_card_type"))
    merchant = txn.get("merchant_name", "")
    category = txn.get("category", "")
    amount = parse_decimal(txn.get("transaction_amount"), "transaction_amount")
    txn_date = parse_date(txn.get("transaction_date"), "transaction_date")
    if card not in SUPPORTED:
        return None, None, "unsupported card type"
    # Cash equivalents, balance transfers, and fees do not earn rewards.
    if category_is(category, "cash equivalent", "cash equivalents", "balance transfer", "balance transfers", "fee", "fees"):
        return 0, {"rate": "0", "basis": "Non-reward category: cash equivalents, balance transfers, and fees earn no rewards", "amount": amount}, None

    if card == "diamond elite card":
        rate, basis = D("5"), "Diamond Elite eligible-purchase rate: 5 points per dollar"
    elif card == "business platinum rewards card":
        if category_is(category, "travel", "software", "media", "advertising", "media advertising"):
            rate, basis = D("4"), "Business Platinum enhanced category rate: 4 points per dollar"
        else:
            rate, basis = D("1.5"), "Business Platinum standard rate: 1.5 points per dollar"
    elif card == "business silver rewards card":
        enhanced = category_is(category, "travel", "software") and not merchant_matches(merchant, SILVER_EXCLUSIONS)
        rate = D("10") if enhanced else D("1")
        basis = ("Business Silver Travel/Software bonus: 10 points per dollar" if enhanced
                 else "Business Silver standard/excluded-merchant rate: 1 point per dollar")
        opened = openings.get(card)
        if opened is None:
            return None, None, "missing account opening date needed for Business Silver offer check"
        if silver_promo_applies(opened, txn_date, promo):
            rate *= 2
            basis += "; eligible first-six-month double-rewards offer applied"
        else:
            offer_start = parse_date(promo["start_date"], "business_silver_promo.start_date")
            offer_end = parse_date(promo["end_date"], "business_silver_promo.end_date")
            if not (offer_start <= opened <= offer_end):
                basis += "; double-rewards offer not applied: account opening date is outside its offer window"
            elif txn_date < opened or txn_date > add_months(opened, 6):
                basis += "; double-rewards offer not applied: transaction is outside the first six months"
    else:  # EcoCard
        if merchant_matches(merchant, ECO_EXCLUSIONS):
            rate, basis = D("1"), "EcoCard named-merchant exclusion: 1 point per dollar"
        elif category_is(category, "ev charging", "electric vehicle charging"):
            if merchant_matches(merchant, EV_PARTNERS):
                rate, basis = D("5"), "EcoCard certified EV charging partner rate: 5 points per dollar"
            else:
                rate, basis = D("1"), "EcoCard non-partner EV charging rate: 1 point per dollar"
        elif category_is(category, "green"):
            rate, basis = D("5"), "EcoCard qualifying Green category rate: 5 points per dollar"
        else:
            rate, basis = D("1"), "EcoCard standard rate: 1 point per dollar"
    return points(amount, rate), {"rate": str(rate), "basis": basis, "amount": amount}, None


def output_error(errors):
    return {"ok": False, "errors": errors, "discrepancies": [], "skipped": [], "reviewed_count": 0}


def main(payload):
    if not isinstance(payload, dict):
        return output_error(["input must be a JSON object"])
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return output_error(["accounts and transactions must both be arrays"])

    errors, openings = [], {}
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append("accounts[%d] must be an object" % index)
            continue
        card = clean_text(account.get("card_type"))
        if card == "business silver rewards card":
            try:
                openings[card] = parse_date(account.get("date_of_account_open"), "date_of_account_open")
            except ValueError as exc:
                errors.append("accounts[%d]: %s" % (index, exc))
    promo = payload.get("business_silver_promo", DEFAULT_PROMO)
    if not isinstance(promo, dict) or "start_date" not in promo or "end_date" not in promo:
        errors.append("business_silver_promo must contain start_date and end_date")
    else:
        try:
            start, end = parse_date(promo["start_date"], "business_silver_promo.start_date"), parse_date(promo["end_date"], "business_silver_promo.end_date")
            if end < start:
                errors.append("business_silver_promo end_date precedes start_date")
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        return output_error(errors)

    reviewed, skipped, discrepancies = 0, [], []
    # Keep cash-back reward points and EcoCard sustainability points separate.
    # They share a redemption value, but are distinct reward currencies.
    over, under = 0, 0
    over_cash, under_cash, over_eco, under_eco = 0, 0, 0, 0
    for index, txn in enumerate(transactions):
        identifier = "transactions[%d]" % index
        if not isinstance(txn, dict):
            skipped.append({"input_index": index, "reason": "transaction is not an object"})
            continue
        txn_id = str(txn.get("transaction_id") or "").strip()
        status = clean_text(txn.get("status"))
        if not txn_id:
            skipped.append({"input_index": index, "reason": "missing transaction_id"})
            continue
        # Posted returns/refunds are reviewed so their original rewards can be reversed.
        if status not in {"completed", "refunded", "returned", "reversed"}:
            skipped.append({"transaction_id": txn_id, "reason": "status is not a posted purchase or return"})
            continue
        try:
            recorded_decimal = parse_decimal(txn.get("rewards_earned"), "rewards_earned")
            if recorded_decimal != recorded_decimal.to_integral_value():
                raise ValueError("rewards_earned must be a whole number of points")
            recorded = int(recorded_decimal)
            expected, details, reason = expected_for(txn, openings, promo)
        except ValueError as exc:
            skipped.append({"transaction_id": txn_id, "reason": str(exc)})
            continue
        if reason:
            skipped.append({"transaction_id": txn_id, "reason": reason})
            continue
        reviewed += 1
        difference = expected - recorded
        if difference == 0:
            continue
        direction = "under-awarded" if difference > 0 else "over-awarded"
        magnitude = abs(difference)
        is_eco = clean_text(txn.get("credit_card_type")) == "ecocard"
        if difference > 0:
            under += magnitude
            if is_eco:
                under_eco += magnitude
            else:
                under_cash += magnitude
        else:
            over += magnitude
            if is_eco:
                over_eco += magnitude
            else:
                over_cash += magnitude
        amount_text = format(details["amount"].quantize(D("0.01")), "f")
        discrepancies.append({
            "transaction_id": txn_id,
            "transaction_date": str(txn.get("transaction_date", "")),
            "card_type": txn.get("credit_card_type"),
            "merchant_name": txn.get("merchant_name"),
            "amount": "$" + amount_text,
            "recorded_points": recorded,
            "expected_points": expected,
            "difference_points": difference,
            "direction": direction,
            "reward_currency": "sustainability points" if is_eco else "cash-back points",
            # Every point redeems at one cent.  Preserve the currency label so
            # EcoCard redemption values are not presented as cash-back earnings.
            "recorded_redemption_value": "$%s" % format((D(recorded) / 100).quantize(D("0.01")), "f"),
            "expected_redemption_value": "$%s" % format((D(expected) / 100).quantize(D("0.01")), "f"),
            "difference_redemption_value": "$%s" % format((D(magnitude) / 100).quantize(D("0.01")), "f"),
            "rate_points_per_dollar": details["rate"],
            "rule": details["basis"],
            "calculation": "floor(%s × %s) = %d" % (amount_text, details["rate"], expected),
            "statement_credit_equivalent": "$%s" % format((D(magnitude) / D("100")).quantize(D("0.01")), "f"),
        })
    return {
        "ok": True,
        "reviewed_count": reviewed,
        "correct_count": reviewed - len(discrepancies),
        "skipped": skipped,
        "discrepancies": discrepancies,
        "summary": {
            "total_discrepancy_count": len(discrepancies),
            # Do not add cash-back points and EcoCard sustainability points:
            # they are separate reward currencies.  Their stated redemption
            # values can be added because each point redeems at $0.01.
            "all_rewards": {
                "over_awarded_redemption_value": "$%s" % format((D(over) / 100).quantize(D("0.01")), "f"),
                "under_awarded_redemption_value": "$%s" % format((D(under) / 100).quantize(D("0.01")), "f"),
                "net_magnitude_redemption_value": "$%s" % format((D(under - over).copy_abs() / 100).quantize(D("0.01")), "f"),
                "net_direction": "under-awarded" if under > over else ("over-awarded" if over > under else "balanced"),
            },
            "cash_back_cards": {
                "over_awarded_points": over_cash,
                "under_awarded_points": under_cash,
                "net_expected_minus_recorded_points": under_cash - over_cash,
                "over_awarded_cash_back_equivalent": "$%s" % format((D(over_cash) / 100).quantize(D("0.01")), "f"),
                "under_awarded_cash_back_equivalent": "$%s" % format((D(under_cash) / 100).quantize(D("0.01")), "f"),
            },
            "ecocard_sustainability_points": {
                "over_awarded_points": over_eco,
                "under_awarded_points": under_eco,
                "net_expected_minus_recorded_points": under_eco - over_eco,
                "over_awarded_redemption_value": "$%s" % format((D(over_eco) / 100).quantize(D("0.01")), "f"),
                "under_awarded_redemption_value": "$%s" % format((D(under_eco) / 100).quantize(D("0.01")), "f"),
            },
            "rounding": "Each expected transaction reward is calculated with floor rounding to whole points."
        }
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
    except json.JSONDecodeError as exc:
        result = output_error(["invalid JSON input: " + str(exc)])
    except Exception as exc:  # retain JSON-only interface for executor handling
        result = output_error(["unexpected audit error: " + str(exc)])
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
