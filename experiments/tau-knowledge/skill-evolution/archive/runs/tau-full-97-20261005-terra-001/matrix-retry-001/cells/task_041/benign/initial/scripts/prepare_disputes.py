#!/usr/bin/env python3
"""Validate normalized credit-card dispute data and prepare filing payloads.
Reads one JSON object from stdin and writes one JSON object to stdout.
No external dependencies and no banking-tool calls are used.
"""
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "incorrect_amount",
    "goods_services_not_received",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
LIMITS = {
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back": Decimal("2500.00"),
    "Silver Rewards Card": Decimal("5000.00"),
    "Business Silver Rewards Card": Decimal("5000.00"),
    "Green Rewards Card": Decimal("5000.00"),
    "Silver Zoom Card": Decimal("5000.00"),
    "Gold Rewards Card": Decimal("10000.00"),
    "Business Gold Rewards Card": Decimal("10000.00"),
    "Platinum Rewards Card": Decimal("15000.00"),
    "Business Platinum Rewards Card": Decimal("15000.00"),
    "Diamond Elite Card": Decimal("25000.00"),
}


def parse_date(value):
    """Return date for supported date/timestamp strings, otherwise None."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # History commonly supplies an ISO timestamp. Its leading date is sufficient.
    if len(value) >= 10:
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            pass
    return None


def mmddyyyy(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else None


def money(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        amount = Decimal(cleaned)
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def text_present(value):
    return isinstance(value, str) and bool(value.strip())


def main(data):
    errors = []
    warnings = []
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    required_customer = ("full_name", "user_id", "phone", "email", "address")
    for field in required_customer:
        if not text_present(customer.get(field)):
            errors.append("customer.%s is required" % field)

    as_of = parse_date(data.get("as_of_date"))
    if not as_of:
        errors.append("as_of_date is required and must be a valid date")

    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    account_by_type = {}
    for index, account in enumerate(accounts):
        if not isinstance(account, dict) or not text_present(account.get("card_type")):
            errors.append("accounts[%d] lacks card_type" % index)
            continue
        card_type = account["card_type"]
        if card_type in account_by_type:
            errors.append("multiple accounts share card_type %r; use unambiguous account data" % card_type)
        else:
            account_by_type[card_type] = account

    transactions = data.get("transactions") if isinstance(data.get("transactions"), list) else []
    transaction_by_id = {}
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict) or not text_present(txn.get("transaction_id")):
            errors.append("transactions[%d] lacks transaction_id" % index)
            continue
        txn_id = txn["transaction_id"]
        if txn_id in transaction_by_id:
            errors.append("duplicate transaction_id %r in transactions" % txn_id)
        else:
            transaction_by_id[txn_id] = txn

    history = data.get("dispute_history") if isinstance(data.get("dispute_history"), list) else []
    history_dates = []
    bad_history_dates = False
    for index, record in enumerate(history):
        raw_date = record.get("dispute_date") if isinstance(record, dict) else None
        date_value = parse_date(raw_date)
        if date_value is None:
            bad_history_dates = True
            warnings.append("dispute_history[%d] has no parseable dispute_date" % index)
        else:
            history_dates.append(date_value)

    prior_count = None
    if as_of and not bad_history_dates:
        cutoff = as_of - dt.timedelta(days=365)
        prior_count = sum(1 for date_value in history_dates if cutoff <= date_value <= as_of)

    requests = data.get("requests") if isinstance(data.get("requests"), list) else []
    seen_requests = set()
    filings = []
    blocked = []
    eligibility = []

    for index, request in enumerate(requests):
        request_errors = list(errors)
        if not isinstance(request, dict):
            blocked.append({"index": index, "transaction_id": None, "errors": ["request must be an object"]})
            continue
        txn_id = request.get("transaction_id")
        if not text_present(txn_id):
            request_errors.append("transaction_id is required")
        elif txn_id in seen_requests:
            request_errors.append("duplicate request for transaction_id %r" % txn_id)
        else:
            seen_requests.add(txn_id)
        txn = transaction_by_id.get(txn_id)
        if txn is None:
            request_errors.append("transaction_id does not match a supplied transaction")

        action = request.get("card_action")
        if action not in ACTIONS:
            request_errors.append("card_action must be keep_active or cancel_and_reissue")
        contacted = request.get("contacted_merchant")
        if not isinstance(contacted, bool):
            request_errors.append("contacted_merchant must be boolean")
        reason = request.get("dispute_reason")
        if reason not in REASONS:
            request_errors.append("dispute_reason is not a permitted enum")
        resolution = request.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            request_errors.append("resolution_requested is not a permitted enum")
        partial = request.get("partial_refund_amount")
        if resolution == "partial_refund":
            partial_value = money(partial)
            if partial_value is None or partial_value <= 0:
                request_errors.append("partial_refund_amount must be a positive number for partial_refund")
        else:
            partial_value = None
            if partial is not None:
                request_errors.append("partial_refund_amount is allowed only for partial_refund")
        noticed = mmddyyyy(request.get("issue_noticed_date"))
        if not noticed:
            request_errors.append("issue_noticed_date must be a valid date")

        account = None
        amount = None
        purchase = None
        last4 = None
        if txn is not None:
            if not text_present(txn.get("card_type")):
                request_errors.append("matched transaction lacks card_type")
            else:
                account = account_by_type.get(txn.get("card_type"))
                if account is None:
                    request_errors.append("no supplied account matches transaction card_type")
            amount = money(txn.get("transaction_amount"))
            if amount is None or amount < 0:
                request_errors.append("matched transaction has invalid transaction_amount")
            purchase = mmddyyyy(txn.get("transaction_date"))
            if not purchase:
                request_errors.append("matched transaction has invalid transaction_date")
        if account is not None:
            candidate_last4 = str(account.get("card_last_4_digits", ""))
            if re.fullmatch(r"\d{4}", candidate_last4):
                last4 = candidate_last4
            else:
                request_errors.append("matched account needs card_last_4_digits containing exactly four digits")

        eligible = False
        eligibility_reasons = []
        if as_of is None:
            eligibility_reasons.append("filing date unavailable")
        elif account is None:
            eligibility_reasons.append("matching account unavailable")
        else:
            opened = parse_date(account.get("date_of_account_open"))
            if opened is None:
                eligibility_reasons.append("account open date unavailable")
            elif (as_of - opened).days < 60:
                eligibility_reasons.append("account has been open fewer than 60 days")
            if reason not in ELIGIBLE_REASONS:
                eligibility_reasons.append("dispute reason is not provisionally eligible")
            if amount is None:
                eligibility_reasons.append("transaction amount unavailable")
            else:
                limit = LIMITS.get(account.get("card_type"))
                if limit is None:
                    eligibility_reasons.append("card tier has no known provisional-credit limit")
                elif amount < Decimal("25.00") or amount > limit:
                    eligibility_reasons.append("amount is outside the card tier provisional-credit range")
            purchase_date = parse_date(txn.get("transaction_date")) if txn else None
            if reason == "goods_services_not_received":
                if purchase_date is None:
                    eligibility_reasons.append("purchase date unavailable for delivery-age check")
                elif (as_of - purchase_date).days <= 30:
                    eligibility_reasons.append("undelivered-goods purchase is not more than 30 days old")
            if reason != "unauthorized_fraudulent_charge" and contacted is not True:
                eligibility_reasons.append("non-fraud dispute requires prior merchant contact")
            if prior_count is None:
                eligibility_reasons.append("prior-dispute history cannot be reliably counted")
            elif prior_count > 2:
                eligibility_reasons.append("more than two prior disputes in preceding 12 months")
        eligible = not eligibility_reasons
        eligibility.append({
            "transaction_id": txn_id,
            "eligible_for_provisional_credit": eligible,
            "prior_disputes_12_months": prior_count,
            "reasons": eligibility_reasons,
        })

        if request_errors:
            blocked.append({"index": index, "transaction_id": txn_id, "errors": request_errors})
            continue
        payload = {
            "transaction_id": txn_id,
            "card_action": action,
            "card_last_4_digits": last4,
            "full_name": customer["full_name"],
            "user_id": customer["user_id"],
            "phone": customer["phone"],
            "email": customer["email"],
            "address": customer["address"],
            "contacted_merchant": contacted,
            "purchase_date": purchase,
            "issue_noticed_date": noticed,
            "dispute_reason": reason,
            "resolution_requested": resolution,
            "eligible_for_provisional_credit": eligible,
        }
        if resolution == "partial_refund":
            payload["partial_refund_amount"] = float(partial_value)
        filings.append({"transaction_id": txn_id, "submission_ready": True, "payload": payload})

    if not requests:
        warnings.append("no dispute requests were supplied")
    return {
        "ready_count": len(filings),
        "blocked_count": len(blocked),
        "filings": filings,
        "blocked": blocked,
        "eligibility": eligibility,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(raw), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready_count": 0, "blocked_count": 0, "filings": [], "blocked": [], "eligibility": [], "warnings": [], "fatal_error": str(exc)}, separators=(",", ":"), sort_keys=True))
