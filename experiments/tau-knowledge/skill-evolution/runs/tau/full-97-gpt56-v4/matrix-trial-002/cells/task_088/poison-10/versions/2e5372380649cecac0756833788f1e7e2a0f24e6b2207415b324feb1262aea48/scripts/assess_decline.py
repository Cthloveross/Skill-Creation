#!/usr/bin/env python3
"""Summarize normalized evidence for a debit-card decline without taking actions.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. All amounts are numeric USD values. Missing fields are reported,
not assumed. This program has no banking-tool access and never performs actions.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def number(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def money(value):
    return float(value.quantize(Decimal("0.01")))


def main(payload):
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    transactions = payload.get("transactions") if isinstance(payload.get("transactions"), list) else []
    amount = number(payload.get("amount"))
    today = parse_date(payload.get("current_date"))
    findings, missing = [], []

    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    if not checking:
        missing.append("No normalized checking account was supplied.")

    for account in checking:
        account_id = account.get("account_id")
        status = account.get("status")
        balance = number(account.get("balance"))
        matching_cards = [c for c in cards if c.get("account_id") == account_id]
        pending = Decimal("0")
        for txn in transactions:
            if txn.get("account_id") == account_id and str(txn.get("status", "")).lower() == "pending":
                txn_amount = number(txn.get("amount"))
                if txn_amount is not None and txn_amount < 0:
                    pending += -txn_amount
        item = {"account_id": account_id, "status": status, "pending_debits_total": money(pending)}
        if balance is not None:
            item["posted_balance"] = money(balance)
            item["posted_balance_minus_pending_debits"] = money(balance - pending)
            item["balance_note"] = "Estimate only; authorization holds and other availability rules are not represented."
        else:
            missing.append("Posted balance missing for a checking account.")
        if not matching_cards:
            item["card_note"] = "No card linked to this account was supplied."
        else:
            card_facts = []
            for card in matching_cards:
                fact = {"card_id": card.get("card_id"), "status": card.get("status")}
                limit = number(card.get("daily_purchase_limit"))
                used = number(card.get("daily_purchase_used"))
                if limit is None:
                    fact["purchase_limit_note"] = "Daily purchase limit unavailable."
                    missing.append("Daily purchase limit missing for one or more card records.")
                else:
                    fact["daily_purchase_limit"] = money(limit)
                    if used is not None:
                        fact["daily_purchase_used"] = money(used)
                        fact["purchase_limit_remaining"] = money(limit - used)
                        if amount is not None:
                            fact["reported_amount_exceeds_reported_remaining_limit"] = amount > (limit - used)
                    else:
                        fact["purchase_limit_note"] = "Daily purchase usage unavailable; remaining limit cannot be determined."
                card_facts.append(fact)
            item["cards"] = card_facts
        findings.append(item)

    if amount is None:
        missing.append("Reported transaction amount is missing or non-numeric.")
    if today is None:
        missing.append("Current date is missing or invalid; date-based review is unavailable.")

    return {
        "reported_amount": money(amount) if amount is not None else None,
        "findings": findings,
        "missing_data": sorted(set(missing)),
        "safety_note": "This is an evidence summary, not a decision on available balance, authorization holds, fraud, or permission to take a banking action."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "findings": [], "missing_data": ["Input could not be assessed."]}))
        sys.exit(1)
