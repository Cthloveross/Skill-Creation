#!/usr/bin/env python3
"""Validate dispute data and build filing payload candidates.

stdin JSON schema:
{
  "reference_date": "MM/DD/YYYY or YYYY-MM-DD",
  "customer": {"full_name","user_id","phone","email","address"},
  "account": {"card_type","date_of_account_open","card_last_4_digits"},
  "history": {"disputes": [{"dispute_date": "date or timestamp"}]} | null,
  "card_action": "keep_active" | "cancel_and_reissue",
  "disputes": [{
    "transaction": {"transaction_id","purchase_date","amount"},
    "issue_noticed_date": "MM/DD/YYYY",
    "contacted_merchant": true|false,
    "dispute_reason": "allowed reason",
    "resolution_requested": "full_refund|partial_refund|reversal_of_charge",
    "partial_refund_amount": number  # only for partial refund
  }]
}

`history` must contain all prior credit-card disputes when provisional eligibility
is to be determined. Output has one result per input dispute. `tool_payload` is
present only if all filing fields are valid and eligibility is determinable.
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
LIMITS = {
    "Bronze Rewards Card": Decimal("2500"), "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"), "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"), "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"), "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"), "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"), "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}

def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None

def money(value):
    try:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

def prior_count(history, ref):
    if history is None or not isinstance(history, dict) or not isinstance(history.get("disputes"), list):
        return None
    cutoff = ref - timedelta(days=365)
    dates = [parse_date(x.get("dispute_date")) for x in history["disputes"] if isinstance(x, dict)]
    if any(x is None for x in dates):
        return None
    return sum(cutoff <= d <= ref for d in dates)

def provisional(reason, amount, purchase, contacted, account_open, card_limit, prior, ref):
    """Return (True/False/None, explanations). None means additional data needed."""
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        return False, ["Reason is not eligible for provisional credit."]
    missing = []
    if account_open is None: missing.append("account open date")
    if amount is None: missing.append("transaction amount")
    if card_limit is None: missing.append("recognized card tier")
    if prior is None: missing.append("complete prior dispute history")
    if reason == "goods_services_not_received" and purchase is None: missing.append("purchase date")
    if reason != "unauthorized_fraudulent_charge" and not isinstance(contacted, bool): missing.append("merchant-contact answer")
    if missing:
        return None, ["Cannot determine provisional-credit eligibility; obtain " + ", ".join(missing) + "."]
    failures = []
    if (ref - account_open).days < 60: failures.append("Account is less than 60 days old.")
    if amount < Decimal("25"): failures.append("Transaction amount is below $25.00.")
    elif amount > card_limit: failures.append("Transaction amount exceeds the card-tier limit.")
    if prior > 2: failures.append("Customer has more than two prior disputes in the past 12 months.")
    if reason != "unauthorized_fraudulent_charge" and contacted is not True: failures.append("Non-fraud dispute requires merchant contact.")
    if reason == "goods_services_not_received" and (ref - purchase).days <= 30: failures.append("Goods/services-not-received purchase is not more than 30 days old.")
    return (not failures), failures or ["All documented eligibility criteria are met."]

def main(case):
    ref = parse_date(case.get("reference_date"))
    customer = case.get("customer") if isinstance(case.get("customer"), dict) else {}
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    action = case.get("card_action")
    account_open = parse_date(account.get("date_of_account_open"))
    card_limit = LIMITS.get(account.get("card_type"))
    prior = prior_count(case.get("history"), ref) if ref else None
    base_missing = []
    for key in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(customer.get(key), str) or not customer[key].strip():
            base_missing.append("customer." + key)
    last4 = str(account.get("card_last_4_digits", ""))
    if len(last4) != 4 or not last4.isdigit(): base_missing.append("account.card_last_4_digits (exactly four digits)")
    if action not in ACTIONS: base_missing.append("card_action")
    if ref is None: base_missing.append("reference_date")
    results = []
    for item in case.get("disputes", []):
        item = item if isinstance(item, dict) else {}
        txn = item.get("transaction") if isinstance(item.get("transaction"), dict) else {}
        errors = list(base_missing)
        tid = txn.get("transaction_id")
        purchase_text = txn.get("purchase_date")
        purchase = parse_date(purchase_text)
        amount = money(txn.get("amount"))
        noticed_text = item.get("issue_noticed_date")
        noticed = parse_date(noticed_text)
        reason = item.get("dispute_reason")
        resolution = item.get("resolution_requested")
        contacted = item.get("contacted_merchant")
        if not isinstance(tid, str) or not tid.strip(): errors.append("transaction.transaction_id")
        if purchase is None: errors.append("transaction.purchase_date (MM/DD/YYYY)")
        if amount is None or amount < 0: errors.append("transaction.amount")
        if noticed is None: errors.append("issue_noticed_date (MM/DD/YYYY)")
        if reason not in REASONS: errors.append("dispute_reason")
        if resolution not in RESOLUTIONS: errors.append("resolution_requested")
        if not isinstance(contacted, bool): errors.append("contacted_merchant (boolean)")
        partial = money(item.get("partial_refund_amount"))
        if resolution == "partial_refund":
            if partial is None or partial <= 0: errors.append("positive partial_refund_amount")
            elif amount is not None and partial > amount: errors.append("partial_refund_amount cannot exceed transaction amount")
        elif item.get("partial_refund_amount") is not None:
            errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")
        eligible, rationale = provisional(reason, amount, purchase, contacted, account_open, card_limit, prior, ref) if ref else (None, ["Cannot determine eligibility without reference date."])
        payload = None
        if not errors and eligible is not None:
            payload = {
                "transaction_id": tid, "card_action": action, "card_last_4_digits": last4,
                "full_name": customer["full_name"], "user_id": customer["user_id"],
                "phone": customer["phone"], "email": customer["email"], "address": customer["address"],
                "contacted_merchant": contacted, "purchase_date": purchase.strftime("%m/%d/%Y"),
                "issue_noticed_date": noticed.strftime("%m/%d/%Y"), "dispute_reason": reason,
                "resolution_requested": resolution, "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund": payload["partial_refund_amount"] = float(partial)
        results.append({
            "transaction_id": tid, "ready": payload is not None,
            "validation_errors": errors, "eligible_for_provisional_credit": eligible,
            "eligibility_rationale": rationale, "tool_payload": payload,
        })
    return {"reference_date": ref.strftime("%m/%d/%Y") if ref else None,
            "prior_disputes_in_previous_12_months": prior,
            "results": results}

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict): raise ValueError("Input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
