#!/usr/bin/env python3
"""Conservative, deterministic preliminary review of ATM transaction exports.

Reads JSON from stdin and writes a JSON review to stdout.  It intentionally marks
ambiguous mappings and eligibility as needing evidence rather than calculating a
refund from a guess.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def amount(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def is_atm_fee(tx):
    return tx.get("type") == "atm_fee" or "atm" in str(tx.get("description", "")).lower() and "fee" in str(tx.get("description", "")).lower()


def is_withdrawal(tx):
    return tx.get("type") == "atm_withdrawal"


def item(tx, state, reason, expected=None, correction=None):
    result = {
        "transaction_id": tx.get("transaction_id"),
        "date": tx.get("date"),
        "description": tx.get("description"),
        "charged_amount": format(amount(tx.get("amount")) or Decimal("0.00"), ".2f"),
        "state": state,
        "reason": reason,
    }
    if expected is not None:
        result["expected_amount"] = format(expected, ".2f")
    if correction is not None:
        result["exact_correction"] = format(correction, ".2f")
    return result


def foreign_fee_expected(withdrawal_amount):
    if withdrawal_amount <= Decimal("100.00"):
        return Decimal("2.00")
    if withdrawal_amount <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def main(data):
    product = data.get("product")
    txs = data.get("transactions")
    if product not in ("bluest", "light_green") or not isinstance(txs, list):
        raise ValueError("product must be bluest or light_green and transactions must be a list")

    posted = [t for t in txs if t.get("status") == "posted"]
    withdrawals = {str(t.get("transaction_id")): t for t in posted if is_withdrawal(t)}
    fees = [t for t in posted if is_atm_fee(t)]
    output = {"month": data.get("month"), "product": product,
              "confirmed_candidates": [], "needs_evidence": [], "notes": []}

    # Count only unambiguously identified posted domestic out-of-network withdrawals.
    domestic_oont = [t for t in posted if is_withdrawal(t) and t.get("is_foreign") is False
                    and t.get("out_of_network") is True]
    domestic_oont.sort(key=lambda t: (str(t.get("date", "")), str(t.get("transaction_id", ""))))
    domestic_rank = {str(t.get("transaction_id")): i + 1 for i, t in enumerate(domestic_oont)}

    third_party_total = Decimal("0.00")
    for fee in fees:
        charged = amount(fee.get("amount"))
        if charged is None:
            output["needs_evidence"].append(item(fee, "needs_evidence", "ATM fee amount is missing or invalid."))
            continue
        kind = fee.get("fee_kind")
        related_id = fee.get("related_withdrawal_id")
        withdrawal = withdrawals.get(str(related_id)) if related_id is not None else None
        foreign = fee.get("is_foreign")
        if foreign is None and withdrawal is not None:
            foreign = withdrawal.get("is_foreign")

        if kind not in ("rho", "third_party"):
            output["needs_evidence"].append(item(fee, "needs_evidence", "Fee source is not identified as Rho-Bank or third party."))
            continue
        if withdrawal is None:
            output["needs_evidence"].append(item(fee, "needs_evidence", "No explicit posted related withdrawal is supplied."))
            continue

        if product == "bluest":
            active = data.get("bluest_benefits_active")
            if active is not True:
                output["needs_evidence"].append(item(fee, "needs_evidence", "Bluest balance eligibility for benefits is not established."))
                continue
            if kind == "rho" and foreign is True:
                correction = charged
                output["confirmed_candidates"].append(item(fee, "confirmed", "Bluest has no Rho-Bank foreign ATM withdrawal fee.", Decimal("0.00"), correction))
            elif kind == "third_party":
                available = max(Decimal("0.00"), Decimal("50.00") - third_party_total)
                eligible = min(charged, available)
                third_party_total += charged
                if eligible > Decimal("0.00"):
                    output["confirmed_candidates"].append(item(fee, "confirmed", "Eligible third-party fee rebate within Bluest monthly $50 cap; verify that no matching rebate posted.", Decimal("0.00"), eligible))
                else:
                    output["notes"].append("Third-party ATM fee %s is beyond the $50 monthly Bluest rebate cap." % fee.get("transaction_id"))
            else:
                output["notes"].append("Bluest domestic Rho-Bank ATM fee %s requires schedule/context review; it is not automatically a mischarge." % fee.get("transaction_id"))
            continue

        # Light Green
        if foreign is True:
            withdrawal_amount = amount(withdrawal.get("withdrawal_amount", withdrawal.get("amount")))
            if kind != "rho":
                output["notes"].append("Light Green foreign third-party charge %s is separate from the Rho-Bank fee schedule." % fee.get("transaction_id"))
            elif withdrawal_amount is None:
                output["needs_evidence"].append(item(fee, "needs_evidence", "Foreign withdrawal amount is needed to apply Light Green tiered fee."))
            else:
                expected = foreign_fee_expected(withdrawal_amount)
                if charged > expected:
                    output["confirmed_candidates"].append(item(fee, "confirmed", "Charged Rho-Bank foreign fee exceeds the per-withdrawal Light Green tier.", expected, charged - expected))
                elif charged < expected:
                    output["notes"].append("Light Green foreign fee %s is not an overcharge under the supplied tier schedule." % fee.get("transaction_id"))
                else:
                    output["notes"].append("Light Green foreign fee %s matches the supplied tier schedule." % fee.get("transaction_id"))
        elif foreign is False and kind == "rho":
            rank = domestic_rank.get(str(related_id))
            if rank is None:
                output["needs_evidence"].append(item(fee, "needs_evidence", "Out-of-network status is needed to count Light Green free domestic withdrawals."))
            else:
                expected = Decimal("0.00") if rank <= 4 else Decimal("1.50")
                if charged > expected:
                    output["confirmed_candidates"].append(item(fee, "confirmed", "Charged domestic Rho-Bank fee exceeds Light Green monthly allowance/schedule.", expected, charged - expected))
                else:
                    output["notes"].append("Light Green domestic fee %s does not exceed the supplied monthly allowance/schedule." % fee.get("transaction_id"))
        else:
            output["needs_evidence"].append(item(fee, "needs_evidence", "Foreign status is unknown or fee is a third-party domestic charge."))

    output["notes"].append("Review only posted records. Confirm no matching rebate, refund, or credit already posted before any correction.")
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
