#!/usr/bin/env python3
"""Pure reward calculation helper; reads JSON stdin and writes JSON stdout."""
import json, sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

ROUND = {"floor": ROUND_DOWN, "nearest": ROUND_HALF_UP, "ceiling": ROUND_CEILING}

def decimal(value):
    if isinstance(value, bool): raise ValueError("amount must not be boolean")
    number = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    if number < 0: raise ValueError("amount must be non-negative")
    return number

def one(tx, rounding):
    for key in ("transaction_id", "card_type", "amount"):
        if tx.get(key) in (None, ""):
            return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": "missing " + key}
    try: amount = decimal(tx["amount"])
    except (InvalidOperation, ValueError) as exc:
        return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": str(exc)}
    card = str(tx["card_type"]).strip()
    out = {"transaction_id": tx["transaction_id"], "card_type": card, "amount": format(amount, "f")}
    if card == "Gold Rewards Card":
        rate, basis = Decimal("2.5"), "Gold Rewards Card rate"
    elif card == "EcoCard":
        eligible = tx.get("eco_green_eligible")
        if not isinstance(eligible, bool):
            out.update(status="needs_eligibility_review", reason="Supply confirmed EcoCard green eligibility; this helper does not infer it.")
            return out
        rate, basis = (Decimal("5"), "qualifying green EcoCard rate") if eligible else (Decimal("1"), "standard EcoCard rate")
    else:
        out.update(status="insufficient_rate_information", reason="No supplied rate for this card type.")
        return out
    exact = amount * rate
    out.update(rate_points_per_dollar=format(rate, "f"), calculation_basis=basis, expected_exact_points=format(exact, "f"))
    if rounding == "unresolved":
        out.update(status="needs_rounding_confirmation", reason="No whole-point rounding rule was supplied.")
        return out
    whole = int(exact.quantize(Decimal("1"), rounding=ROUND[rounding]))
    out.update(status="calculated", rounding=rounding, expected_whole_points=whole)
    return out

def main():
    try:
        data=json.load(sys.stdin)
        if not isinstance(data, dict) or not isinstance(data.get("transactions"), list): raise ValueError("input requires a transactions list")
        rounding=data.get("rounding", "unresolved")
        if rounding not in {"unresolved", *ROUND}: raise ValueError("invalid rounding")
        result=[]
        for tx in data["transactions"]:
            result.append(one(tx, rounding) if isinstance(tx, dict) else {"status":"invalid_input","error":"transaction must be object"})
        print(json.dumps({"rounding":rounding,"results":result}))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error":str(exc)})); sys.exit(2)
if __name__ == "__main__": main()
