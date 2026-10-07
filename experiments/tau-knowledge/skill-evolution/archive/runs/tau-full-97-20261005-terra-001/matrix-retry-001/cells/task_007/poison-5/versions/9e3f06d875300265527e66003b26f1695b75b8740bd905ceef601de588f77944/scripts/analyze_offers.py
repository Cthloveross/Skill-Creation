#!/usr/bin/env python3
"""Classify structured promotion records against an inclusive as-of date."""
import json, re, sys
from datetime import date
from decimal import Decimal

def day(x):
    try: return date.fromisoformat(re.match(r"^\d{4}-\d{2}-\d{2}", str(x)).group(0))
    except (AttributeError, ValueError): return None

def value(offer):
    r = offer.get("reward", {}); kind = str(r.get("kind", "")).lower()
    try: amount = Decimal(str(r["amount"]))
    except Exception: return None
    if kind in ("statement_credit","cash_back","cash") and str(r.get("currency")).upper() == "USD": return amount
    if kind == "points" and r.get("redemption_value_per_point") is not None:
        try: return amount * Decimal(str(r["redemption_value_per_point"]))
        except Exception: pass
    return None

def main(p):
    as_of = day(p.get("as_of")) if isinstance(p, dict) else None
    offers = p.get("offers") if isinstance(p, dict) else None
    if not as_of or not isinstance(offers, list): return {"ok":False,"errors":["as_of and offers are required"],"warnings":[]}
    active, other, warnings = [], [], []
    for raw in offers:
        if not isinstance(raw, dict): continue
        s, e = day(raw.get("window_start")), day(raw.get("window_end")); rec = dict(raw)
        if not s or not e or s > e: rec["status"] = "date_unknown"
        elif as_of < s: rec["status"] = "upcoming"
        elif as_of > e: rec["status"] = "expired"
        else: rec["status"] = "active"
        if rec["status"] == "active" and str(rec.get("offer_type")).lower() == "signup_bonus":
            v = value(rec); rec["documented_usd_value"] = str(v) if v is not None else None
            if v is None: warnings.append(str(rec.get("card", "offer"))+": no documented USD comparison value")
            active.append(rec)
        else: other.append(rec)
    active.sort(key=lambda x: (x["documented_usd_value"] is None, -(Decimal(x["documented_usd_value"]) if x["documented_usd_value"] else 0), str(x.get("card", "")).lower()))
    return {"ok":True,"as_of":as_of.isoformat(),"active_signup_bonuses":active,"inactive_or_nonbonus":other,"warnings":warnings,"errors":[]}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as e: print(json.dumps({"ok":False,"errors":["Invalid JSON: "+e.msg],"warnings":[]}))
