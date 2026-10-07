#!/usr/bin/env python3
"""Deterministically audit explicitly evidenced ATM-fee facts from JSON stdin."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
SUPPORTED = {"Purple", "Light Blue", "Dark Green", "Evergreen"}


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid monetary amount: %r" % (value,))


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def in_month(date, month):
    try:
        return datetime.strptime(date, "%m/%d/%Y").strftime("%m/%Y") == month
    except (TypeError, ValueError):
        return False


def date_key(tx):
    return datetime.strptime(tx["date"], "%m/%d/%Y")


def expected_fee(account_class, location, ordinal, withdrawal_amount):
    if account_class == "Purple":
        return Decimal("2.50") if location == "domestic" else Decimal("0")
    if account_class == "Light Blue":
        if ordinal is None:
            raise ValueError("Light Blue fee needs an evidenced allowance ordinal")
        if ordinal <= 2:
            return Decimal("0")
        return Decimal("2.50") if location == "domestic" else Decimal("4.00")
    if account_class == "Dark Green":
        if location == "domestic":
            return max(withdrawal_amount * Decimal("0.01"), Decimal("1.50"))
        return min(withdrawal_amount * Decimal("0.025"), Decimal("6.00"))
    if account_class == "Evergreen":
        if location == "domestic":
            return min(withdrawal_amount * Decimal("0.01"), Decimal("2.50"))
        return max(withdrawal_amount * Decimal("0.02"), Decimal("3.00"))
    raise ValueError("unsupported account class")


def valid_account(account):
    return (account and account.get("account_type", "").lower() == "checking"
            and str(account.get("status", "")).upper() == "OPEN"
            and account.get("account_class") in SUPPORTED)


def main(data):
    month = data.get("month")
    try:
        datetime.strptime(month, "%m/%Y")
    except (TypeError, ValueError):
        raise ValueError("month must be MM/YYYY")

    accounts = {a.get("account_id"): a for a in data.get("accounts", []) if a.get("account_id")}
    txs, tx_account = {}, {}
    for account_id, rows in data.get("transactions", {}).items():
        if not isinstance(rows, list):
            raise ValueError("transactions values must be lists")
        for tx in rows:
            transaction_id = tx.get("transaction_id")
            if transaction_id:
                txs[transaction_id] = tx
                tx_account[transaction_id] = account_id

    facts = {x.get("withdrawal_transaction_id"): x for x in data.get("withdrawal_facts", [])
             if x.get("withdrawal_transaction_id")}
    links = defaultdict(list)
    for link in data.get("fee_links", []):
        if link.get("withdrawal_transaction_id"):
            links[link["withdrawal_transaction_id"]].append(link)

    out = {"month": month, "discrepancies": [], "correct_items": [],
           "manual_review": [], "proposed_credit_by_account": {}}
    corrections = defaultdict(list)
    audited_fee_ids = set()

    # Count all known, posted, qualified withdrawals before evaluating Light Blue.
    qualified = defaultdict(list)
    for withdrawal_id, fact in facts.items():
        tx = txs.get(withdrawal_id)
        account_id = tx_account.get(withdrawal_id)
        if (tx and tx.get("type") == "atm_withdrawal" and tx.get("status") == "posted"
                and in_month(tx.get("date"), month) and fact.get("out_of_network") is True
                and fact.get("location") in ("domestic", "foreign")):
            qualified[(account_id, fact["location"])].append(withdrawal_id)
    ordinals = {}
    for key, ids in qualified.items():
        try:
            ordered = sorted(ids, key=lambda wid: (date_key(txs[wid]), wid))
        except (KeyError, ValueError):
            continue
        for ordinal, withdrawal_id in enumerate(ordered, 1):
            ordinals[withdrawal_id] = ordinal

    def record_item(account_id, fee_tx, location, expected, source, withdrawal_id=None, ordinal=None):
        charged = money(fee_tx.get("amount"))
        item = {"account_id": account_id, "fee_transaction_id": fee_tx.get("transaction_id"),
                "charged_rho_fee": fmt(charged), "expected_rho_fee": fmt(expected),
                "location": location, "evidence_path": source}
        if withdrawal_id is not None:
            item["withdrawal_transaction_id"] = withdrawal_id
        if ordinal is not None:
            item["allowance_ordinal"] = ordinal
        overcharge = charged - expected
        if overcharge > 0:
            item.update({"kind": "fee_refund", "correction_amount": fmt(overcharge)})
            out["discrepancies"].append(item)
            corrections[account_id].append(item)
        else:
            out["correct_items"].append(item)
        audited_fee_ids.add(fee_tx.get("transaction_id"))

    # Linked evidence path. A link must be supplied; dates alone are never a link.
    for withdrawal_id, fact in facts.items():
        tx = txs.get(withdrawal_id)
        account_id = tx_account.get(withdrawal_id)
        account = accounts.get(account_id)
        if not tx or not account:
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "withdrawal or account data missing"})
            continue
        if (tx.get("type") != "atm_withdrawal" or tx.get("status") != "posted"
                or not in_month(tx.get("date"), month)):
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "not a posted ATM withdrawal in requested month"})
            continue
        if not valid_account(account):
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "account is not a supported open checking account"})
            continue
        location = fact.get("location")
        if fact.get("out_of_network") is not True or location not in ("domestic", "foreign"):
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "unconfirmed out-of-network geography"})
            continue
        rho_links = [link for link in links[withdrawal_id] if link.get("fee_kind") == "rho_bank"]
        if not rho_links:
            continue  # May be assessed through explicit standalone evidence instead.
        if len(rho_links) != 1:
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "need exactly one actual Rho-fee linkage"})
            continue
        fee_tx = txs.get(rho_links[0].get("fee_transaction_id"))
        if (not fee_tx or tx_account.get(fee_tx.get("transaction_id")) != account_id
                or fee_tx.get("status") != "posted"):
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id,
                                         "reason": "linked Rho fee missing, cross-account, or not posted"})
            continue
        try:
            expected = expected_fee(account["account_class"], location, ordinals.get(withdrawal_id),
                                    money(tx.get("amount")))
            record_item(account_id, fee_tx, location, expected, "linked", withdrawal_id,
                        ordinals.get(withdrawal_id))
        except ValueError as exc:
            out["manual_review"].append({"withdrawal_transaction_id": withdrawal_id, "reason": str(exc)})

    # Direct, statement-supported fee evidence. It does not manufacture a withdrawal link.
    for fact in data.get("explicit_fee_facts", []):
        fee_id = fact.get("fee_transaction_id")
        fee_tx = txs.get(fee_id)
        account_id = tx_account.get(fee_id)
        account = accounts.get(account_id)
        if fee_id in audited_fee_ids:
            continue
        if not fee_tx or not account:
            out["manual_review"].append({"fee_transaction_id": fee_id,
                                         "reason": "standalone fee or account data missing"})
            continue
        if fee_tx.get("status") != "posted" or not in_month(fee_tx.get("date"), month):
            out["manual_review"].append({"fee_transaction_id": fee_id,
                                         "reason": "standalone fee is not posted in requested month"})
            continue
        if not valid_account(account):
            out["manual_review"].append({"fee_transaction_id": fee_id,
                                         "reason": "account is not a supported open checking account"})
            continue
        location = fact.get("location")
        if (fact.get("explicitly_identified_as_rho_fee") is not True
                or fact.get("out_of_network") is not True
                or location not in ("domestic", "foreign")):
            out["manual_review"].append({"fee_transaction_id": fee_id,
                                         "reason": "standalone fee lacks explicit Rho-fee classification or geography"})
            continue
        ordinal = fact.get("allowance_ordinal")
        if account.get("account_class") == "Light Blue" and (not isinstance(ordinal, int) or ordinal < 1):
            out["manual_review"].append({"fee_transaction_id": fee_id,
                                         "reason": "standalone Light Blue fee needs evidenced allowance ordinal"})
            continue
        try:
            # Purple's foreign fee is zero, so no withdrawal amount is needed for that calculation.
            withdrawal_amount = money(fact.get("withdrawal_amount", "0"))
            if account.get("account_class") != "Purple" and withdrawal_amount <= 0:
                raise ValueError("standalone fee needs explicit positive withdrawal amount")
            expected = expected_fee(account["account_class"], location, ordinal, withdrawal_amount)
            record_item(account_id, fee_tx, location, expected, "explicit_standalone", ordinal=ordinal)
        except ValueError as exc:
            out["manual_review"].append({"fee_transaction_id": fee_id, "reason": str(exc)})

    # Purple rebates apply only to separately evidenced eligible operator surcharges.
    operator_fees = defaultdict(list)
    for entry in data.get("operator_fees", []):
        operator_fees[entry.get("withdrawal_transaction_id")].append(entry)
    for account_id, account in accounts.items():
        if account.get("account_class") != "Purple" or not valid_account(account):
            continue
        eligible = Decimal("0")
        for withdrawal_id, entries in operator_fees.items():
            withdrawal = txs.get(withdrawal_id)
            if (withdrawal and tx_account.get(withdrawal_id) == account_id
                    and withdrawal.get("status") == "posted" and in_month(withdrawal.get("date"), month)):
                for entry in entries:
                    if entry.get("eligible_for_purple_rebate") is True:
                        eligible += money(entry.get("amount"))
        if not eligible:
            continue
        posted = sum((money(tx.get("amount")) for tx in data.get("transactions", {}).get(account_id, [])
                      if tx.get("status") == "posted" and tx.get("type") == "rebate_credit"
                      and in_month(tx.get("date"), month)), Decimal("0"))
        shortfall = min(eligible, Decimal("30.00")) - posted
        if shortfall > 0:
            item = {"account_id": account_id, "kind": "rebate_credit",
                    "eligible_operator_fees": fmt(eligible), "posted_rebates": fmt(posted),
                    "monthly_cap": "30.00", "correction_amount": fmt(shortfall)}
            out["discrepancies"].append(item)
            corrections[account_id].append(item)

    for account_id, items in corrections.items():
        total = sum((Decimal(item["correction_amount"]) for item in items), Decimal("0"))
        counts = defaultdict(int)
        for item in items:
            counts[item["kind"]] += 1
        ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            out["proposed_credit_by_account"][account_id] = {
                "amount": fmt(total), "credit_type": ranked[0][0],
                "correction_event_count": len(items), "requires_precredit_checks": True}
        else:
            out["manual_review"].append({"account_id": account_id,
                                         "reason": "correction types tie; operational credit type required"})
    return out


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
