#!/usr/bin/env python3
"""Check that a proposed answer covers all source-supported active bonuses."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from extract_promotions import main as extract
from analyze_offers import main as analyze

def main(p):
    if not isinstance(p, dict) or not isinstance(p.get("response"), str): return {"ok":False,"errors":["response must be a string"],"warnings":[]}
    ex = extract(p)
    if not ex.get("ok"): return ex
    a = analyze({"as_of":ex.get("as_of"),"offers":ex.get("offers",[])})
    text = " ".join(p["response"].lower().replace("$", " $").split()); errors = []
    for o in a.get("active_signup_bonuses",[]):
        if o["card"].lower() not in text: errors.append("Missing active card name: "+o["card"])
        amount = str(o.get("reward",{}).get("amount","")); comma = format(int(amount), ",") if amount.isdigit() else amount
        if amount and amount not in text and comma not in text: errors.append("Missing reward amount: "+o["card"])
        q = o.get("qualification") or {}
        if q.get("invitation_required") and not any(x in text for x in ("invitation", "invited", "invite-only")): errors.append("Missing invitation restriction: "+o["card"])
        if q.get("spend_requirement") and q["spend_requirement"].split()[0].replace("$", "") not in text.replace(",", ""): errors.append("Missing spend requirement: "+o["card"])
        if o.get("product_scope") == "business" and "business" not in text: errors.append("Missing business context: "+o["card"])
    if len(a.get("active_signup_bonuses",[])) > 1 and not any(x in text for x in ("largest","highest","best","top","most valuable","strongest")): errors.append("Missing value comparison")
    return {"ok":not errors,"errors":errors,"warnings":ex.get("warnings",[])+a.get("warnings",[])}
if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as e: print(json.dumps({"ok":False,"errors":["Invalid JSON: "+e.msg],"warnings":[]}))
