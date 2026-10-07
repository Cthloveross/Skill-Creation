#!/usr/bin/env python3
"""Calculate explicitly normalized ATM fee discrepancies; makes no bank actions."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
REQUIRED_PREREQUISITES = (
    "identity_verified", "authority_verified", "ownership_verified",
    "checking_account_verified", "account_status_verified",
    "product_eligibility_verified", "balance_or_credit_verified",
    "no_credit_in_last_14_days", "no_prior_credit_this_interaction",
)


def money(value, field):
    try:
        value = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if value < 0:
        # Normalized ledgers may retain debit signs; comparison values are absolute.
        value = -value
    return value


def parse_day(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD")


def amount_text(value):
    return format(value.quantize(CENT), ".2f")


def posted(item):
    return str(item.get("status", "posted")).lower() == "posted"


def fee_expected_light(withdrawal, domestic_index):
    location = str(withdrawal.get("location", "unknown")).lower()
    amount = money(withdrawal.get("amount"), "withdrawal.amount")
    if location == "foreign":
        if amount <= Decimal("100"):
            return Decimal("2.00"), "Light Green foreign tier: up to $100"
        if amount <= Decimal("300"):
            return Decimal("3.50"), "Light Green foreign tier: $100.01-$300"
        return Decimal("5.00"), "Light Green foreign tier: above $300"
    if location == "domestic" and withdrawal.get("out_of_network") is True:
        if domestic_index <= 4:
            return Decimal("0.00"), "Light Green domestic out-of-network withdrawal within first four"
        return Decimal("1.50"), "Light Green domestic out-of-network withdrawal after first four"
    return None, "location or out-of-network status is not explicit"


def main(payload):
    account = payload.get("account") or {}
    account_class = str(account.get("account_class", "")).strip().lower()
    if account_class not in ("bluest account", "light green account"):
        raise ValueError("account.account_class must be 'Bluest Account' or 'Light Green Account'")

    prerequisites = payload.get("prerequisites") or {}
    missing_prereqs = [key for key in REQUIRED_PREREQUISITES if prerequisites.get(key) is not True]
    withdrawals = payload.get("withdrawals") or []
    fees = payload.get("fees") or []
    rebates = payload.get("rebates") or []
    issues, discrepancies, unresolved = [], [], []

    normalized_withdrawals = {}
    for w in withdrawals:
        wid = str(w.get("id", "")).strip()
        if not wid:
            raise ValueError("every withdrawal needs a nonempty id")
        if wid in normalized_withdrawals:
            raise ValueError(f"duplicate withdrawal id: {wid}")
        w = dict(w)
        w["_day"] = parse_day(w.get("date"), "withdrawal.date")
        w["_amount"] = money(w.get("amount"), "withdrawal.amount")
        normalized_withdrawals[wid] = w

    fees_by_withdrawal = {}
    for f in fees:
        fid = str(f.get("id", "")).strip()
        if not fid:
            raise ValueError("every fee needs a nonempty id")
        f = dict(f)
        f["_day"] = parse_day(f.get("date"), "fee.date")
        f["_amount"] = money(f.get("amount"), "fee.amount")
        if f["_amount"] == 0:
            raise ValueError("fee.amount must be greater than zero")
        wid = str(f.get("withdrawal_id", "")).strip()
        if not wid or wid not in normalized_withdrawals:
            unresolved.append({"fee_id": fid, "reason": "fee has no explicit linked withdrawal"})
            continue
        fees_by_withdrawal.setdefault(wid, []).append(f)

    # One linked fee per withdrawal is expected for this calculation. Multiple fees
    # are left unresolved rather than assuming they should be summed or refunded.
    fee_signed_total = Decimal("0")
    fee_correction_count = 0

    if account_class == "light green account":
        domestic_counter = 0
        ordered = sorted(normalized_withdrawals.values(), key=lambda x: (x["_day"], str(x["id"])))
        for w in ordered:
            if not posted(w):
                continue
            location = str(w.get("location", "unknown")).lower()
            if location == "domestic" and w.get("out_of_network") is True:
                domestic_counter += 1
            if w["_amount"] > Decimal("150"):
                issues.append({"withdrawal_id": str(w["id"]), "reason": "withdrawal exceeds documented $150 daily ATM limit; investigate rather than infer a credit"})
            expected, rationale = fee_expected_light(w, domestic_counter)
            linked = fees_by_withdrawal.get(str(w["id"]), [])
            if expected is None:
                if linked:
                    unresolved.append({"withdrawal_id": str(w["id"]), "reason": rationale})
                continue
            if len(linked) != 1:
                unresolved.append({"withdrawal_id": str(w["id"]), "reason": "expected fee cannot be compared because linked fee count is not exactly one"})
                continue
            f = linked[0]
            if not posted(f):
                unresolved.append({"fee_id": str(f.get("id")), "reason": "fee is pending, not final"})
                continue
            if str(f.get("source", "unknown")).lower() != "rho_bank":
                unresolved.append({"fee_id": str(f.get("id")), "reason": "Light Green schedule applies to Rho-Bank fees; fee source is not confirmed as rho_bank"})
                continue
            signed = f["_amount"] - expected
            fee_signed_total += signed
            if signed != 0:
                fee_correction_count += 1
            discrepancies.append({
                "withdrawal_id": str(w["id"]), "fee_id": str(f.get("id")),
                "expected_fee": amount_text(expected), "actual_fee": amount_text(f["_amount"]),
                "signed_customer_correction": amount_text(signed), "basis": rationale,
            })

    else:  # Bluest
        cycle = payload.get("statement_cycle")
        cycle_ok = False
        if isinstance(cycle, dict) and cycle.get("start") and cycle.get("end"):
            start = parse_day(cycle["start"], "statement_cycle.start")
            end = parse_day(cycle["end"], "statement_cycle.end")
            if end < start:
                raise ValueError("statement_cycle.end must not precede start")
            cycle_ok = True
        else:
            unresolved.append({"reason": "Bluest rebate calculation requires actual statement-cycle start and end dates"})

        third_party_total = Decimal("0")
        rho_foreign_total = Decimal("0")
        for wid, linked in fees_by_withdrawal.items():
            if len(linked) != 1:
                unresolved.append({"withdrawal_id": wid, "reason": "multiple linked fees require manual reconciliation"})
                continue
            w, f = normalized_withdrawals[wid], linked[0]
            if not posted(w) or not posted(f):
                unresolved.append({"fee_id": str(f.get("id")), "reason": "withdrawal or fee is pending, not final"})
                continue
            source = str(f.get("source", "unknown")).lower()
            location = str(w.get("location", "unknown")).lower()
            if source == "third_party":
                third_party_total += f["_amount"]
            elif source == "rho_bank" and location == "foreign":
                rho_foreign_total += f["_amount"]
                fee_signed_total += f["_amount"]  # expected Rho-Bank foreign fee is zero
                fee_correction_count += 1
                discrepancies.append({
                    "withdrawal_id": wid, "fee_id": str(f.get("id")), "expected_fee": "0.00",
                    "actual_fee": amount_text(f["_amount"]), "signed_customer_correction": amount_text(f["_amount"]),
                    "basis": "Bluest has no Rho-Bank foreign ATM withdrawal fee",
                })
            elif source == "unknown":
                unresolved.append({"fee_id": str(f.get("id")), "reason": "fee source is unknown; cannot classify as Rho-Bank or eligible third-party fee"})

        if cycle_ok:
            applied_rebates = Decimal("0")
            for r in rebates:
                r = dict(r)
                day = parse_day(r.get("date"), "rebate.date")
                if posted(r) and str(r.get("purpose", "unknown")).lower() == "atm_fee" and start <= day <= end:
                    applied_rebates += money(r.get("amount"), "rebate.amount")
            expected_rebate = min(Decimal("50.00"), third_party_total)
            missing_rebate = expected_rebate - applied_rebates
            if missing_rebate < 0:
                missing_rebate = Decimal("0")
            if missing_rebate > 0:
                fee_signed_total += missing_rebate
                discrepancies.append({
                    "expected_rebate": amount_text(expected_rebate), "applied_rebate": amount_text(applied_rebates),
                    "signed_customer_correction": amount_text(missing_rebate),
                    "basis": "Bluest eligible third-party ATM-fee rebate, capped at $50 per statement cycle",
                })
            rebate_summary = {"eligible_third_party_fees": amount_text(third_party_total), "expected_rebate_capplied": amount_text(expected_rebate), "confirmed_rebates": amount_text(applied_rebates)}
        else:
            rebate_summary = None

    positive_net = max(Decimal("0"), fee_signed_total)
    # A rebate discrepancy has no fee_id; count it separately for credit-type majority.
    rebate_count = sum(1 for d in discrepancies if "expected_rebate" in d and Decimal(d["signed_customer_correction"]) > 0)
    suggested_type = None
    if positive_net > 0:
        if rebate_count > fee_correction_count:
            suggested_type = "rebate_credit"
        elif fee_correction_count > rebate_count:
            suggested_type = "fee_refund"
        else:
            unresolved.append({"reason": "credit type has no clear majority of supported corrections"})

    action_allowed = bool(positive_net > 0 and suggested_type and not unresolved and not missing_prereqs)
    output = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "discrepancies": discrepancies,
        "unresolved": unresolved,
        "issues_for_investigation": issues,
        "net_signed_customer_correction": amount_text(fee_signed_total),
        "potential_credit_amount": amount_text(positive_net),
        "suggested_credit_type": suggested_type,
        "missing_prerequisites": missing_prereqs,
        "credit_action_allowed": action_allowed,
        "note": "A true result is still a recommendation: executor must recheck transaction evidence and tool-call constraints immediately before any bank action.",
    }
    if account_class == "bluest account":
        output["bluest_rebate_summary"] = rebate_summary
    return output


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
