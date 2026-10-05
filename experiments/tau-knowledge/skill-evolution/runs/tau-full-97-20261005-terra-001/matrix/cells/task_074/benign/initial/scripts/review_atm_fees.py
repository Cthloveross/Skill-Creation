#!/usr/bin/env python3
"""Calculate supported ATM fee corrections from reviewed transaction facts.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
script is deliberately a calculator: it never calls banking tools and never
infers ATM geography, network status, fee ownership, or rebate eligibility.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
CAP_PURPLE_REBATE = Decimal("30.00")


def money(value):
    try:
        return abs(Decimal(str(value).replace("$", "").replace(",", "").strip())).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("invalid monetary amount: %r" % (value,))


def money_text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    text = str(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid date (use YYYY-MM-DD or MM/DD/YYYY): %r" % value)


def in_month(line, month):
    return parse_date(line["date"]).strftime("%Y-%m") == month


def posted(line):
    return str(line.get("status", "")).lower() == "posted"


def normalized_class(value):
    return " ".join(str(value).strip().lower().split())


def product_for(account_class):
    value = normalized_class(account_class)
    products = {
        "purple account": "purple",
        "light blue account": "light_blue",
        "dark green account": "dark_green",
        "evergreen account": "evergreen",
    }
    return products.get(value)


def percentage(amount, rate):
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def expected_rho_fee(product, event, light_blue_number=None):
    geography = event.get("geography")
    out_network = event.get("out_of_network")
    amount = money(event["withdrawal_amount"])

    if geography not in ("domestic", "foreign"):
        raise ValueError("geography must be domestic or foreign")

    if product == "purple":
        if geography == "foreign":
            return ZERO
        if not isinstance(out_network, bool):
            raise ValueError("domestic Purple withdrawal needs boolean out_of_network")
        return Decimal("2.50") if out_network else ZERO

    if product == "light_blue":
        if not isinstance(out_network, bool):
            raise ValueError("Light Blue withdrawal needs boolean out_of_network")
        if not out_network:
            return ZERO
        if light_blue_number is None:
            raise ValueError("Light Blue out-of-network withdrawal order is unavailable")
        return ZERO if light_blue_number <= 2 else Decimal("2.50")

    if product == "dark_green":
        if geography == "foreign":
            return min(percentage(amount, Decimal("0.025")), Decimal("6.00"))
        if not isinstance(out_network, bool):
            raise ValueError("domestic Dark Green withdrawal needs boolean out_of_network")
        return max(percentage(amount, Decimal("0.01")), Decimal("1.50")) if out_network else ZERO

    if product == "evergreen":
        if geography == "foreign":
            return max(percentage(amount, Decimal("0.02")), Decimal("3.00"))
        if not isinstance(out_network, bool):
            raise ValueError("domestic Evergreen withdrawal needs boolean out_of_network")
        return min(percentage(amount, Decimal("0.01")), Decimal("2.50")) if out_network else ZERO

    raise ValueError("unsupported account class")


def scoped_posted(lines, review_month, warnings, label, event_id):
    result = []
    for line in lines:
        try:
            scoped = in_month(line, review_month)
        except (KeyError, ValueError) as exc:
            warnings.append("%s %s has invalid date: %s" % (event_id, label, exc))
            continue
        if scoped and not posted(line):
            warnings.append("%s %s is not posted and was excluded" % (event_id, label))
        elif scoped and posted(line):
            result.append(line)
    return result


def main(payload):
    review_month = payload.get("review_month")
    try:
        datetime.strptime(str(review_month), "%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("review_month must be YYYY-MM")

    accounts = payload.get("accounts")
    events = payload.get("events")
    if not isinstance(accounts, list) or not isinstance(events, list):
        raise ValueError("accounts and events must be arrays")

    history_complete = payload.get("history_complete_by_account", {})
    if not isinstance(history_complete, dict):
        raise ValueError("history_complete_by_account must be an object")

    account_map = {}
    for account in accounts:
        account_id = account.get("account_id")
        if not account_id:
            raise ValueError("each account needs account_id")
        account_map[str(account_id)] = account

    known_ids = set()
    supplied_history = payload.get("transactions_by_account", {})
    if supplied_history:
        if not isinstance(supplied_history, dict):
            raise ValueError("transactions_by_account must be an object")
        for lines in supplied_history.values():
            for line in lines:
                if line.get("transaction_id"):
                    known_ids.add(str(line["transaction_id"]))

    events_by_account = {account_id: [] for account_id in account_map}
    global_warnings = []
    for event in events:
        event_id = event.get("event_id")
        account_id = str(event.get("account_id", ""))
        if not event_id:
            global_warnings.append("An event has no event_id")
            continue
        if account_id not in account_map:
            global_warnings.append("%s references an account not supplied in accounts" % event_id)
            continue
        events_by_account[account_id].append(event)

    unclassified = payload.get("unclassified_atm_fee_lines", [])
    if not isinstance(unclassified, list):
        raise ValueError("unclassified_atm_fee_lines must be an array")

    results = []
    for account_id, account in account_map.items():
        warnings = []
        blockers = []
        fee_items = []
        rebate_items = []
        product = product_for(account.get("account_class", ""))
        if str(account.get("account_type", "")).lower() != "checking":
            blockers.append("Account is not a checking account and cannot receive a credit")
        if product is None:
            blockers.append("Unsupported or unrecognized account_class")
        if history_complete.get(account_id) is not True:
            blockers.append("Complete transaction-history review was not confirmed")

        account_events = events_by_account[account_id]
        for line in unclassified:
            if str(line.get("account_id", "")) == account_id:
                blockers.append("An ATM-related fee line remains unclassified")
                break

        # Light Blue's free allowance is based on all qualifying withdrawals in
        # the withdrawal month, not merely the fee lines that posted that month.
        light_blue_order = {}
        if product == "light_blue":
            qualifying = []
            for event in account_events:
                try:
                    if (event.get("out_of_network") is True and
                            parse_date(event["withdrawal_date"]).strftime("%Y-%m") == review_month):
                        qualifying.append(event)
                except (KeyError, ValueError) as exc:
                    blockers.append("%s has invalid withdrawal_date: %s" % (event.get("event_id", "event"), exc))
            qualifying.sort(key=lambda item: (parse_date(item["withdrawal_date"]), str(item.get("event_id"))))
            light_blue_order = {str(item.get("event_id")): index + 1 for index, item in enumerate(qualifying)}

        purple_rebate_candidates = []
        event_records = []
        for event in account_events:
            event_id = str(event.get("event_id"))
            try:
                parse_date(event["withdrawal_date"])
                money(event["withdrawal_amount"])
            except (KeyError, ValueError) as exc:
                blockers.append("%s lacks usable withdrawal facts: %s" % (event_id, exc))
                continue

            rho_lines = event.get("rho_fee_lines", [])
            operator_lines = event.get("operator_fee_lines", [])
            rebate_lines = event.get("rebate_lines", [])
            if not all(isinstance(x, list) for x in (rho_lines, operator_lines, rebate_lines)):
                blockers.append("%s fee-line fields must be arrays" % event_id)
                continue

            for line in rho_lines + operator_lines + rebate_lines:
                txid = line.get("transaction_id")
                if known_ids and (not txid or str(txid) not in known_ids):
                    blockers.append("%s references a transaction not present in supplied history" % event_id)

            scope_rho = scoped_posted(rho_lines, review_month, warnings, "Rho fee", event_id)
            actual_rho = ZERO
            for line in scope_rho:
                try:
                    actual_rho += money(line["amount"])
                except (KeyError, ValueError) as exc:
                    blockers.append("%s has invalid Rho fee amount: %s" % (event_id, exc))

            expected = None
            if product is not None:
                try:
                    expected = expected_rho_fee(product, event, light_blue_order.get(event_id))
                except ValueError as exc:
                    blockers.append("%s cannot be evaluated: %s" % (event_id, exc))

            if expected is not None and scope_rho:
                if actual_rho > expected:
                    fee_items.append({
                        "event_id": event_id,
                        "expected_rho_fee": money_text(expected),
                        "actual_posted_rho_fee": money_text(actual_rho),
                        "fee_refund": money_text(actual_rho - expected),
                    })
                elif actual_rho < expected:
                    warnings.append("%s was charged less than the documented fee; no debit correction is proposed" % event_id)

            event_records.append({
                "event_id": event_id,
                "expected_rho_fee": money_text(expected) if expected is not None else None,
                "actual_posted_rho_fee": money_text(actual_rho),
                "in_scope_rho_fee_lines": len(scope_rho),
            })

            if product == "purple" and event.get("eligible_for_purple_rebate") is True:
                scoped_operator = scoped_posted(operator_lines, review_month, warnings, "operator fee", event_id)
                operator_total = ZERO
                for line in scoped_operator:
                    try:
                        operator_total += money(line["amount"])
                    except (KeyError, ValueError) as exc:
                        blockers.append("%s has invalid operator fee amount: %s" % (event_id, exc))
                if operator_total > ZERO:
                    dates = [parse_date(line["date"]) for line in scoped_operator]
                    purple_rebate_candidates.append((min(dates), event_id, operator_total, rebate_lines))
            elif product == "purple" and operator_lines and event.get("eligible_for_purple_rebate") is not False:
                blockers.append("%s has an operator fee without confirmed Purple rebate eligibility" % event_id)

        # The cap is allocated chronologically among confirmed eligible operator
        # fees. Rebate lines must have been manually linked to their event.
        remaining_cap = CAP_PURPLE_REBATE
        for _, event_id, operator_total, rebate_lines in sorted(purple_rebate_candidates, key=lambda row: (row[0], row[1])):
            expected_rebate = min(operator_total, remaining_cap)
            remaining_cap -= expected_rebate
            actual_rebate = ZERO
            for line in scoped_posted(rebate_lines, review_month, warnings, "rebate credit", event_id):
                try:
                    actual_rebate += money(line["amount"])
                except (KeyError, ValueError) as exc:
                    blockers.append("%s has invalid rebate amount: %s" % (event_id, exc))
            if actual_rebate > expected_rebate:
                warnings.append("%s has rebate credits greater than the documented monthly-cap allocation; review the linkage" % event_id)
            elif actual_rebate < expected_rebate:
                rebate_items.append({
                    "event_id": event_id,
                    "eligible_operator_fee": money_text(operator_total),
                    "expected_rebate_under_monthly_cap": money_text(expected_rebate),
                    "posted_related_rebate": money_text(actual_rebate),
                    "missing_rebate": money_text(expected_rebate - actual_rebate),
                })

        fee_total = sum((Decimal(item["fee_refund"]) for item in fee_items), ZERO)
        rebate_total = sum((Decimal(item["missing_rebate"]) for item in rebate_items), ZERO)
        total = fee_total + rebate_total
        fee_count = len(fee_items)
        rebate_count = len(rebate_items)
        credit_type = None
        manual_decision = False
        if fee_count > rebate_count:
            credit_type = "fee_refund"
        elif rebate_count > fee_count:
            credit_type = "rebate_credit"
        elif total > ZERO:
            manual_decision = True
            blockers.append("Mixed correction categories have no strict majority for credit_type")

        ready = bool(total > ZERO and not blockers and not manual_decision)
        results.append({
            "account_id": account_id,
            "account_class": account.get("account_class"),
            "supported_product": product,
            "event_comparisons": event_records,
            "fee_refund_items": fee_items,
            "missing_rebate_items": rebate_items,
            "fee_refund_total": money_text(fee_total),
            "missing_rebate_total": money_text(rebate_total),
            "recommended_credit_total": money_text(total),
            "recommended_credit_type": credit_type,
            "manual_decision_required": manual_decision,
            "ready_for_credit": ready,
            "blocking_warnings": blockers,
            "warnings": warnings,
        })

    return {
        "review_month": review_month,
        "account_results": results,
        "global_warnings": global_warnings,
        "note": "A ready result is a calculation aid only; the executor must confirm history, checking eligibility, identity verification, and one-call credit restrictions before any banking action.",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
