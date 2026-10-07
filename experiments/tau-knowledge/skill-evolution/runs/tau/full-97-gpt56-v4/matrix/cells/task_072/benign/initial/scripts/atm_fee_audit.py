#!/usr/bin/env python3
"""Deterministically audit explicitly normalized ATM events.

Input JSON schema:
  account_class: "Bluest Account" or "Light Green Account"
  bluest_benefits_active: boolean (required to assess Bluest benefit pricing)
  events: list of objects with date (MM/DD/YYYY or ISO date), location
          (domestic_out_of_network|foreign|unknown), withdrawal_amount,
          rho_fee_charged, third_party_fee, rebate_credits (decimal strings),
          and status (posted|pending).
Output JSON gives supported, positive correction candidates only. The caller is
responsible for transaction matching, the actual statement-cycle definition, and
bank-tool authorization.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0.00")
CAP = Decimal("50.00")


def money(value, field, index):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"events[{index}].{field} must be a decimal")
    if result < 0:
        raise ValueError(f"events[{index}].{field} must be nonnegative")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parsed_date(value, index):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"events[{index}].date must be MM/DD/YYYY or YYYY-MM-DD")


def fmt(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def light_green_fee(location, amount, domestic_number):
    if location == "foreign":
        if amount <= Decimal("100.00"):
            return Decimal("2.00"), domestic_number
        if amount <= Decimal("300.00"):
            return Decimal("3.50"), domestic_number
        return Decimal("5.00"), domestic_number
    if location == "domestic_out_of_network":
        domestic_number += 1
        return (ZERO if domestic_number <= 4 else Decimal("1.50")), domestic_number
    return None, domestic_number


def audit(payload):
    account_class = payload.get("account_class")
    if account_class not in ("Bluest Account", "Light Green Account"):
        raise ValueError("account_class must be 'Bluest Account' or 'Light Green Account'")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    normalized = []
    for i, raw in enumerate(events):
        if not isinstance(raw, dict):
            raise ValueError(f"events[{i}] must be an object")
        location = raw.get("location")
        if location not in ("domestic_out_of_network", "foreign", "unknown"):
            raise ValueError(f"events[{i}].location is invalid")
        status = raw.get("status")
        if status not in ("posted", "pending"):
            raise ValueError(f"events[{i}].status must be posted or pending")
        normalized.append({
            "index": i,
            "date": parsed_date(raw.get("date"), i),
            "location": location,
            "status": status,
            "withdrawal_amount": money(raw.get("withdrawal_amount", "0"), "withdrawal_amount", i),
            "rho_fee_charged": money(raw.get("rho_fee_charged", "0"), "rho_fee_charged", i),
            "third_party_fee": money(raw.get("third_party_fee", "0"), "third_party_fee", i),
            "rebate_credits": money(raw.get("rebate_credits", "0"), "rebate_credits", i),
        })
    normalized.sort(key=lambda e: (e["date"], e["index"]))

    benefits_active = payload.get("bluest_benefits_active")
    if account_class == "Bluest Account" and not isinstance(benefits_active, bool):
        raise ValueError("bluest_benefits_active must be boolean for Bluest Account")

    domestic_by_month = {}
    rebate_used_by_month = {}
    rows, issues = [], []
    fee_refund_total = ZERO
    missing_rebate_total = ZERO

    for event in normalized:
        key = event["date"].strftime("%Y-%m")
        finding = {
            "input_index": event["index"],
            "date": event["date"].isoformat(),
            "status": event["status"],
            "location": event["location"],
            "expected_rho_fee": None,
            "fee_refund_candidate": "0.00",
            "missing_rebate_candidate": "0.00",
            "notes": [],
        }
        if event["status"] != "posted":
            finding["notes"].append("Pending event excluded from final correction calculation.")
            rows.append(finding)
            continue
        if event["location"] == "unknown":
            msg = f"Event {event['index']}: ATM location/network classification is unknown."
            issues.append(msg)
            finding["notes"].append(msg)
            rows.append(finding)
            continue

        expected = None
        if account_class == "Light Green Account":
            count = domestic_by_month.get(key, 0)
            expected, count = light_green_fee(event["location"], event["withdrawal_amount"], count)
            domestic_by_month[key] = count
        elif not benefits_active:
            msg = f"Event {event['index']}: Bluest historical benefit eligibility is not established."
            issues.append(msg)
            finding["notes"].append(msg)
        elif event["location"] == "foreign":
            expected = ZERO
        else:
            expected = Decimal("2.00")

        if expected is not None:
            finding["expected_rho_fee"] = fmt(expected)
            correction = max(ZERO, event["rho_fee_charged"] - expected)
            fee_refund_total += correction
            finding["fee_refund_candidate"] = fmt(correction)

        # Only Bluest has the supplied monthly ATM-fee rebate rule. The caller
        # must enter only a known eligible third-party fee in third_party_fee.
        if account_class == "Bluest Account" and benefits_active:
            prior = rebate_used_by_month.get(key, ZERO)
            eligible = min(event["third_party_fee"], max(ZERO, CAP - prior))
            applied = min(event["rebate_credits"], eligible)
            missing = max(ZERO, eligible - applied)
            # Credits actually posted consume the cap; excess input is noted,
            # rather than being used to create another correction.
            rebate_used_by_month[key] = min(CAP, prior + event["rebate_credits"])
            missing_rebate_total += missing
            finding["missing_rebate_candidate"] = fmt(missing)
            if event["third_party_fee"] > ZERO:
                finding["notes"].append("Rebate candidate is capped by the $50 monthly Bluest limit.")
        rows.append(finding)

    result = {
        "account_class": account_class,
        "findings": rows,
        "fee_refund_total": fmt(fee_refund_total),
        "missing_rebate_total": fmt(missing_rebate_total),
        "total_positive_correction_candidate": fmt(fee_refund_total + missing_rebate_total),
        "insufficient_evidence": issues,
        "warning": "Candidates require transaction matching, identity verification, checking-account confirmation, and a human/tool-authorized credit decision.",
    }
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(audit(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
