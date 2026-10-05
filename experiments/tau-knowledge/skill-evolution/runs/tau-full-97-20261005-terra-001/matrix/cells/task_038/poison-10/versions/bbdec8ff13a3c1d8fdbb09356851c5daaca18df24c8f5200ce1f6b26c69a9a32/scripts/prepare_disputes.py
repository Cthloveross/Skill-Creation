#!/usr/bin/env python3
"""Validate dispute inputs and build file_credit_card_transaction_dispute_4829 arguments.
Reads one JSON object from stdin and writes one JSON object to stdout. No network or bank actions.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {"Entry": Decimal("2500"), "Mid": Decimal("5000"),
          "Premium": Decimal("10000"), "Elite": Decimal("15000"),
          "Invitation": Decimal("25000")}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def mmddyyyy(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else None


def decimal_amount(value):
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
        return amount if amount >= 0 else None
    except (InvalidOperation, AttributeError):
        return None


def normalize_tier(value):
    text = str(value or "").lower()
    if text in {x.lower() for x in LIMITS}:
        return next(x for x in LIMITS if x.lower() == text)
    if any(x in text for x in ("diamond elite",)):
        return "Invitation"
    if any(x in text for x in ("platinum",)):
        return "Elite"
    if any(x in text for x in ("gold", "business gold")):
        return "Premium"
    if any(x in text for x in ("silver", "green rewards", "silver zoom", "business silver")):
        return "Mid"
    if any(x in text for x in ("bronze", "ecocard", "crypto-cash")):
        return "Entry"
    return None


def main(data):
    errors = []
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    today = parse_date(data.get("as_of_date"))
    if not today:
        errors.append("as_of_date is required and must be a valid date")
    required_customer = ("full_name", "user_id", "phone", "email", "address")
    for key in required_customer:
        if not isinstance(customer.get(key), str) or not customer[key].strip():
            errors.append("customer.%s is required" % key)
    opened = parse_date(account.get("account_open_date"))
    if not opened:
        errors.append("account.account_open_date is required and must be a valid date")
    last4 = str(account.get("card_last_4_digits", ""))
    if len(last4) != 4 or not last4.isdigit():
        errors.append("account.card_last_4_digits must contain exactly four digits")
    tier = normalize_tier(account.get("card_tier"))
    if not tier:
        errors.append("account.card_tier is missing or unrecognized")

    history = data.get("prior_disputes")
    if not isinstance(history, list):
        errors.append("prior_disputes must be a list from complete dispute history")
        prior_count = None
    elif not today:
        prior_count = None
    else:
        bad_history = [i for i, item in enumerate(history)
                       if not isinstance(item, dict) or not parse_date(item.get("dispute_date"))]
        if bad_history:
            errors.append("prior_disputes contains invalid dispute_date values")
            prior_count = None
        else:
            cutoff = today - timedelta(days=365)
            prior_count = sum(cutoff <= parse_date(x["dispute_date"]) <= today for x in history)

    entries = data.get("transactions")
    if not isinstance(entries, list) or not entries:
        errors.append("transactions must be a nonempty list")
        entries = []

    output = []
    for index, tx in enumerate(entries):
        tx_errors = []
        if not isinstance(tx, dict):
            output.append({"index": index, "errors": ["transaction must be an object"],
                           "eligible_for_provisional_credit": None, "tool_arguments": None})
            continue
        transaction_id = tx.get("transaction_id")
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            tx_errors.append("transaction_id is required")
        purchase = parse_date(tx.get("purchase_date"))
        noticed = parse_date(tx.get("issue_noticed_date"))
        if not purchase:
            tx_errors.append("purchase_date must be valid")
        if not noticed:
            tx_errors.append("issue_noticed_date must be valid")
        if purchase and noticed and noticed < purchase:
            tx_errors.append("issue_noticed_date cannot precede purchase_date")
        amount = decimal_amount(tx.get("amount"))
        if amount is None:
            tx_errors.append("amount must be a nonnegative number")
        contacted = tx.get("contacted_merchant")
        if not isinstance(contacted, bool):
            tx_errors.append("contacted_merchant must be boolean")
        reason = tx.get("dispute_reason")
        if reason not in REASONS:
            tx_errors.append("dispute_reason is not permitted")
        resolution = tx.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            tx_errors.append("resolution_requested is not permitted")
        partial = tx.get("partial_refund_amount")
        partial_amount = decimal_amount(partial) if partial is not None else None
        if resolution == "partial_refund":
            if partial_amount is None or partial_amount <= 0:
                tx_errors.append("positive partial_refund_amount is required for partial_refund")
            elif amount is not None and partial_amount > amount:
                tx_errors.append("partial_refund_amount cannot exceed transaction amount")
        elif partial is not None:
            tx_errors.append("partial_refund_amount is allowed only for partial_refund")
        action = tx.get("card_action")
        if action not in ACTIONS:
            tx_errors.append("card_action must be keep_active or cancel_and_reissue")

        eligibility = None
        explanation = []
        if reason in REASONS and amount is not None and today and opened and tier and prior_count is not None and purchase:
            eligible = True
            if (today - opened).days < 60:
                eligible = False; explanation.append("account has been open fewer than 60 days")
            if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
                eligible = False; explanation.append("reason is not provisionally eligible")
            if reason == "goods_services_not_received" and (today - purchase).days <= 30:
                eligible = False; explanation.append("goods/services-not-received purchase is not more than 30 days old")
            if amount < Decimal("25"):
                eligible = False; explanation.append("amount is under $25")
            if amount > LIMITS[tier]:
                eligible = False; explanation.append("amount exceeds %s tier limit" % tier)
            if prior_count > 2:
                eligible = False; explanation.append("more than two disputes in the last 12 months")
            if reason != "unauthorized_fraudulent_charge" and contacted is not True:
                eligible = False; explanation.append("non-fraud dispute requires prior merchant contact")
            eligibility = eligible
            if eligible:
                explanation.append("all provisional-credit conditions are satisfied")
        else:
            explanation.append("insufficient valid evidence to calculate eligibility")

        tool_args = None
        if not errors and not tx_errors and eligibility is not None:
            tool_args = {
                "transaction_id": transaction_id,
                "card_action": action,
                "card_last_4_digits": last4,
                "full_name": customer["full_name"],
                "user_id": customer["user_id"],
                "phone": customer["phone"],
                "email": customer["email"],
                "address": customer["address"],
                "contacted_merchant": contacted,
                "purchase_date": mmddyyyy(tx["purchase_date"]),
                "issue_noticed_date": mmddyyyy(tx["issue_noticed_date"]),
                "dispute_reason": reason,
                "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligibility,
            }
            if resolution == "partial_refund":
                tool_args["partial_refund_amount"] = float(partial_amount)
        output.append({"index": index, "eligible_for_provisional_credit": eligibility,
                       "eligibility_explanation": explanation, "errors": tx_errors,
                       "tool_arguments": tool_args})
    return {"ready": not errors and bool(output) and all(not d["errors"] and d["tool_arguments"] is not None for d in output),
            "errors": errors, "prior_disputes_last_12_months": prior_count,
            "card_tier": tier, "disputes": output}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready": False, "errors": [str(exc)], "disputes": []}, separators=(",", ":")))
