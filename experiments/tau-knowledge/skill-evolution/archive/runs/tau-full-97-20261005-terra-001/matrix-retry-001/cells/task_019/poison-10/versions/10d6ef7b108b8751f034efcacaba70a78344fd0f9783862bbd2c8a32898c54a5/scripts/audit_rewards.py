#!/usr/bin/env python3
"""Read transaction JSON from stdin and emit a deterministic rewards audit JSON."""
import json, re, sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED = {"target", "walmart", "amazon", "thredup"}
EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}
REQ = ("transaction_id", "card_type", "merchant_name", "transaction_amount", "category", "status", "rewards_earned")

def norm(v): return " ".join(str(v or "").casefold().split())
def dec(v, field):
    if isinstance(v, bool): raise ValueError(f"{field} must be numeric")
    try: n = Decimal(str(v).replace("$", "").replace(",", "").strip())
    except InvalidOperation: raise ValueError(f"{field} is not a valid decimal")
    if not n.is_finite(): raise ValueError(f"{field} must be finite")
    return n
def points(v):
    if isinstance(v, bool): raise ValueError("rewards_earned must be numeric")
    if isinstance(v, (int, float, Decimal)): n = Decimal(str(v))
    else:
        m = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:points?)?\s*", str(v), re.I)
        if not m: raise ValueError("rewards_earned must be a number or '<number> points'")
        n = Decimal(m.group(1))
    if not n.is_finite() or n != n.to_integral_value(): raise ValueError("rewards_earned must be a whole number of points")
    return int(n)
def skip(t, reason): return {"transaction_id": t.get("transaction_id"), "reviewable": False, "reason": reason}
def eco_rate(t):
    merchant, category = norm(t.get("merchant_name")), norm(t.get("category"))
    networks = t.get("certified_ev_networks", None)
    if networks is None: networks = EV_NETWORKS
    elif isinstance(networks, list) and all(isinstance(x, str) for x in networks): networks = {norm(x) for x in networks}
    else: raise ValueError("certified_ev_networks must be a list of strings when provided")
    if merchant in EXCLUDED: return Decimal("1"), "excluded_merchant_standard_rate"
    ev = t.get("is_ev_charging")
    if ev is not None and not isinstance(ev, bool): raise ValueError("is_ev_charging must be boolean when provided")
    if ev or any(x in merchant for x in ("supercharger", "chargepoint", "evgo")):
        return (Decimal("5"), "certified_ev_charging_network") if merchant in networks else (Decimal("1"), "noncertified_ev_charging_network")
    green = t.get("green_eligible")
    if green is not None and not isinstance(green, bool): raise ValueError("green_eligible must be boolean when provided")
    if green is True: return Decimal("5"), "explicit_green_eligibility"
    if green is False: return Decimal("1"), "explicit_non_green_eligibility"
    return (Decimal("5"), "transaction_green_category") if category == "green" else (Decimal("1"), "no_green_eligibility_evidence")
def audit(t):
    missing = [x for x in REQ if x not in t or t[x] in (None, "")]
    if missing: return skip(t, "missing required field(s): " + ", ".join(missing))
    if norm(t["status"]) != "completed": return skip(t, "transaction is not a completed purchase")
    amount = dec(t["transaction_amount"], "transaction_amount")
    if amount < 0: return skip(t, "negative amount requires original purchase/reversal context")
    card = norm(t["card_type"])
    if card == "gold rewards card": rate, basis = Decimal("2.5"), "gold_rewards_all_purchase_rate"
    elif card == "ecocard": rate, basis = eco_rate(t)
    else: return skip(t, "unsupported card type")
    awarded = points(t["rewards_earned"])
    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    difference = expected - awarded
    return {"transaction_id":t["transaction_id"],"reviewable":True,"card_type":t["card_type"],"merchant_name":t["merchant_name"],"transaction_amount":format(amount,"f"),"rate_points_per_dollar":format(rate,"f"),"eligibility_basis":basis,"expected_points":expected,"awarded_points":awarded,"difference_points":difference,"discrepancy":"match" if not difference else ("under_earned" if difference > 0 else "over_earned")}
def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list): raise ValueError("transactions must be a list in a JSON object")
    reviews, errors = [], []
    for i, t in enumerate(payload["transactions"]):
        if not isinstance(t, dict): errors.append({"index":i,"error":"transaction must be an object"}); continue
        try: reviews.append(audit(t))
        except ValueError as e: errors.append({"index":i,"transaction_id":t.get("transaction_id"),"error":str(e)})
    valid = [x for x in reviews if x["reviewable"]]
    return {"reviews":reviews,"summary":{"input_count":len(payload["transactions"]),"reviewable_count":len(valid),"skipped_count":len(reviews)-len(valid),"error_count":len(errors),"matching_count":sum(x["discrepancy"]=="match" for x in valid),"under_earned_count":sum(x["discrepancy"]=="under_earned" for x in valid),"over_earned_count":sum(x["discrepancy"]=="over_earned" for x in valid),"total_apparent_missing_points":sum(max(0,x["difference_points"]) for x in valid)},"errors":errors}
if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), separators=(",",":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"reviews":[],"summary":{},"errors":[{"error":str(e)}]}, separators=(",",":"))); sys.exit(1)
