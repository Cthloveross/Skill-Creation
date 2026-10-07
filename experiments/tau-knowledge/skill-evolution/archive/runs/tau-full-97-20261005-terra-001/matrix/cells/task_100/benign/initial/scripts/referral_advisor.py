#!/usr/bin/env python3
"""Evaluate documented business-checking referral program eligibility.
Reads one JSON object on stdin and emits one JSON object on stdout.
"""
import json
import sys
from datetime import datetime, date, timedelta, timezone
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


def truth(value):
    return value is True


def state_for_fact(facts, key, label):
    value = facts.get(key)
    if value is True:
        return None
    if value is False:
        return {"kind": "blocked", "reason": label + " is not satisfied"}
    return {"kind": "needs_confirmation", "reason": "Confirm " + label}


def main(payload):
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    now = parse_when(payload.get("now"), "now")
    deposit = payload.get("planned_new_money_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        raise ValueError("planned_new_money_deposit must be a nonnegative number")

    facts = payload.get("general_referral_facts", {})
    if not isinstance(facts, dict):
        raise ValueError("general_referral_facts must be an object")
    global_findings = []
    for key, label in [
        ("new_customer", "that the referred person is a new Rho-Bank customer"),
        ("separate_registered_address", "that referrer and referred person have separate registered addresses"),
        ("different_business_primary_owner", "that the referred business has a different primary owner"),
    ]:
        finding = state_for_fact(facts, key, label)
        if finding:
            global_findings.append(finding)

    events_known = "successful_bonus_events" in payload
    events = payload.get("successful_bonus_events", [])
    if not isinstance(events, list):
        raise ValueError("successful_bonus_events must be an array when supplied")
    parsed_events = []
    if events_known:
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError(f"successful_bonus_events[{index}] must be an object")
            product = event.get("product")
            if not isinstance(product, str) or not product:
                raise ValueError(f"successful_bonus_events[{index}].product is required")
            credited = parse_when(event.get("credited_at"), f"successful_bonus_events[{index}].credited_at")
            if credited > now:
                raise ValueError("successful bonus event cannot be later than now")
            parsed_events.append((product, credited))
        boundary = now - timedelta(days=catalog["global_rules"]["rolling_window_days"])
        recent = [(p, t) for p, t in parsed_events if t >= boundary]
        if len(recent) >= catalog["global_rules"]["rolling_bonus_limit"]:
            global_findings.append({
                "kind": "blocked",
                "reason": "rolling nine-day bonus limit reached",
                "recent_successful_bonus_count": len(recent),
                "eligible_after": (min(t for _, t in recent) + timedelta(days=9)).isoformat()
            })
    else:
        recent = []
        global_findings.append({"kind": "needs_confirmation", "reason": "Retrieve successful referral-bonus history to check the rolling nine-day limit"})

    referrer = payload.get("referrer", {})
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object")
    first_opened = None
    tenure_days = None
    if referrer.get("first_checking_opened") is not None:
        first_opened = parse_when(referrer["first_checking_opened"], "referrer.first_checking_opened")
        if first_opened > now:
            raise ValueError("referrer.first_checking_opened cannot be later than now")
        tenure_days = (now.date() - first_opened.date()).days

    gate_status = "pass"
    if any(item["kind"] == "blocked" for item in global_findings):
        gate_status = "blocked"
    elif global_findings:
        gate_status = "needs_confirmation"

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
        if program.get("terms_complete") is False:
            result["findings"].append({"kind": "needs_confirmation", "reason": "Documented referral qualification terms are incomplete; do not assume missing terms"})
        if program["required_deposit"] is not None and deposit < program["required_deposit"]:
            result["findings"].append({"kind": "blocked", "reason": "planned deposit is below required qualifying deposit"})
        if program["min_tenure_days"] is not None:
            if tenure_days is None:
                result["findings"].append({"kind": "needs_confirmation", "reason": "Confirm exact earliest checking-account opening date"})
            elif tenure_days < program["min_tenure_days"]:
                result["findings"].append({"kind": "blocked", "reason": "earliest checking-account tenure is below program minimum", "tenure_days": tenure_days})
        if not events_known:
            result["findings"].append({"kind": "needs_confirmation", "reason": "Annual referral-bonus count is unknown"})
        else:
            year_count = sum(1 for p, t in parsed_events if p == program["name"] and t.year == now.year)
            result["bonuses_this_calendar_year"] = year_count
            if year_count >= program["annual_cap"]:
                result["findings"].append({"kind": "blocked", "reason": "annual referral-bonus cap reached"})
        result["findings"].extend(global_findings)
        if any(f["kind"] == "blocked" for f in result["findings"]):
            result["eligibility_status"] = "blocked"
        elif result["findings"]:
            result["eligibility_status"] = "needs_confirmation"
        else:
            result["eligibility_status"] = "qualifies_from_known_inputs"
        program_results.append(result)

    qualified = [r for r in program_results if r["eligibility_status"] == "qualifies_from_known_inputs"]
    qualified.sort(key=lambda r: (-r["referrer_bonus"], r["product"]))
    recommendation = qualified[0] if gate_status == "pass" and qualified else None
    return {
        "as_of": now.isoformat(),
        "tenure_days_from_earliest_checking": tenure_days,
        "global_gate": {"status": gate_status, "findings": global_findings},
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
