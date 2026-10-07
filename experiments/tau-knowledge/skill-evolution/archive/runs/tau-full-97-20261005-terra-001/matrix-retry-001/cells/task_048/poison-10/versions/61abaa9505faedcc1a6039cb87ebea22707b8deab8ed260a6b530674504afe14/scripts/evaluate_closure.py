#!/usr/bin/env python3
"""Evaluate structured credit-card closure eligibility evidence.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never calls banking tools and never changes an account.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def main():
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        current = parse_date(raw.get("current_date"), "current_date")
        opened = parse_date(raw.get("account_open_date"), "account_open_date")
        if opened > current:
            raise ValueError("account_open_date cannot be after current_date")

        age_days = (current - opened).days
        checks = {}
        reasons = []
        unknown = False

        checks["account_age"] = "pass" if age_days >= 60 else "fail"
        if age_days < 60:
            reasons.append("Account must be open for at least 60 days.")

        balance = raw.get("balance")
        if balance is None:
            checks["zero_balance"] = "unknown"
            unknown = True
        else:
            try:
                amount = Decimal(str(balance))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("balance must be numeric") from exc
            checks["zero_balance"] = "pass" if amount == Decimal("0") else "fail"
            if amount != Decimal("0"):
                reasons.append("Outstanding balance must be exactly $0.00.")

        disputes = raw.get("active_or_pending_disputes")
        if disputes is None:
            checks["pending_disputes"] = "unknown"
            unknown = True
        elif not isinstance(disputes, bool):
            raise ValueError("active_or_pending_disputes must be boolean")
        else:
            checks["pending_disputes"] = "fail" if disputes else "pass"
            if disputes:
                reasons.append("Active or pending disputes must be resolved.")

        statuses = raw.get("replacement_order_statuses")
        if statuses is None:
            checks["replacement_orders"] = "unknown"
            unknown = True
        elif not isinstance(statuses, list) or not all(isinstance(x, str) for x in statuses):
            raise ValueError("replacement_order_statuses must be a list of strings")
        else:
            unresolved = [s for s in statuses if s.strip().lower() not in FINAL_REPLACEMENT_STATUSES]
            checks["replacement_orders"] = "fail" if unresolved else "pass"
            if unresolved:
                reasons.append("A replacement-card order remains unresolved.")

        pending = raw.get("pending_transactions_present")
        if pending is None:
            checks["pending_transactions"] = "unknown"
            unknown = True
        elif not isinstance(pending, bool):
            raise ValueError("pending_transactions_present must be boolean")
        else:
            checks["pending_transactions"] = "fail" if pending else "pass"
            if pending:
                reasons.append("Pending transactions must post before closure.")

        if any(value == "fail" for value in checks.values()):
            eligibility = "ineligible"
        elif unknown:
            eligibility = "unknown"
            reasons.append("Required eligibility evidence is missing or unresolved.")
        else:
            eligibility = "eligible"

        print(json.dumps({
            "eligibility": eligibility,
            "account_age_days": age_days,
            "checks": checks,
            "reasons": reasons,
        }, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
