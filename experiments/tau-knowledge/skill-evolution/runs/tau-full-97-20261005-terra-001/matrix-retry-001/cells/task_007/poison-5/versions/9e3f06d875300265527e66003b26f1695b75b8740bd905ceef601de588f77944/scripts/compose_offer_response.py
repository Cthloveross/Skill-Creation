#!/usr/bin/env python3
"""Compose a direct customer-facing draft from reviewed structured offers."""
import json, os, sys
from decimal import Decimal
sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze

def number(x):
    n = Decimal(str(x)); return format(int(n), ",") if n == n.to_integral() else format(n, ",.2f")
def reward(r):
    r = r or {}; k = str(r.get("kind", "bonus")).replace("_", " "); a = number(r.get("amount", 0))
    if k in ("statement credit", "cash back", "cash"): return "$%s %s" % (a, k)
    text = "%s %s" % (a, r.get("point_type") or k)
    if r.get("redemption_value_per_point") is not None:
        text += " (about $%s at the documented $%s-per-point redemption rate)" % (number(Decimal(str(r["amount"])) * Decimal(str(r["redemption_value_per_point"]))), r["redemption_value_per_point"])
    return text
def detail(o):
    q = o.get("qualification") or {}; fee = o.get("annual_fee") or {}
    bits = []
    if q.get("invitation_required"): bits.append("invitation-only")
    if q.get("new_customer_required"): bits.append("eligible new customers only")
    for x in ("required_event","spend_requirement","spend_window","good_standing"):
        if q.get(x): bits.append(str(q[x]))
    if q.get("exclusions"): bits.append("returns, credits, and other documented exclusions reduce qualifying spend")
    text = "%s (%s): %s. Campaign: %s through %s." % (o["card"], "business-card alternative" if o.get("product_scope") == "business" else "consumer card", reward(o.get("reward")), o.get("window_start"), o.get("window_end"))
    if bits: text += " Requirements: %s." % "; ".join(bits)
    if fee.get("standard"): text += " Standard annual fee: %s." % fee["standard"]
    if fee.get("waiver_condition"): text += " %s." % fee["waiver_condition"]
    return text
def main(p):
    r = analyze(p)
    if not r.get("ok"): return r
    offers = r["active_signup_bonuses"]
    if not offers:
        r["response"] = "As of %s, no active sign-up bonus is supported by the supplied dated records." % r["as_of"]; return r
    lead = offers[0]; lines = ["As of %s, the largest active headline sign-up bonus by documented redemption value is %s: %s." % (r["as_of"], lead["card"], reward(lead.get("reward"))), detail(lead)]
    if len(offers) > 1: lines += ["Other active sign-up bonuses:"] + [detail(x) for x in offers[1:]]
    alt = next((x for x in offers[1:] if x.get("product_scope") != "business"), None)
    rec = "Recommendation: %s has the highest stated bonus" % lead["card"]
    if (lead.get("qualification") or {}).get("invitation_required"): rec += ", but it is invitation-only"
    rec += " and is practical only if its spend requirement and annual-fee conditions are realistic."
    if alt: rec += " %s is the more accessible active consumer alternative when its lower threshold or new-customer access is a better fit." % alt["card"]
    biz = next((x for x in offers if x.get("product_scope") == "business"), None)
    if biz: rec += " %s is relevant only for a qualifying business applicant and should be compared separately on annual fee." % biz["card"]
    r["response"] = "\n\n".join(lines + [rec]); return r
if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as e: print(json.dumps({"ok":False,"errors":["Invalid JSON: "+e.msg],"warnings":[]}))
