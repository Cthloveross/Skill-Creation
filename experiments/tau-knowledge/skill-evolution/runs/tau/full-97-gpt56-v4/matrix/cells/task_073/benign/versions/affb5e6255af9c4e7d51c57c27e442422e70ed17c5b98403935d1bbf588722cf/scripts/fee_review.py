#!/usr/bin/env python3
"""Calculate documented Rho ATM-fee overcharges without performing bank actions.

Reads {"cases": [...]} from stdin and emits a JSON review object. See SKILL.md for
case schema. Monetary inputs are decimal strings (or JSON numbers) in USD.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal amount")
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    return amount


def fmt(amount):
    return format(amount.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def account_kind(value):
    text = str(value).strip().lower()
    if "light green" in text:
        return "light_green"
    if "blue" in text:
        return "blue"
    if "green" in text:
        return "green"
    return None


def parse_date(value):
    text = str(value).strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError("withdrawal_date must be MM/DD/YYYY or YYYY-MM-DD")


def expected_fee(kind, channel, withdrawal, domestic_index=None):
    if channel == "domestic_in_network":
        return ZERO
    if channel == "domestic_out_of_network":
        if kind == "blue":
            return min(withdrawal * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if kind == "green":
            return Decimal("3.00")
        if kind == "light_green":
            if domestic_index is None:
                raise ValueError("Light Green domestic withdrawal index is unavailable")
            return ZERO if domestic_index <= 4 else Decimal("1.50")
    if channel == "foreign":
        if kind in ("blue", "green"):
            return max(withdrawal * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if kind == "light_green":
            if withdrawal <= Decimal("100.00"):
                return Decimal("2.00")
            if withdrawal <= Decimal("300.00"):
                return Decimal("3.50")
            return Decimal("5.00")
    raise ValueError("unsupported account class or channel")


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        return {"results": [], "total_refund_by_account": {}, "safe_to_credit_accounts": [],
                "blocked_accounts": [], "errors": ["Input must be an object with a cases array."]}

    prepared = []
    results = []
    errors = []
    blocked = set()

    # Parse first so chronological Light Green counting is deterministic.
    for index, case in enumerate(payload["cases"]):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label} must be an object")
            continue
        account_id = str(case.get("account_id", "")).strip()
        if not account_id:
            errors.append(f"{label}: account_id is required")
            continue
        try:
            kind = account_kind(case.get("account_class", ""))
            if kind is None:
                raise ValueError("account_class is not a supported Blue, Green, or Light Green class")
            date = parse_date(case.get("withdrawal_date", ""))
            channel = str(case.get("channel", "")).strip()
            if channel not in {"domestic_out_of_network", "domestic_in_network", "foreign"}:
                raise ValueError("channel must be domestic_out_of_network, domestic_in_network, or foreign")
            withdrawal = money(case.get("withdrawal_amount"), "withdrawal_amount")
            charged = money(case.get("rho_fee_charged"), "rho_fee_charged")
            if withdrawal <= ZERO:
                raise ValueError("withdrawal_amount must be greater than zero")
            if charged < ZERO:
                raise ValueError("rho_fee_charged cannot be negative")
        except ValueError as exc:
            errors.append(f"{label} ({account_id}): {exc}")
            blocked.add(account_id)
            continue
        prepared.append({"source_index": index, "case": case, "account_id": account_id,
                         "kind": kind, "date": date, "channel": channel,
                         "withdrawal": withdrawal, "charged": charged})

    # Light Green free domestic withdrawals reset by account and calendar month.
    light_groups = defaultdict(list)
    for item in prepared:
        if item["kind"] == "light_green" and item["channel"] == "domestic_out_of_network":
            light_groups[(item["account_id"], item["date"].year, item["date"].month)].append(item)
    domestic_position = {}
    for group in light_groups.values():
        group.sort(key=lambda item: (item["date"], item["source_index"]))
        for position, item in enumerate(group, 1):
            domestic_position[item["source_index"]] = position

    totals = defaultdict(lambda: ZERO)
    for item in prepared:
        case = item["case"]
        account_id = item["account_id"]
        status = str(case.get("status", "")).strip().lower()
        owner = str(case.get("charge_owner", "")).strip().lower()
        confirmed = case.get("match_confirmed") is True
        base = {"case_index": item["source_index"], "account_id": account_id,
                "withdrawal_date": item["date"].strftime("%m/%d/%Y"),
                "channel": item["channel"], "charged_fee": fmt(item["charged"])}
        if status != "posted":
            base.update({"outcome": "not_refundable_pending_or_nonposted", "expected_fee": None,
                         "overcharge": "0.00"})
            results.append(base)
            continue
        if owner != "rho_bank":
            base.update({"outcome": "blocked_fee_owner_not_confirmed_as_rho_bank", "expected_fee": None,
                         "overcharge": "0.00"})
            results.append(base)
            blocked.add(account_id)
            continue
        if not confirmed:
            base.update({"outcome": "blocked_withdrawal_fee_match_not_confirmed", "expected_fee": None,
                         "overcharge": "0.00"})
            results.append(base)
            blocked.add(account_id)
            continue
        try:
            position = domestic_position.get(item["source_index"])
            expected = expected_fee(item["kind"], item["channel"], item["withdrawal"], position)
        except ValueError as exc:
            base.update({"outcome": f"blocked_{exc}", "expected_fee": None, "overcharge": "0.00"})
            results.append(base)
            blocked.add(account_id)
            continue
        overcharge = max(ZERO, item["charged"] - expected)
        totals[account_id] += overcharge
        base.update({"outcome": "overcharge" if overcharge > ZERO else "fee_matches_schedule",
                     "expected_fee": fmt(expected), "overcharge": fmt(overcharge)})
        if position is not None:
            base["light_green_domestic_withdrawal_number_in_month"] = position
        results.append(base)

    refund_by_account = {account: fmt(total) for account, total in totals.items()
                         if total > ZERO and account not in blocked}
    return {
        "results": results,
        "total_refund_by_account": refund_by_account,
        "safe_to_credit_accounts": sorted(refund_by_account),
        "blocked_accounts": sorted(a for a in blocked if a),
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), indent=2, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"results": [], "total_refund_by_account": {}, "safe_to_credit_accounts": [],
                          "blocked_accounts": [], "errors": [f"Invalid JSON input: {exc.msg}"]}))
        sys.exit(2)
