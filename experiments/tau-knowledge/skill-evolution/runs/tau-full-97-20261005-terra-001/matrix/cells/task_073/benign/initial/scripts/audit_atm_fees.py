#!/usr/bin/env python3
"""Calculate confirmed bank ATM-fee overcharges from a complete monthly audit.

Read one JSON object from stdin and write one JSON object to stdout.  This module
uses only the Python standard library and performs no banking actions.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
VALID_CLASSES = {"Blue", "Green", "Light Green"}
VALID_CATEGORIES = {"foreign", "domestic_out_of_network", "in_network"}
VALID_STATUSES = {"posted", "pending"}


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal dollar amount")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative finite amount")
    return result


def parse_date(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        raise ValueError("event date must use MM/DD/YYYY")


def parse_month(value):
    try:
        return datetime.strptime(value, "%m/%Y").strftime("%m/%Y")
    except (TypeError, ValueError):
        raise ValueError("review_month must use MM/YYYY")


def expected_fee(account_class, category, amount, light_green_number):
    """Return (fee, issue). issue is nonempty when policy lacks precision."""
    if category == "in_network":
        return Decimal("0.00"), None
    if account_class == "Blue":
        if category == "domestic_out_of_network":
            fee = min(amount * Decimal("0.01"), Decimal("3.00"))
        else:
            fee = max(amount * Decimal("0.03"), Decimal("5.00"))
    elif account_class == "Green":
        if category == "domestic_out_of_network":
            fee = Decimal("3.00")
        else:
            fee = max(amount * Decimal("0.03"), Decimal("5.00"))
    else:  # Light Green
        if category == "domestic_out_of_network":
            fee = Decimal("0.00") if light_green_number <= 4 else Decimal("1.50")
        elif amount <= Decimal("100.00"):
            fee = Decimal("2.00")
        elif amount <= Decimal("300.00"):
            fee = Decimal("3.50")
        else:
            fee = Decimal("5.00")
    # The policy provides no rounding rule for fractional-cent percentage fees.
    if fee != fee.quantize(CENT):
        return fee, "percentage fee has a fractional-cent result; policy rounding is unspecified"
    return fee, None


def main(payload):
    review_month = parse_month(payload.get("review_month"))
    accounts_raw = payload.get("accounts")
    events_raw = payload.get("events")
    if not isinstance(accounts_raw, list) or not accounts_raw:
        raise ValueError("accounts must be a nonempty list")
    if not isinstance(events_raw, list):
        raise ValueError("events must be a list")

    accounts = {}
    account_blockers = {}
    required_account_fields = (
        "review_complete", "unmatched_atm_fee_count", "unknown_atm_withdrawal_count",
        "prior_refund_for_reviewed_fee", "credit_called_this_interaction",
    )
    for raw in accounts_raw:
        if not isinstance(raw, dict):
            raise ValueError("each account must be an object")
        account_id = raw.get("account_id")
        account_class = raw.get("account_class")
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("each account needs a nonempty account_id")
        if account_id in accounts:
            raise ValueError("account_id appears more than once")
        if account_class not in VALID_CLASSES:
            raise ValueError("account_class must be Blue, Green, or Light Green")
        missing = [f for f in required_account_fields if f not in raw]
        if missing:
            raise ValueError("account missing required controls: " + ", ".join(missing))
        if not isinstance(raw["review_complete"], bool):
            raise ValueError("review_complete must be boolean")
        if not isinstance(raw["prior_refund_for_reviewed_fee"], bool) or not isinstance(raw["credit_called_this_interaction"], bool):
            raise ValueError("refund and credit controls must be boolean")
        for count_field in ("unmatched_atm_fee_count", "unknown_atm_withdrawal_count"):
            if not isinstance(raw[count_field], int) or raw[count_field] < 0:
                raise ValueError(count_field + " must be a non-negative integer")
        accounts[account_id] = {"account_class": account_class, "raw": raw}
        blockers = []
        if not raw["review_complete"]:
            blockers.append("transaction review is not marked complete")
        if raw["unmatched_atm_fee_count"]:
            blockers.append("unmatched ATM fee lines remain")
        if raw["unknown_atm_withdrawal_count"]:
            blockers.append("unclassified ATM withdrawals remain")
        if raw["prior_refund_for_reviewed_fee"]:
            blockers.append("a reviewed fee was already corrected")
        if raw["credit_called_this_interaction"]:
            blockers.append("a credit was already called for this account in this interaction")
        account_blockers[account_id] = blockers

    parsed = []
    required_event_fields = (
        "account_id", "date", "withdrawal_amount", "category", "category_confirmed",
        "withdrawal_status", "fee_status", "bank_fee_attribution_confirmed", "charged_bank_fee",
    )
    for index, raw in enumerate(events_raw):
        if not isinstance(raw, dict):
            raise ValueError("each event must be an object")
        missing = [f for f in required_event_fields if f not in raw]
        if missing:
            raise ValueError("event missing required fields: " + ", ".join(missing))
        account_id = raw["account_id"]
        if account_id not in accounts:
            raise ValueError("event account_id is not present in accounts")
        date = parse_date(raw["date"])
        if date.strftime("%m/%Y") != review_month:
            raise ValueError("every event must belong to review_month")
        category = raw["category"]
        if category not in VALID_CATEGORIES:
            raise ValueError("invalid event category")
        if raw["withdrawal_status"] not in VALID_STATUSES or raw["fee_status"] not in VALID_STATUSES:
            raise ValueError("withdrawal_status and fee_status must be posted or pending")
        if not isinstance(raw["category_confirmed"], bool) or not isinstance(raw["bank_fee_attribution_confirmed"], bool):
            raise ValueError("event confirmation fields must be boolean")
        amount = money(raw["withdrawal_amount"], "withdrawal_amount")
        if amount == 0:
            raise ValueError("withdrawal_amount must be greater than zero")
        charged = money(raw["charged_bank_fee"], "charged_bank_fee")
        sequence = raw.get("sequence", index)
        if not isinstance(sequence, int):
            raise ValueError("sequence must be an integer when supplied")
        parsed.append({
            "index": index, "account_id": account_id, "date": date, "sequence": sequence,
            "category": category, "category_confirmed": raw["category_confirmed"],
            "withdrawal_status": raw["withdrawal_status"], "fee_status": raw["fee_status"],
            "attributed": raw["bank_fee_attribution_confirmed"], "amount": amount, "charged": charged,
        })

    # Light Green free-withdrawal sequence counts confirmed posted domestic OON withdrawals.
    light_counts = {}
    for event in sorted(parsed, key=lambda e: (e["account_id"], e["date"], e["sequence"], e["index"])):
        cls = accounts[event["account_id"]]["account_class"]
        if (cls == "Light Green" and event["category"] == "domestic_out_of_network"
                and event["category_confirmed"] and event["withdrawal_status"] == "posted"):
            light_counts[event["account_id"]] = light_counts.get(event["account_id"], 0) + 1
            event["light_number"] = light_counts[event["account_id"]]
        else:
            event["light_number"] = 0

    results = []
    totals = {account_id: Decimal("0.00") for account_id in accounts}
    for event in parsed:
        account_id = event["account_id"]
        cls = accounts[account_id]["account_class"]
        issues = []
        expected = None
        difference = None
        if not event["category_confirmed"]:
            issues.append("withdrawal category is not confirmed")
        if event["withdrawal_status"] != "posted" or event["fee_status"] != "posted":
            issues.append("relevant withdrawal or fee is pending")
        if not event["attributed"]:
            issues.append("bank-fee attribution is not confirmed")
        if not issues:
            expected, precision_issue = expected_fee(cls, event["category"], event["amount"], event["light_number"])
            if precision_issue:
                issues.append(precision_issue)
            else:
                difference = event["charged"] - expected
                if difference > 0:
                    totals[account_id] += difference
        if issues:
            for issue in issues:
                if issue not in account_blockers[account_id]:
                    account_blockers[account_id].append(issue)
        results.append({
            "account_id": account_id,
            "date": event["date"].strftime("%m/%d/%Y"),
            "category": event["category"],
            "withdrawal_amount": format(event["amount"], ".2f"),
            "light_green_domestic_oon_number": event["light_number"] or None,
            "charged_bank_fee": format(event["charged"], ".2f"),
            "expected_bank_fee": None if expected is None else format(expected, "f"),
            "overcharge": None if difference is None else format(max(difference, Decimal("0.00")), "f"),
            "issues": issues,
        })

    recommendations = []
    account_summary = []
    for account_id, data in accounts.items():
        blockers = account_blockers[account_id]
        total = totals[account_id]
        eligible = not blockers and total > 0
        account_summary.append({
            "account_id": account_id,
            "account_class": data["account_class"],
            "confirmed_overcharge_total": format(total, "f"),
            "blockers": blockers,
            "credit_eligible": eligible,
        })
        if eligible:
            recommendations.append({
                "account_id": account_id,
                "amount": format(total, ".2f"),
                "credit_type": "fee_refund",
                "reason": "Combined confirmed ATM bank-fee overcharges for the reviewed month",
            })
    return {
        "review_month": review_month,
        "event_results": results,
        "accounts": account_summary,
        "credit_recommendations": recommendations,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
