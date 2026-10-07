#!/usr/bin/env python3
"""Audit documented card-reward calculations.

Reads JSON from stdin.  See SKILL.md for schema.  Emits a JSON result to stdout.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or invalid")
    text = str(value).strip().replace(",", "").replace("$", "")
    text = text.replace("points", "").replace("point", "").strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc


def whole_points(value):
    if value < 0:
        raise ValueError("negative amounts are unsupported")
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def expected_points(txn, extra_rates):
    card = str(txn.get("credit_card_type", "")).strip()
    amount = decimal_value(txn.get("transaction_amount"), "transaction_amount")
    category = str(txn.get("category", "")).strip().casefold()

    if card == "Crypto-Cash Back":
        return whole_points(amount * Decimal("2")), "Crypto-Cash Back: 2.0% eligible-spend rate"
    if card == "EcoCard":
        multiplier = Decimal("5") if category == "green" else Decimal("1")
        label = "EcoCard: 5 points per green-purchase dollar" if multiplier == 5 else "EcoCard: 1 point per other-purchase dollar"
        return whole_points(amount * multiplier), label
    if card in extra_rates:
        rate = decimal_value(extra_rates[card], f"rate_points_per_dollar[{card}]")
        if rate < 0:
            raise ValueError(f"rate_points_per_dollar[{card}] cannot be negative")
        return whole_points(amount * rate), "explicit documented points-per-dollar rate"
    return None, "no documented card-specific rate supplied"


def audit_transaction(txn, extra_rates):
    txn_id = str(txn.get("transaction_id", "")).strip()
    if not txn_id:
        raise ValueError("transaction_id is required")
    status = str(txn.get("status", "")).strip()
    result = {
        "transaction_id": txn_id,
        "card_type": str(txn.get("credit_card_type", "")).strip(),
        "status": "",
    }
    if status != "COMPLETED":
        result.update({"status": "skipped", "reason": "transaction is not completed"})
        return result

    expected, basis = expected_points(txn, extra_rates)
    if expected is None:
        result.update({"status": "not_assessed", "reason": basis})
        return result

    recorded = whole_points(decimal_value(txn.get("rewards_earned"), "rewards_earned"))
    difference = expected - recorded
    result.update({
        "status": "assessed",
        "recorded_points": recorded,
        "expected_points": expected,
        "difference_points": difference,
        "difference_cash_value": format(Decimal(difference) / Decimal("100"), ".2f"),
        "calculation_basis": basis,
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("transactions must be a list")
        extra_rates = payload.get("rate_points_per_dollar", {})
        if not isinstance(extra_rates, dict):
            raise ValueError("rate_points_per_dollar must be an object")
        selected = payload.get("transaction_ids")
        if selected is not None:
            if not isinstance(selected, list) or not all(isinstance(x, str) and x for x in selected):
                raise ValueError("transaction_ids must be a list of nonempty strings")
            if len(set(selected)) != len(selected):
                raise ValueError("transaction_ids contains duplicates")
            selected = set(selected)

        seen = set()
        audits = []
        for txn in payload["transactions"]:
            if not isinstance(txn, dict):
                raise ValueError("each transaction must be an object")
            txn_id = str(txn.get("transaction_id", "")).strip()
            if selected is not None and txn_id not in selected:
                continue
            if txn_id in seen:
                raise ValueError(f"duplicate transaction_id: {txn_id}")
            seen.add(txn_id)
            audits.append(audit_transaction(txn, extra_rates))
        if selected is not None:
            missing = sorted(selected - seen)
            if missing:
                raise ValueError("selected transaction IDs not found: " + ", ".join(missing))

        assessed = [a for a in audits if a["status"] == "assessed"]
        output = {
            "audits": audits,
            "summary": {
                "transactions_considered": len(audits),
                "assessed": len(assessed),
                "not_assessed": sum(a["status"] == "not_assessed" for a in audits),
                "skipped": sum(a["status"] == "skipped" for a in audits),
                "discrepancies": sum(a.get("difference_points", 0) != 0 for a in assessed),
            },
        }
        print(json.dumps(output, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
