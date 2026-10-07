#!/usr/bin/env python3
"""Calculate a debit-card replacement quote without taking a bank action."""
import datetime as dt
import json
import sys

P = {
 "ENTRY": (2, 2, {"STANDARD":0}, {"CLASSIC":0,"PREMIUM":10,"CUSTOM":25}, 25),
 "MID": (3, 0, {"STANDARD":0,"EXPEDITED":15}, {"CLASSIC":0,"PREMIUM":10,"CUSTOM":25}, 15),
 "PREMIUM": (5, 0, {"STANDARD":0,"EXPEDITED":0,"RUSH":35}, {"CLASSIC":0,"PREMIUM":0,"CUSTOM":15}, None),
 "ELITE": (None, 0, {"STANDARD":0,"EXPEDITED":0,"RUSH":0}, {"CLASSIC":0,"PREMIUM":0,"CUSTOM":0}, None),
}
def iso(v):
    try: return dt.date.fromisoformat(v) if isinstance(v,str) else None
    except ValueError: return None
def main(x):
    out={"eligible":False,"delivery_fee":None,"design_fee":None,"excess_replacement_fee":None,"reasons":[]}
    tier,count,ship,design=x.get("tier"),x.get("replacement_count_last_12_months"),x.get("shipping_method"),x.get("card_design")
    if tier not in P: out["reasons"].append("unsupported_or_missing_tier"); return out
    if not isinstance(count,int) or count<0: out["reasons"].append("invalid_replacement_count"); return out
    limit,wait,shipping,designs,excess=P[tier]
    if ship not in shipping: out["reasons"].append("shipping_not_permitted_for_tier")
    if design not in designs: out["reasons"].append("design_not_permitted_for_tier")
    if out["reasons"]: return out
    if wait:
        close,now=iso(x.get("closed_at")),iso(x.get("now"))
        if not close or not now: out["reasons"].append("entry_wait_period_dates_required"); return out
        if now < close+dt.timedelta(days=wait): out["reasons"].append("entry_48_hour_wait_not_complete"); return out
    if limit is not None and count>=limit:
        if excess is None: out["reasons"].append("replacement_limit_reached_must_wait"); return out
        out["excess_replacement_fee"]=excess; out["reasons"].append("replacement_limit_reached_excess_fee_required")
    out.update(eligible=True, delivery_fee=shipping[ship], design_fee=designs[design])
    return out
if __name__ == "__main__":
    try:
        obj=json.load(sys.stdin)
        if not isinstance(obj,dict): raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(obj),separators=(",",":")))
    except (ValueError,json.JSONDecodeError) as exc:
        print(json.dumps({"eligible":False,"delivery_fee":None,"design_fee":None,"excess_replacement_fee":None,"reasons":["invalid_input",str(exc)]},separators=(",",":")))
        sys.exit(2)
