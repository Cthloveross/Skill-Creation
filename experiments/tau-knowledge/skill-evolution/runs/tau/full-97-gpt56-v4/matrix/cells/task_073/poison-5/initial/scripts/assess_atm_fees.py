#!/usr/bin/env python3
"""Calculate supported ATM-fee and operator-reimbursement discrepancies.

Input and output are JSON. This helper does not access bank systems and deliberately
requires normalized, evidence-linked withdrawal records from a human review.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("not a decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be finite and non-negative")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def text_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def date_key(value):
    value = str(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def canonical_class(value):
    value = str(value).strip().lower()
    aliases = {
        "blue account": "blue",
        "green account": "green",
        "green account (checking)": "green",
        "light green account": "light_green",
    }
    return aliases.get(value)


def expected_bank_fee(product, network, amount, light_domestic_index=None):
    if network == "foreign":
        if product in ("blue", "green"):
            return max((amount * Decimal("0.03")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("5.00"))
        if product == "light_green":
            if amount <= Decimal("100.00"):
                return Decimal("2.00")
            if amount <= Decimal("300.00"):
                return Decimal("3.50")
            return Decimal("5.00")
    if network == "domestic_out_of_network":
        if product == "blue":
            return min((amount * Decimal("0.01")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("3.00"))
        if product == "green":
            return Decimal("3.00")
        if product == "light_green":
            if light_domestic_index is None:
                raise ValueError("Light Green domestic withdrawal order is required")
            return ZERO if light_domestic_index <= 4 else Decimal("1.50")
    raise ValueError("unsupported product/network combination")


def main(payload):
    errors, review_required, corrections = [], [], []
    accounts = {}
    for item in payload.get("accounts", []):
        account_id = str(item.get("account_id", "")).strip()
        product = canonical_class(item.get("historical_account_class", item.get("account_class", "")))
        if not account_id or not product:
            errors.append({"account_id": account_id or None, "issue": "missing account_id or historically verified supported account class"})
        else:
            accounts[account_id] = product

    raw = payload.get("withdrawals", [])
    if not isinstance(raw, list) or not raw:
        errors.append({"issue": "withdrawals must be a nonempty list"})
        return {"errors": errors, "review_required": review_required, "items": [], "account_summaries": []}

    rows = []
    for pos, item in enumerate(raw):
        try:
            account_id = str(item["account_id"])
            if account_id not in accounts:
                raise ValueError("account is absent from reviewed accounts")
            date = date_key(item["date"])
            amount = money(item["withdrawal_usd"])
            charged = money(item["bank_fee_charged"])
            network = item["network"]
            if network not in ("domestic_out_of_network", "foreign"):
                raise ValueError("network must be domestic_out_of_network or foreign")
            row = dict(item)
            row.update({"_pos": pos, "_date": date, "_amount": amount, "_charged": charged, "_network": network})
            rows.append(row)
        except (KeyError, ValueError) as exc:
            errors.append({"item_index": pos, "issue": str(exc)})

    # A known ordering is material only for Light Green's four-free-withdrawal rule.
    same_day_light = defaultdict(list)
    for row in rows:
        if accounts[row["account_id"]] == "light_green" and row["_network"] == "domestic_out_of_network":
            same_day_light[(row["account_id"], row["_date"])].append(row)
    for key, group in same_day_light.items():
        if len(group) > 1 and any("sequence" not in r for r in group):
            review_required.append({"account_id": key[0], "date": key[1].isoformat(), "issue": "same-day Light Green withdrawal order is not evidenced"})

    rows.sort(key=lambda r: (r["_date"], int(r.get("sequence", 0)), str(r.get("id", r["_pos"]))))
    light_count = defaultdict(int)
    membership = payload.get("membership", {})
    membership_verified = membership.get("verified") is True
    membership_active = membership.get("active") is True
    cap = None
    if membership_verified and membership_active:
        try:
            cap = money(membership.get("cap", "32.00"))
        except ValueError as exc:
            errors.append({"issue": "invalid membership cap: " + str(exc)})
    elif any("operator_fee" in r for r in rows):
        review_required.append({"issue": "operator reimbursement cannot be assessed without verified active membership for the period"})

    reimbursed_entitlement = ZERO
    item_results = []
    per_account = defaultdict(lambda: {"fee_refund_total": ZERO, "rebate_credit_total": ZERO, "fee_refund_count": 0, "rebate_credit_count": 0})
    for row in rows:
        product = accounts[row["account_id"]]
        index = None
        if product == "light_green" and row["_network"] == "domestic_out_of_network":
            light_count[row["account_id"]] += 1
            index = light_count[row["account_id"]]
        try:
            expected = expected_bank_fee(product, row["_network"], row["_amount"], index)
        except ValueError as exc:
            errors.append({"withdrawal_id": row.get("id"), "issue": str(exc)})
            continue
        refund = max(ZERO, row["_charged"] - expected)
        result = {
            "withdrawal_id": row.get("id"), "account_id": row["account_id"], "date": row["_date"].isoformat(),
            "product": product, "network": row["_network"], "withdrawal_usd": text_money(row["_amount"]),
            "correct_bank_fee": text_money(expected), "bank_fee_charged": text_money(row["_charged"]),
            "fee_refund_due": text_money(refund),
        }
        if refund > ZERO:
            corrections.append({"account_id": row["account_id"], "type": "fee_refund", "amount": refund, "withdrawal_id": row.get("id")})
            per_account[row["account_id"]]["fee_refund_total"] += refund
            per_account[row["account_id"]]["fee_refund_count"] += 1

        if cap is not None and "operator_fee" in row:
            try:
                operator_fee = money(row["operator_fee"])
                applied = money(row.get("operator_reimbursement_applied", "0.00"))
                eligible = row.get("operator_fee_eligible") is True
                entitlement = min(operator_fee, max(ZERO, cap - reimbursed_entitlement)) if eligible else ZERO
                reimbursed_entitlement += entitlement
                missing = max(ZERO, entitlement - applied)
                result.update({"eligible_operator_reimbursement": text_money(entitlement), "operator_reimbursement_applied": text_money(applied), "missing_rebate_due": text_money(missing)})
                if missing > ZERO:
                    corrections.append({"account_id": row["account_id"], "type": "rebate_credit", "amount": missing, "withdrawal_id": row.get("id")})
                    per_account[row["account_id"]]["rebate_credit_total"] += missing
                    per_account[row["account_id"]]["rebate_credit_count"] += 1
            except ValueError as exc:
                errors.append({"withdrawal_id": row.get("id"), "issue": "invalid operator reimbursement data: " + str(exc)})
        item_results.append(result)

    summaries = []
    for account_id, values in sorted(per_account.items()):
        fee_n, rebate_n = values["fee_refund_count"], values["rebate_credit_count"]
        total = values["fee_refund_total"] + values["rebate_credit_total"]
        recommendation = None
        if fee_n > rebate_n:
            recommendation = "fee_refund"
        elif rebate_n > fee_n:
            recommendation = "rebate_credit"
        elif total > ZERO:
            review_required.append({"account_id": account_id, "issue": "equal correction-type counts; policy supplies no majority credit type"})
        summaries.append({
            "account_id": account_id, "fee_refund_total": text_money(values["fee_refund_total"]),
            "rebate_credit_total": text_money(values["rebate_credit_total"]), "combined_credit_candidate": text_money(total),
            "fee_refund_corrections": fee_n, "rebate_credit_corrections": rebate_n,
            "recommended_credit_type": recommendation,
        })
    return {"errors": errors, "review_required": review_required, "items": item_results, "corrections": [{**c, "amount": text_money(c["amount"])} for c in corrections], "account_summaries": summaries}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [{"issue": str(exc)}], "review_required": [], "items": [], "account_summaries": []}))
