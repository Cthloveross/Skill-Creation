#!/usr/bin/env python3
"""Conservative arithmetic helper for debit-card decline diagnosis.

Input JSON schema:
{
  "requested_amount": "12.34" | 12.34,
  "transaction_kind": "purchase" | "atm",
  "account": {"status": "OPEN", "balance": "100.00"},
  "card": {"status": "ACTIVE", "daily_purchase_limit": "...",
           "daily_purchase_used": "...", "daily_atm_limit": "...",
           "daily_atm_used": "..."},
  "transactions": [{"amount": "-5.00", "status": "pending", "type": "..."}]
}

Output JSON schema:
{
  "valid": bool,
  "errors": [string],
  "calculations": { ... },
  "signals": [string]
}
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a valid decimal amount")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["input must be a JSON object"], "calculations": {}, "signals": []}

    required = ("requested_amount", "transaction_kind", "account", "card", "transactions")
    for key in required:
        if key not in payload:
            errors.append(f"missing required field: {key}")

    kind = payload.get("transaction_kind")
    if kind not in ("purchase", "atm"):
        errors.append("transaction_kind must be 'purchase' or 'atm'")
    account = payload.get("account")
    card = payload.get("card")
    transactions = payload.get("transactions")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    if not isinstance(card, dict):
        errors.append("card must be an object")
        card = {}
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
        transactions = []

    requested = money(payload.get("requested_amount"), "requested_amount", errors)
    if requested is not None and requested < 0:
        errors.append("requested_amount cannot be negative")

    calculations = {
        "requested_amount": fmt(requested) if requested is not None else None,
        "account_status": account.get("status"),
        "card_status": card.get("status"),
    }
    signals = []

    balance = None
    if "balance" in account:
        balance = money(account.get("balance"), "account.balance", errors)
        calculations["reported_balance"] = fmt(balance) if balance is not None else None
        if balance is not None and requested is not None:
            calculations["reported_balance_minus_request"] = fmt(balance - requested)
            if balance < requested:
                signals.append("reported balance is lower than the requested amount; confirm available funds and holds")

    pending_debits = Decimal("0.00")
    pending_count = 0
    malformed_transactions = 0
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            malformed_transactions += 1
            continue
        if str(transaction.get("status", "")).lower() != "pending":
            continue
        amount = money(transaction.get("amount"), f"transactions[{index}].amount", errors)
        if amount is None:
            continue
        if amount < 0:
            pending_debits += -amount
            pending_count += 1
    calculations["known_pending_debit_count"] = pending_count
    calculations["known_pending_debit_total"] = fmt(pending_debits)
    if malformed_transactions:
        signals.append("some transaction records were not objects and were ignored")
    if pending_debits > 0:
        signals.append("pending debits can reduce available funds; this total may not include authorization holds")

    if kind in ("purchase", "atm"):
        prefix = "daily_purchase" if kind == "purchase" else "daily_atm"
        limit_key = f"{prefix}_limit"
        used_key = f"{prefix}_used"
        if limit_key in card and used_key in card:
            limit = money(card.get(limit_key), f"card.{limit_key}", errors)
            used = money(card.get(used_key), f"card.{used_key}", errors)
            if limit is not None and used is not None:
                remaining = max(Decimal("0.00"), limit - used)
                calculations["daily_limit"] = fmt(limit)
                calculations["daily_used"] = fmt(used)
                calculations["daily_remaining"] = fmt(remaining)
                if requested is not None:
                    calculations["request_exceeds_remaining_daily_limit"] = requested > remaining
                    if requested > remaining:
                        signals.append("requested amount exceeds the calculated remaining daily limit")
        else:
            calculations["daily_limit"] = None
            calculations["daily_used"] = None
            calculations["daily_remaining"] = None
            signals.append("daily limit cannot be calculated because limit or used amount was not returned")

    if account.get("status") not in (None, "OPEN"):
        signals.append("linked account is not OPEN; do not continue with ordinary card use")
    if card.get("status") not in (None, "ACTIVE"):
        signals.append("selected card is not ACTIVE; follow the status-specific workflow")

    return {"valid": not errors, "errors": errors, "calculations": calculations, "signals": signals}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"], "calculations": {}, "signals": []}))
        sys.exit(0)
    print(json.dumps(main(payload), sort_keys=True))
