#!/usr/bin/env python3
"""Screen and compare documented business-checking referral programs.

Reads one JSON object from stdin and emits one JSON object to stdout. When
referrer screening is incomplete, no product-specific data is emitted.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "referral_programs.json"


def parse_when(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO-8601 date or datetime string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} is not ISO-8601: {value}") from exc
        parsed = datetime.combine(parsed_date, datetime.min.time())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fact_finding(facts, key, label):
    value = facts.get(key)
    if value is True:
        return None
    if value is False:
        return {"kind": "blocked", "reason": label + " is not satisfied"}
    return {"kind": "needs_confirmation", "reason": "Confirm " + label}


def gate_status(findings):
    if any(item["kind"] == "blocked" for item in findings):
        return "blocked"
    if findings:
        return "needs_confirmation"
    return "pass"


def load_history(payload, now, rules, findings):
    events_known = "successful_bonus_events" in payload
    raw_events = payload.get("successful_bonus_events", [])
    if not isinstance(raw_events, list):
        raise ValueError("successful_bonus_events must be an array when supplied")
    parsed = []
    if not events_known:
        findings.append({
            "kind": "needs_confirmation",
            "reason": "Retrieve successful referral-bonus history to check referral limits"
        })
        return False, parsed
    for index, event in enumerate(raw_events):
        if not isinstance(event, dict):
            raise ValueError(f"successful_bonus_events[{index}] must be an object")
        product = event.get("product")
        if not isinstance(product, str) or not product.strip():
            raise ValueError(f"successful_bonus_events[{index}].product is required")
        credited = parse_when(event.get("credited_at"), f"successful_bonus_events[{index}].credited_at")
        if credited > now:
            raise ValueError("successful bonus event cannot be later than now")
        parsed.append((product, credited))
    boundary = now - timedelta(days=rules["rolling_window_days"])
    recent = [(product, credited) for product, credited in parsed if credited >= boundary]
    if len(recent) >= rules["rolling_bonus_limit"]:
        findings.append({
            "kind": "blocked",
            "reason": "rolling nine-day bonus limit reached",
            "recent_successful_bonus_count": len(recent),
            "eligible_after": (min(credited for _, credited in recent) + timedelta(days=9)).isoformat()
        })
    return True, parsed


def read_tenure(referrer, now, findings):
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object")
    exact = referrer.get("first_checking_opened")
    upper_bound = referrer.get("first_checking_opened_on_or_before")
    if exact is not None and upper_bound is not None:
        raise ValueError("supply only one first-checking opening field")
    if exact is None and upper_bound is None:
        findings.append({
            "kind": "needs_confirmation",
            "reason": "Confirm the earliest Rho-Bank checking-account opening date"
        })
        return None, None
    field = "referrer.first_checking_opened" if exact is not None else "referrer.first_checking_opened_on_or_before"
    opened = parse_when(exact if exact is not None else upper_bound, field)
    if opened > now:
        raise ValueError(field + " cannot be later than now")
    basis = "exact" if exact is not None else "conservative_lower_bound"
    return (now.date() - opened.date()).days, basis


def screening_output(now, findings):
    required = []
    for item in findings:
        if item["kind"] == "needs_confirmation":
            required.append(item["reason"])
    return {
        "as_of": now.isoformat(),
        "advice_permitted": False,
        "stage": "collect_referrer_eligibility",
        "global_gate": {"status": gate_status(findings), "findings": findings},
        "next_required_facts": required,
        "instruction": "Do not give product-specific referral recommendations or terms until this screen passes."
    }


def main(payload):
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    now = parse_when(payload.get("now"), "now")
    facts = payload.get("general_referral_facts", {})
    if not isinstance(facts, dict):
        raise ValueError("general_referral_facts must be an object")

    findings = []
    for key, label in [
        ("new_customer", "that the referred person is a new Rho-Bank customer"),
        ("separate_registered_address", "that referrer and referred person have separate registered addresses"),
        ("different_business_primary_owner", "that the referred business has a different primary owner"),
    ]:
        finding = fact_finding(facts, key, label)
        if finding:
            findings.append(finding)

    events_known, parsed_events = load_history(payload, now, catalog["global_rules"], findings)
    tenure_days, tenure_basis = read_tenure(payload.get("referrer", {}), now, findings)

    # This is intentionally before deposit validation and any catalog output. A caller
    # cannot use the helper to expose product terms while screening is incomplete.
    if gate_status(findings) != "pass":
        return screening_output(now, findings)

    deposit = payload.get("planned_new_money_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        raise ValueError("planned_new_money_deposit must be a nonnegative number after eligibility screening")

    program_results = []
    for program in catalog["programs"]:
        result = {
            "product": program["name"],
            "referrer_bonus": program["referrer_bonus"],
            "required_deposit": program["required_deposit"],
            "deposit_window_days": program["deposit_window_days"],
            "min_tenure_days": program["min_tenure_days"],
            "annual_cap": program["annual_cap"],
            "sources": program["sources"],
            "findings": []
        }
        if program.get("payment_timing"):
            result["payment_timing"] = program["payment_timing"]
        if program.get("terms_complete") is False:
            result["findings"].append({
                "kind": "catalog_terms_incomplete",
                "reason": "Documented referral qualification terms are incomplete; do not assume missing terms"
            })
        if program["required_deposit"] is not None and deposit < program["required_deposit"]:
            result["findings"].append({
                "kind": "blocked",
                "reason": "planned deposit is below required qualifying deposit"
            })
        if program["min_tenure_days"] is not None and tenure_days < program["min_tenure_days"]:
            result["findings"].append({
                "kind": "blocked",
                "reason": "earliest checking-account tenure is below program minimum",
                "tenure_days": tenure_days
            })
        year_count = sum(
            1 for product, credited in parsed_events
            if product == program["name"] and credited.year == now.year
        )
        result["bonuses_this_calendar_year"] = year_count
        if year_count >= program["annual_cap"]:
            result["findings"].append({
                "kind": "blocked",
                "reason": "annual referral-bonus cap reached"
            })
        if any(finding["kind"] == "blocked" for finding in result["findings"]):
            result["eligibility_status"] = "blocked"
        elif result["findings"]:
            result["eligibility_status"] = "catalog_terms_incomplete"
        else:
            result["eligibility_status"] = "qualifies_from_known_inputs"
        program_results.append(result)

    qualified = [
        result for result in program_results
        if result["eligibility_status"] == "qualifies_from_known_inputs"
    ]
    qualified.sort(key=lambda result: (-result["referrer_bonus"], result["product"]))
    recommendation = qualified[0] if qualified else None
    return {
        "as_of": now.isoformat(),
        "advice_permitted": True,
        "stage": "compare_documented_programs",
        "tenure_days_from_earliest_checking": tenure_days,
        "tenure_basis": tenure_basis,
        "global_gate": {"status": "pass", "findings": []},
        "ranked_qualifying_products": qualified,
        "recommendation": recommendation,
        "account_opening_prerequisites_not_evaluated": catalog["business_account_opening_prerequisites"],
        "global_terms_to_disclose": catalog["global_rules"],
        "products": program_results
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(raw), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
