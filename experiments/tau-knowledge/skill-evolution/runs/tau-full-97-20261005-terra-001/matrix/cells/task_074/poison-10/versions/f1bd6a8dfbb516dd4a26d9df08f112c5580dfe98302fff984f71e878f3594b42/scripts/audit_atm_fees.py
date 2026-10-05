#!/usr/bin/env python3
"""Read ATM-audit JSON from stdin and emit deterministic audit JSON to stdout."""
import json, sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid monetary amount: %r" % (value,))
def fmt(value): return format(value.quantize(CENT), ".2f")
def parsed_date(value): return datetime.strptime(value, "%m/%d/%Y")
def same_month(date, month): return date[0:2] + "/" + date[6:10] == month

def expected_fee(cls, location, ordinal, withdrawal):
    if cls == "Purple": return Decimal("2.50") if location == "domestic" else Decimal("0")
    if cls == "Light Blue":
        return Decimal("0") if ordinal <= 2 else (Decimal("2.50") if location == "domestic" else Decimal("4.00"))
    if cls == "Dark Green":
        return max(withdrawal * Decimal(".01"), Decimal("1.50")) if location == "domestic" else min(withdrawal * Decimal(".025"), Decimal("6.00"))
    if cls == "Evergreen":
        return min(withdrawal * Decimal(".01"), Decimal("2.50")) if location == "domestic" else max(withdrawal * Decimal(".02"), Decimal("3.00"))
    return None

def main(data):
    month = data.get("month")
    if not isinstance(month, str) or len(month) != 7:
        raise ValueError("month must be MM/YYYY")
    accounts = {a.get("account_id"): a for a in data.get("accounts", [])}
    txs, tx_account = {}, {}
    for aid, rows in data.get("transactions", {}).items():
        for tx in rows:
            tid = tx.get("transaction_id")
            if tid:
                txs[tid], tx_account[tid] = tx, aid
    facts = {x.get("withdrawal_transaction_id"): x for x in data.get("withdrawal_facts", [])}
    links = defaultdict(list)
    for x in data.get("fee_links", []): links[x.get("withdrawal_transaction_id")].append(x)
    operator = defaultdict(list)
    for x in data.get("operator_fees", []): operator[x.get("withdrawal_transaction_id")].append(x)
    out = {"month": month, "discrepancies": [], "correct_items": [], "manual_review": [], "proposed_credit_by_account": {}}
    qualified = defaultdict(list)
    # Build qualified withdrawal population before calculating Light Blue allowance.
    for wid, fact in facts.items():
        tx = txs.get(wid); aid = tx_account.get(wid)
        if not tx or not aid or tx.get("type") != "atm_withdrawal" or tx.get("status") != "posted" or not same_month(tx.get("date", ""), month):
            continue
        if fact.get("out_of_network") is True and fact.get("location") in ("domestic", "foreign"):
            qualified[(aid, fact["location"])].append(wid)
    ordinal = {}
    for key, ids in qualified.items():
        for n, wid in enumerate(sorted(ids, key=lambda x: (parsed_date(txs[x]["date"]), x)), 1): ordinal[wid] = n
    corrections = defaultdict(list)
    for wid, fact in facts.items():
        tx = txs.get(wid); aid = tx_account.get(wid); acct = accounts.get(aid)
        if not tx or not aid or not acct:
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "withdrawal, account, or account ownership data missing"}); continue
        if tx.get("type") != "atm_withdrawal" or tx.get("status") != "posted" or not same_month(tx.get("date", ""), month):
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "withdrawal is not a posted ATM withdrawal in the requested month"}); continue
        if acct.get("account_type", "").lower() != "checking" or str(acct.get("status", "")).upper() != "OPEN":
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "account is not an open checking account"}); continue
        cls, loc = acct.get("account_class"), fact.get("location")
        if cls not in ("Purple", "Light Blue", "Dark Green", "Evergreen") or loc not in ("domestic", "foreign") or fact.get("out_of_network") is not True:
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "unsupported account class or unconfirmed out-of-network geography"}); continue
        try: expected = expected_fee(cls, loc, ordinal.get(wid, 0), money(tx.get("amount")))
        except ValueError as e: out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": str(e)}); continue
        rho_links = [x for x in links[wid] if x.get("fee_kind") == "rho_bank"]
        if len(rho_links) != 1:
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "need exactly one evidenced Rho-fee link (including a $0/no-fee statement fact)"}); continue
        fee_tx = txs.get(rho_links[0].get("fee_transaction_id"))
        if not fee_tx or tx_account.get(fee_tx.get("transaction_id")) != aid or fee_tx.get("status") != "posted":
            out["manual_review"].append({"withdrawal_transaction_id": wid, "reason": "linked Rho fee is missing, cross-account, or not posted"}); continue
        charged = money(fee_tx.get("amount")); over = charged - expected
        item = {"account_id": aid, "withdrawal_transaction_id": wid, "fee_transaction_id": fee_tx.get("transaction_id"), "charged_rho_fee": fmt(charged), "expected_rho_fee": fmt(expected), "location": loc, "allowance_ordinal": ordinal.get(wid)}
        if over > 0:
            item.update({"kind": "fee_refund", "correction_amount": fmt(over)})
            out["discrepancies"].append(item); corrections[aid].append(item)
        else: out["correct_items"].append(item)
    # Purple rebate review is account-wide and based only on explicitly supplied eligible operator facts.
    for aid, acct in accounts.items():
        if acct.get("account_class") != "Purple": continue
        eligible = Decimal("0")
        for wid, entries in operator.items():
            tx = txs.get(wid)
            if tx and tx_account.get(wid) == aid and tx.get("status") == "posted" and same_month(tx.get("date", ""), month):
                for e in entries:
                    if e.get("eligible_for_purple_rebate") is True: eligible += money(e.get("amount"))
        if eligible == 0: continue
        posted = sum((money(t.get("amount")) for t in data.get("transactions", {}).get(aid, []) if t.get("status") == "posted" and t.get("type") == "rebate_credit" and same_month(t.get("date", ""), month)), Decimal("0"))
        due = min(eligible, Decimal("30.00")); short = due - posted
        if short > 0:
            item = {"account_id": aid, "kind": "rebate_credit", "eligible_operator_fees": fmt(eligible), "posted_rebates": fmt(posted), "monthly_cap": "30.00", "correction_amount": fmt(short)}
            out["discrepancies"].append(item); corrections[aid].append(item)
    for aid, items in corrections.items():
        total = sum((Decimal(x["correction_amount"]) for x in items), Decimal("0"))
        kinds = defaultdict(int)
        for x in items: kinds[x["kind"]] += 1
        ranked = sorted(kinds.items(), key=lambda x: x[1], reverse=True)
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            out["proposed_credit_by_account"][aid] = {"amount": fmt(total), "credit_type": ranked[0][0], "correction_event_count": len(items), "requires_precredit_checks": True}
        else:
            out["manual_review"].append({"account_id": aid, "reason": "fee-refund and rebate-credit correction counts tie; credit type has no majority"})
    return out

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
