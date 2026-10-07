#!/usr/bin/env python3
"""Deterministic advisory checks for the personal-checking opening workflow.

Reads one JSON object from stdin and writes one JSON object to stdout.
No bank action, lookup, or logging is performed by this program.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "checking_products.json"


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    # Accept ISO timestamps with timezone offsets where supported.
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    days = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, days[month - 1]))


def calculate_age(dob, as_of):
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


def active_checking_count(accounts):
    count = 0
    pending = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            pending.append("accounts[%d] is not an object" % index)
            continue
        account_type = str(account.get("account_type", "")).strip().lower()
        if account_type != "checking":
            continue
        status = str(account.get("status", "")).strip().lower()
        if not status:
            pending.append("checking account status missing at accounts[%d]" % index)
        elif status in {"active", "open", "opened"}:
            count += 1
    return count, pending


def is_for_cause(item):
    if item.get("closed_for_cause") is True:
        return True
    cause = item.get("cause", item.get("closure_cause", ""))
    return isinstance(cause, str) and cause.strip().lower() in {
        "for cause", "closed for cause", "cause"
    }


def recommend(payload, products):
    requirements = payload.get("requirements", {})
    if not isinstance(requirements, dict):
        return {"ok": False, "error": "requirements must be an object"}
    allowed = {
        "no_overdraft_fee", "automatic_overdraft_protection",
        "min_early_direct_deposit_days", "max_monthly_fee",
        "max_protection_transfer_fee"
    }
    unknown = sorted(set(requirements) - allowed)
    if unknown:
        return {"ok": False, "error": "unsupported requirement keys", "keys": unknown}

    matches = []
    for product in products:
        if requirements.get("no_overdraft_fee") is True and product["overdraft_fee"] != 0:
            continue
        if ("automatic_overdraft_protection" in requirements and
                product["automatic_overdraft_protection"] != requirements["automatic_overdraft_protection"]):
            continue
        if ("min_early_direct_deposit_days" in requirements and
                product["early_direct_deposit_days"] < requirements["min_early_direct_deposit_days"]):
            continue
        if ("max_monthly_fee" in requirements and
                product["monthly_maintenance_fee"] > requirements["max_monthly_fee"]):
            continue
        if "max_protection_transfer_fee" in requirements:
            fee = product["overdraft_protection_transfer_fee"]
            if fee is None or fee > requirements["max_protection_transfer_fee"]:
                continue
        matches.append(product)

    matches.sort(key=lambda p: (p["monthly_maintenance_fee"],
                                float("inf") if p["overdraft_protection_transfer_fee"] is None else p["overdraft_protection_transfer_fee"],
                                p["account_class"]))
    return {
        "ok": True,
        "matches": matches,
        "selection_required": True,
        "warning": "A match is not eligibility approval or authorization to open."
    }


def eligibility(payload):
    pending = []
    failed = []
    as_of = parse_date(payload.get("as_of"))
    dob = parse_date(payload.get("date_of_birth"))

    if payload.get("verified") is not True:
        failed.append("customer identity is not verified")
    if as_of is None:
        pending.append("valid as_of date is required")
    if dob is None:
        pending.append("valid date_of_birth is required")
    elif as_of is not None:
        age = calculate_age(dob, as_of)
        if age < 18:
            failed.append("customer is under 18")
    else:
        age = None

    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        pending.append("accounts must be a list returned from account lookup")
        checking_count = None
    else:
        checking_count, account_pending = active_checking_count(accounts)
        pending.extend(account_pending)
        if checking_count >= 4:
            failed.append("opening would exceed the four personal checking account limit")

    if payload.get("closures_checked") is not True:
        pending.append("checking closure-for-cause history has not been verified")
    closures = payload.get("closures", [])
    if not isinstance(closures, list):
        pending.append("closures must be a list")
    elif as_of is not None and payload.get("closures_checked") is True:
        cutoff = subtract_months(as_of, 6)
        for index, closure in enumerate(closures):
            if not isinstance(closure, dict):
                pending.append("closures[%d] is not an object" % index)
                continue
            if is_for_cause(closure):
                closed_at = parse_date(closure.get("closed_at", closure.get("date_closed")))
                if closed_at is None:
                    pending.append("for-cause closure date missing at closures[%d]" % index)
                elif cutoff <= closed_at <= as_of:
                    failed.append("checking account closed for cause within prior six months")

    return {
        "ok": True,
        "age": age,
        "existing_active_checking_accounts": checking_count,
        "failed": failed,
        "pending": pending,
        "action_allowed": not failed and not pending,
        "warning": "A true result permits no bank action without authority, product selection, fee disclosure, and explicit confirmation."
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "error": "invalid JSON: %s" % exc.msg})
        return
    if not isinstance(payload, dict):
        emit({"ok": False, "error": "input must be a JSON object"})
        return
    try:
        products = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["products"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": "catalog unavailable: %s" % exc})
        return

    operation = payload.get("operation")
    if operation == "catalog":
        emit({"ok": True, "products": products})
    elif operation == "recommend":
        emit(recommend(payload, products))
    elif operation == "eligibility":
        emit(eligibility(payload))
    else:
        emit({"ok": False, "error": "operation must be catalog, recommend, or eligibility"})


if __name__ == "__main__":
    main()
