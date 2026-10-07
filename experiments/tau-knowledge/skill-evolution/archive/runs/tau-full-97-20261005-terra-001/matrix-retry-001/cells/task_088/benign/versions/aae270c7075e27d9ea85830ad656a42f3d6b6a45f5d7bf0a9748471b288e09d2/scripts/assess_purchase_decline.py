#!/usr/bin/env python3
"""Deterministic decision support for a debit-card purchase decline.

Reads one JSON object from stdin and emits one JSON object to stdout. It performs
no bank action and does not access tools, clocks, or external files.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "")).quantize(CENT)
    except (InvalidOperation, ValueError):
        return None


def money_text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def truthy(value):
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"})


def normalize_code(value):
    if value is None:
        return None
    code = str(value).upper().replace("CODE", "").strip()
    return code if code else None


def add(finding_list, kind, message, **data):
    item = {"kind": kind, "message": message}
    item.update(data)
    finding_list.append(item)


def main(payload):
    errors = []
    findings = []
    missing = []
    next_steps = []
    gates = []

    amount = money(payload.get("purchase_amount"))
    if amount is None or amount <= 0:
        errors.append("purchase_amount must be a positive USD number.")

    accounts = payload.get("accounts")
    cards_map = payload.get("cards_by_account")
    transactions_map = payload.get("transactions_by_account")
    if not isinstance(accounts, list):
        errors.append("accounts must be an array from the account lookup.")
        accounts = []
    if not isinstance(cards_map, dict):
        errors.append("cards_by_account must map account IDs to card arrays.")
        cards_map = {}
    if not isinstance(transactions_map, dict):
        errors.append("transactions_by_account must map account IDs to transaction arrays.")
        transactions_map = {}

    today = parse_date(payload.get("today"))
    if payload.get("today") and today is None:
        errors.append("today must be YYYY-MM-DD, MM/DD/YYYY, or a timestamp beginning with YYYY-MM-DD.")

    checking = []
    account_by_id = {}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_id = account.get("account_id")
        if account_id is not None:
            account_by_id[str(account_id)] = account
        if str(account.get("account_type", "")).lower() == "checking":
            checking.append(account)

    if not checking:
        add(findings, "no_checking_account", "No checking account was supplied; debit cards cannot be linked to savings accounts.")
        missing.append("Retrieve all customer accounts and identify the relevant checking account.")

    selector_id = str(payload.get("card_id")) if payload.get("card_id") is not None else None
    selector_last4 = str(payload.get("card_last4")).strip() if payload.get("card_last4") is not None else None
    candidates = []
    for account in checking:
        account_id = str(account.get("account_id", ""))
        cards = cards_map.get(account_id, [])
        if not isinstance(cards, list):
            errors.append("cards_by_account[%s] must be an array." % account_id)
            continue
        for card in cards:
            if not isinstance(card, dict):
                continue
            matches_id = selector_id is not None and str(card.get("card_id")) == selector_id
            matches_last4 = selector_last4 is not None and str(card.get("card_number_last_4", "")).strip() == selector_last4
            if selector_id is None and selector_last4 is None:
                # Do not silently select one card; list only non-sensitive metadata.
                candidates.append((account, card, False))
            elif matches_id or matches_last4:
                candidates.append((account, card, True))

    output_cards = []
    for account, card, selected in candidates:
        output_cards.append({
            "account_id": account.get("account_id"),
            "card_id": card.get("card_id"),
            "last4": card.get("card_number_last_4"),
            "status": card.get("status"),
            "selected_by_input": selected,
        })

    if selector_id or selector_last4:
        selected = [x for x in candidates if x[2]]
        if not selected:
            missing.append("The supplied card selector did not match a card on the supplied checking accounts; confirm card last four digits or card ID.")
        elif len(selected) > 1:
            errors.append("Card selector matched more than one card; do not take a card action until the intended card is unambiguous.")
    else:
        selected = []
        if len(candidates) == 1:
            missing.append("Confirm that the single listed card is the card used, or collect its last four digits before a card action.")
        else:
            missing.append("Collect the last four digits of the card used to select the correct card.")

    code = normalize_code(payload.get("reported_decline_code"))
    if code is None:
        add(findings, "no_decline_code", "No decline code is available; conclusions must remain provisional until card, account, and activity checks are completed.")
        next_steps.append("Ask the customer to check the app or merchant for the exact decline code while completing the generic card-status sequence.")

    if code == "19":
        add(findings, "retry_guidance", "Code 19 is a momentary processing error; an immediate retry is appropriate.")
    elif code in {"91", "96"}:
        add(findings, "retry_guidance", "Code %s is a temporary issuer/system issue; retry in a few minutes and wait 10–15 minutes if it persists." % code)
    elif code == "92":
        add(findings, "retry_guidance", "Code 92 is a temporary routing issue; retry, then use another terminal or merchant if it persists.")

    for account, card, _ in selected:
        account_id = str(account.get("account_id", ""))
        status = str(card.get("status", "")).upper()
        account_status = str(account.get("status", "")).upper()
        if status:
            add(findings, "card_status", "Selected card status is %s." % status, card_id=card.get("card_id"), status=status)
        else:
            missing.append("Selected card status was not returned.")
        if status == "FROZEN":
            gates.append("Unfreeze only after verified ownership, confirmation the customer wants unfreeze, and confirmation the linked checking account is OPEN.")
        elif status == "CLOSED":
            next_steps.append("Check all cards on this account for an active or pending replacement; a closed card cannot be used.")
        elif status == "PENDING":
            next_steps.append("Follow the issue-reason-specific card activation procedure; a pending card cannot be used for purchases.")

        if account_status:
            add(findings, "account_status", "Linked checking account status is %s." % account_status, account_id=account.get("account_id"), status=account_status)
        else:
            missing.append("Linked checking-account status was not returned.")
        if account_status != "OPEN":
            gates.append("Do not attempt a card transaction action while the linked account is not OPEN; use the restricted-account wording without disclosing restriction details when applicable.")

        if truthy(card.get("fraud_alert_active")):
            source = str(card.get("alert_source", "unknown"))
            add(findings, "fraud_alert", "A fraud alert is active; source is %s." % source, alert_source=source)
            if source == "bank_initiated":
                gates.append("Bank-initiated fraud alerts must not be cleared; transfer to security.")
            elif source == "customer_initiated":
                gates.append("Clear a customer-initiated alert only after identity verification and customer confirmation that recent activity is legitimate.")
            else:
                missing.append("Determine the fraud-alert source before considering any clearance.")
        elif "fraud_alert_active" not in card:
            missing.append("Fraud-alert status was not returned for the selected card.")

        if truthy(card.get("velocity_blocked")):
            add(findings, "velocity_block", "A velocity block is active; it normally expires after 30 minutes.")
            gates.append("Clear a velocity block early only after identity verification and a reasonable explanation for unusual activity.")
        elif "velocity_blocked" not in card:
            missing.append("Velocity-block status was not returned for the selected card.")

        balance = money(account.get("balance"))
        if amount is not None:
            if balance is None:
                missing.append("Linked checking-account balance is unavailable or malformed.")
            elif balance < amount:
                add(findings, "balance_screen", "Displayed balance is below the declined purchase amount; insufficient available funds is plausible.", balance=money_text(balance), purchase_amount=money_text(amount))
            else:
                add(findings, "balance_screen", "Displayed balance covers the purchase amount, but this does not establish available funds because holds and pending debits can reduce it.", balance=money_text(balance), purchase_amount=money_text(amount))

        txs = transactions_map.get(account_id, [])
        if not isinstance(txs, list):
            errors.append("transactions_by_account[%s] must be an array." % account_id)
            txs = []
        pending_debits = Decimal("0")
        same_day_purchases = Decimal("0")
        overdraft_recent = False
        unparsable_dates = 0
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            tx_amount = money(tx.get("amount"))
            tx_date = parse_date(tx.get("date"))
            if tx.get("date") and tx_date is None:
                unparsable_dates += 1
            if tx_amount is not None and tx_amount < 0 and str(tx.get("status", "")).lower() == "pending":
                pending_debits += -tx_amount
            if today and tx_date == today and tx_amount is not None and tx_amount < 0 and str(tx.get("type", "")).lower() == "debit_card_purchase":
                same_day_purchases += -tx_amount
            if today and tx_date and (today - tx_date).days in range(0, 31) and str(tx.get("type", "")).lower() == "overdraft_fee":
                overdraft_recent = True
        if txs:
            add(findings, "pending_debits", "Pending negative transactions total %s; authorization holds may not be included." % money_text(pending_debits), pending_debits=money_text(pending_debits))
        else:
            missing.append("Retrieve transaction history to assess pending debits and recent overdraft fees.")
        if unparsable_dates:
            missing.append("Some transaction dates could not be parsed; do not use them for same-day or 30-day eligibility calculations.")

        limit = money(card.get("daily_purchase_limit"))
        used = money(card.get("daily_purchase_used"))
        used_source = "card field"
        if used is None and today and txs:
            used = same_day_purchases
            used_source = "same-day transactions (conservative clue, not authoritative card usage)"
        if limit is None:
            missing.append("Daily purchase limit was not returned for the selected card.")
        elif used is None:
            missing.append("Daily purchase usage is unavailable; retrieve card-provided daily_purchase_used before a definitive limit conclusion.")
        else:
            remaining = max(Decimal("0"), limit - used)
            add(findings, "purchase_limit_screen", "Purchase limit is %s, reported/estimated use is %s, and nonnegative remaining capacity is %s." % (money_text(limit), money_text(used), money_text(remaining)), limit=money_text(limit), used=money_text(used), remaining=money_text(remaining), usage_source=used_source)
            if amount is not None and amount > remaining:
                add(findings, "possible_limit_decline", "The purchase exceeds remaining calculated purchase capacity; a daily purchase limit may explain the decline.")
                opened = parse_date(account.get("date_opened"))
                eligible = status == "ACTIVE" and account_status == "OPEN" and opened is not None and today is not None and (today - opened).days >= 60 and not overdraft_recent
                max_limit = limit * Decimal("1.5")
                needed_limit = used + amount
                if eligible and needed_limit <= max_limit:
                    next_steps.append("A temporary purchase-limit increase may be eligible; verify no increase was granted in the previous 24 hours and obtain customer authorization.")
                else:
                    gates.append("Temporary limit increase is not yet established: it requires ACTIVE card, OPEN account, at least 60 days account age, no overdraft fee in last 30 days, 24-hour frequency eligibility, and a new limit no greater than 150% of current limit.")

        if code == "82":
            next_steps.append("Ask whether the chip or stripe is physically damaged; if not damaged, review for suspicious activity before any replacement/security action.")
        if code in {"51", None}:
            next_steps.append("Review authorization holds, pending debits, and POS overdraft setting before concluding that the displayed balance was available.")

    if selected:
        if not payload.get("identity_verified", False):
            gates.append("Identity is not marked verified. Do not reveal sensitive details or perform freeze, unfreeze, alert clearance, transfer, limit-increase, closure, replacement, or activation actions.")
        next_steps.insert(0, "Apply the generic sequence in order: selected-card status, linked-account status, fraud-alert source, then velocity-block status.")

    return {
        "validation_errors": errors,
        "candidate_cards": output_cards,
        "findings": findings,
        "missing_data": list(dict.fromkeys(missing)),
        "recommended_next_steps": list(dict.fromkeys(next_steps)),
        "action_gates": list(dict.fromkeys(gates)),
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"validation_errors": ["Invalid script input: %s" % exc], "candidate_cards": [], "findings": [], "missing_data": [], "recommended_next_steps": [], "action_gates": []}, separators=(",", ":")))
