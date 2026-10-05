#!/usr/bin/env python3
"""Deterministically calculate documented ATM bank-fee expectations.

Read one JSON object from stdin and write one JSON result to stdout. This helper
requires already-classified ATM events; it deliberately does not infer network,
country, fee ownership, eligibility, membership, or transaction matching.
"""
import json
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

CENT = Decimal("0.01")
PRODUCTS = {"Purple", "Light Blue", "Dark Green", "Evergreen"}


def money(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("monetary values must be decimal-compatible")
    if result < 0:
        raise ValueError("monetary values must not be negative")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def expected_fee(product, locale, cash, ordinal):
    """Return expected Rho fee for a known qualifying out-of-network event."""
    if product == "Purple":
        return Decimal("2.50") if locale == "domestic" else Decimal("0.00")
    if product == "Light Blue":
        if ordinal <= 2:
            return Decimal("0.00")
        return Decimal("2.50") if locale == "domestic" else Decimal("4.00")
    if product == "Dark Green":
        if locale == "domestic":
            return max(cash * Decimal("0.01"), Decimal("1.50")).quantize(CENT, rounding=ROUND_HALF_UP)
        return min(cash * Decimal("0.025"), Decimal("6.00")).quantize(CENT, rounding=ROUND_HALF_UP)
    if product == "Evergreen":
        if locale == "domestic":
            return min(cash * Decimal("0.01"), Decimal("2.50")).quantize(CENT, rounding=ROUND_HALF_UP)
        return max(cash * Decimal("0.02"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
    raise ValueError("unsupported product")


def main(payload):
    period = payload.get("period")
    try:
        datetime.strptime(period, "%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("period must be YYYY-MM")

    output = {
        "period": period,
        "accounts": [],
        "credit_recommendations": [],
        "global_notes": [
            "Recommendations require live verification, documented transaction matching, duplicate-credit/cooldown checks, and an authorized banking action.",
            "ATM operator surcharges and Rho bank fees must remain separate.",
            "Rho Bank Plus reimbursement is not calculated here because active coverage and interaction with other benefits require documentary confirmation."
        ]
    }

    for account in payload.get("accounts", []):
        account_id = account.get("account_id")
        product = account.get("product")
        account_type = str(account.get("account_type", "")).lower()
        status = str(account.get("status", "")).lower()
        result = {
            "account_id": account_id,
            "product": product,
            "events": [],
            "fee_refund_total": "0.00",
            "purple_rebate": None,
            "unsupported_or_incomplete": []
        }
        if product not in PRODUCTS:
            result["unsupported_or_incomplete"].append("Unsupported or unidentified account product.")
        if account_type != "checking":
            result["unsupported_or_incomplete"].append("Credits are only supported for checking accounts.")
        if status != "open":
            result["unsupported_or_incomplete"].append("Account is not open; do not recommend a checking credit.")

        events = []
        for index, raw in enumerate(account.get("events", [])):
            event = dict(raw)
            event["_index"] = index
            try:
                event["_date"] = parse_date(event.get("date"))
            except (TypeError, ValueError):
                event["_date"] = None
            events.append(event)
        events.sort(key=lambda e: (e["_date"] is None, e["_date"], e["_index"]))

        allowance_count = defaultdict(int)
        refund_total = Decimal("0.00")
        purple_eligible_total = Decimal("0.00")
        purple_credited_total = Decimal("0.00")

        for event in events:
            item = {k: v for k, v in event.items() if not k.startswith("_")}
            issues = []
            date = event["_date"]
            if date is None or event.get("date", "")[:7] != period:
                issues.append("Event date is invalid or outside the review period.")
            network = event.get("network")
            locale = event.get("locale")
            if network not in ("out_of_network", "in_network", "unknown"):
                issues.append("network must be out_of_network, in_network, or unknown.")
            if locale not in ("domestic", "foreign", "unknown"):
                issues.append("locale must be domestic, foreign, or unknown.")
            try:
                cash = money(event.get("cash_amount"))
                if cash is None or cash == 0:
                    issues.append("cash_amount must be a positive withdrawal amount.")
            except ValueError as error:
                cash = None
                issues.append(str(error))
            try:
                observed = money(event.get("bank_fee"))
            except ValueError as error:
                observed = None
                issues.append(str(error))

            item["expected_bank_fee"] = None
            item["observed_bank_fee"] = None if observed is None else fmt(observed)
            item["difference"] = None
            item["finding"] = "incomplete"

            if not issues and network == "in_network":
                item["expected_bank_fee"] = "0.00"
                if observed is None:
                    item["finding"] = "No explicitly matched bank-fee line supplied."
                else:
                    diff = observed
                    item["difference"] = fmt(diff)
                    item["finding"] = "potential_overcharge" if diff > 0 else "matches_expected"
                    refund_total += max(diff, Decimal("0.00"))
            elif not issues and network == "out_of_network" and locale in ("domestic", "foreign"):
                allowance_count[locale] += 1
                expected = expected_fee(product, locale, cash, allowance_count[locale])
                item["qualifying_withdrawal_number"] = allowance_count[locale]
                item["expected_bank_fee"] = fmt(expected)
                if observed is None:
                    item["finding"] = "No explicitly matched bank-fee line supplied."
                else:
                    diff = (observed - expected).quantize(CENT, rounding=ROUND_HALF_UP)
                    item["difference"] = fmt(diff)
                    if diff > 0:
                        item["finding"] = "potential_overcharge"
                        refund_total += diff
                    elif diff < 0:
                        item["finding"] = "charged_less_than_schedule"
                    else:
                        item["finding"] = "matches_expected"
            else:
                if network == "unknown" or locale == "unknown":
                    issues.append("Network or domestic/foreign classification is unresolved.")

            # Purple operator-fee rebates are kept distinct from fee-refund math.
            if product == "Purple":
                try:
                    eligible_operator_fee = money(event.get("eligible_operator_fee")) or Decimal("0.00")
                    rebate_credited = money(event.get("rebate_credited")) or Decimal("0.00")
                    if eligible_operator_fee > 0:
                        purple_eligible_total += eligible_operator_fee
                    if rebate_credited > 0:
                        purple_credited_total += rebate_credited
                except ValueError as error:
                    issues.append("Purple rebate field: " + str(error))
            item["issues"] = issues
            result["events"].append(item)

        result["fee_refund_total"] = fmt(refund_total)
        if product == "Purple":
            capped_expected = min(purple_eligible_total, Decimal("30.00"))
            potential_missing = max(capped_expected - purple_credited_total, Decimal("0.00"))
            result["purple_rebate"] = {
                "eligible_operator_fee_total": fmt(purple_eligible_total),
                "rebates_credited_total": fmt(purple_credited_total),
                "monthly_cap": "30.00",
                "maximum_rebate_under_cap": fmt(capped_expected),
                "potential_missing_rebate": fmt(potential_missing),
                "warning": "This is not a credit recommendation until the operator fees, posting status, eligibility, and rebate matching are documented."
            }

        if not result["unsupported_or_incomplete"] and refund_total > 0:
            output["credit_recommendations"].append({
                "account_id": account_id,
                "amount": fmt(refund_total),
                "credit_type": "fee_refund",
                "basis": "Sum of explicitly supplied matched Rho bank-fee overcharges only; review each source transaction before action."
            })
        output["accounts"].append(result)
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
