#!/usr/bin/env python3
"""Plan debit-card disputes without performing banking actions.

Read one JSON object on stdin and emit JSON on stdout. Dates are MM/DD/YYYY or
YYYY-MM-DD. This program neither contacts a bank nor changes state.
"""
import json, sys
from collections import defaultdict
from datetime import datetime, date, timedelta

CATEGORIES={"unauthorized_transaction","atm_cash_discrepancy","atm_deposit_not_credited","duplicate_charge","incorrect_amount","goods_services_not_received","recurring_charge_after_cancellation","card_present_fraud","card_not_present_fraud"}
TYPES={"pin_purchase","signature_purchase","online_purchase","atm_withdrawal","atm_deposit","recurring_payment","person_to_person"}
PINS={"yes_shared","yes_observed","no","unknown"}
FRAUD={"card_present_fraud","card_not_present_fraud"}
PC=FRAUD|{"unauthorized_transaction","atm_cash_discrepancy","duplicate_charge"}
OPEN={"OPEN","PENDING_DOCUMENTATION","UNDER_REVIEW","PROVISIONAL_CREDIT_ISSUED"}
LIMITS={"entry":2,"mid":3,"premium":4,"elite":5}
ACTION={c:"keep_active" for c in CATEGORIES}; ACTION.update({"unauthorized_transaction":"freeze_pending_investigation","card_present_fraud":"close_and_reissue","card_not_present_fraud":"close_and_reissue"})
SEVERITY={"keep_active":0,"freeze_pending_investigation":1,"close_and_reissue":2}

def d(v):
    if not isinstance(v,str): return None
    for f in ("%m/%d/%Y","%Y-%m-%d"):
        try:return datetime.strptime(v,f).date()
        except ValueError:pass
    return None

def fd(v):
    x=d(v); return x.strftime("%m/%d/%Y") if x else v

def tier(a):
    # account_type/class identifies checking, not necessarily its tier.
    s=" ".join(str(a.get(k,"")) for k in ("account_tier","account_class","level")).lower()
    for k,n in LIMITS.items():
        if k in s:return n,False
    return 2,True                         # safe published lower bound

def business_days(start,end):
    n=0
    while start<end:
        start+=timedelta(days=1)
        if start.weekday()<5:n+=1
    return n

def liability(statement, filing, claimed):
    if not statement or not filing:return None,"statement date is required to calculate liability"
    delta=(filing-statement).days
    if delta<0:return None,"filing date precedes statement date"
    if business_days(statement,filing)<=2:return min(50.0,claimed),None
    if delta<=60:return min(500.0,claimed),None
    return -1.0,None

def main(x):
    filing=d(x.get("filing_date")); out={"claims":[],"card_actions":[],"global_errors":[]}
    if not filing: out["global_errors"].append("filing_date must be a valid date")
    user=x.get("user_id")
    accounts={a.get("account_id"):a for a in x.get("accounts",[]) if a.get("account_id")}
    cards={c.get("card_id"):c for c in x.get("cards",[]) if c.get("card_id")}
    occupied=defaultdict(int)
    for z in x.get("open_disputes",[]):
        if str(z.get("status","")).upper() in OPEN:occupied[z.get("account_id")]+=1
    claims=list(enumerate(x.get("claims",[])))
    # Oldest claims consume scarce capacity first unless caller supplied a lower priority.
    claims.sort(key=lambda ic:(ic[1].get("priority",0),d(ic[1].get("transaction_date")) or date.max,ic[0]))
    duplicate_winner={}
    for i,c in claims:
        g=c.get("duplicate_group")
        if g:
            key=(d(c.get("transaction_date")) or date.max,c.get("duplicate_sequence",i),i)
            if g not in duplicate_winner or key<duplicate_winner[g][0]:duplicate_winner[g]=(key,i)
    filed=defaultdict(list)
    for i,c in claims:
        errs=[]; warns=[]; cat=c.get("dispute_category"); typ=c.get("transaction_type"); tx=d(c.get("transaction_date")); disc=d(c.get("discovery_date")); stmt=d(c.get("statement_date"))
        a=accounts.get(c.get("account_id")); card=cards.get(c.get("card_id"))
        if c.get("duplicate_group") and duplicate_winner[c["duplicate_group"]][1]!=i:
            out["claims"].append({"index":i,"transaction_id":c.get("transaction_id"),"eligible_to_file":False,"errors":[],"warnings":["Skipped: a prior transaction in duplicate group must be disputed first."],"filing_payload":None});continue
        if not c.get("transaction_id"):errs.append("transaction_id is required")
        if cat not in CATEGORIES:errs.append("invalid dispute_category")
        if typ not in TYPES:errs.append("invalid transaction_type")
        if not tx or not disc:errs.append("transaction_date and discovery_date are required valid dates")
        if tx and disc and disc<tx:errs.append("discovery_date cannot precede transaction_date")
        try:
            total=abs(float(c.get("transaction_amount"))); amount=float(c.get("disputed_amount"))
            if amount<1:errs.append("disputed_amount must be at least $1")
            if amount>total:errs.append("disputed_amount exceeds transaction amount")
        except (TypeError,ValueError): total=amount=0;errs.append("amounts must be numeric")
        if filing and tx and (tx>filing or (filing-tx).days>60):errs.append("transaction is outside the permitted 60-day window")
        if not a: errs.append("account was not retrieved")
        else:
            account_type=str(a.get("account_type",a.get("class",""))).lower()
            if account_type!="checking":errs.append("linked account is not checking")
            if str(a.get("status","")).upper()!="OPEN":errs.append("linked account is not OPEN")
        if not card:errs.append("card was not retrieved")
        else:
            if card.get("account_id")!=c.get("account_id"):errs.append("card is not linked to account")
            if user and card.get("user_id")!=user:errs.append("card is not owned by user")
        for k in ("card_in_possession","contacted_merchant","police_report_filed","written_statement_provided"):
            if not isinstance(c.get(k),bool):errs.append(k+" must be boolean")
        if c.get("pin_compromised") not in PINS:errs.append("invalid pin_compromised")
        if cat in FRAUD and c.get("fraud_suspected") is False:errs.append("fraud category conflicts with fraud_suspected=false")
        if cat=="unauthorized_transaction" and c.get("fraud_suspected") is True:errs.append("suspected fraud needs fraud category")
        if cat in FRAUD and amount>500 and not c.get("police_report_filed"):warns.append("Recommend police report for fraud over $500.")
        if cat.startswith("atm_") and c.get("atm_owner") not in {"rho_bank","third_party"}:errs.append("ATM owner must be confirmed")
        lim,conservative=tier(a or {})
        if conservative:warns.append("Account tier unavailable; applied conservative maximum of 2 open disputes.")
        if occupied[c.get("account_id")]>=lim:errs.append("account has reached the open-dispute limit")
        computed,liaberr=liability(stmt,filing,amount)
        provided=c.get("customer_max_liability_amount")
        if provided is None:
            if liaberr:errs.append(liaberr)
            else: provided=computed
        else:
            try: provided=float(provided)
            except (TypeError,ValueError):errs.append("customer_max_liability_amount must be numeric")
        reasons=[]
        clear=bool(a) and str(a.get("status","")).upper()=="OPEN" and not a.get("has_holds_or_restrictions",False)
        opened=d(a.get("date_opened")) if a else None
        if cat not in PC: reasons.append("category is not covered")
        if not stmt or not filing or (filing-stmt).days<0 or (filing-stmt).days>60:reasons.append("timely statement reporting is not established")
        if not c.get("written_statement_provided"):reasons.append("no written statement")
        if not clear:reasons.append("account is not open and clear")
        if c.get("pin_compromised")=="yes_shared":reasons.append("PIN was voluntarily shared")
        if opened and filing and (filing-opened).days<30 and cat=="card_not_present_fraud":reasons.append("new-account card-not-present exclusion")
        if cat not in FRAUD and not c.get("contacted_merchant"):reasons.append("merchant has not been contacted")
        provisional=not reasons
        ok=not errs
        payload=None
        if ok:
            occupied[c.get("account_id")]+=1; filed[c.get("card_id")].append(cat)
            payload={"transaction_id":c.get("transaction_id"),"account_id":c.get("account_id"),"card_id":c.get("card_id"),"user_id":user,"dispute_category":cat,"transaction_date":fd(c.get("transaction_date")),"discovery_date":fd(c.get("discovery_date")),"disputed_amount":amount,"transaction_type":typ,"card_in_possession":c.get("card_in_possession"),"pin_compromised":c.get("pin_compromised"),"contacted_merchant":c.get("contacted_merchant"),"police_report_filed":c.get("police_report_filed"),"written_statement_provided":c.get("written_statement_provided"),"provisional_credit_eligible":provisional,"customer_max_liability_amount":provided,"card_action":ACTION[cat]}
        out["claims"].append({"index":i,"transaction_id":c.get("transaction_id"),"eligible_to_file":ok,"errors":errs,"warnings":warns,"provisional_credit_eligible":provisional,"provisional_credit_reasons_not_required":reasons,"filing_payload":payload})
    for cid,cats in filed.items():
        act=max((ACTION[c] for c in cats),key=lambda z:SEVERITY[z]); card=cards[cid]; blockers=[]; tool=args=None
        if act=="freeze_pending_investigation":
            if str(card.get("status","")).upper()=="ACTIVE": tool,args="freeze_debit_card_3892",{"card_id":cid}
            else:blockers.append("card must be ACTIVE to freeze")
        elif act=="close_and_reissue":
            if str(card.get("status","")).upper() not in {"ACTIVE","PENDING"}:blockers.append("card must be ACTIVE or PENDING to close")
            if card.get("pending_transactions"):blockers.append("pending transactions must settle")
            if card.get("pending_refunds"):blockers.append("pending refunds must settle or be acknowledged in writing")
            if not blockers:tool,args="close_debit_card_4721",{"card_id":cid,"reason":"fraud_suspected"}
        out["card_actions"].append({"card_id":cid,"actual_action":act,"categories":cats,"tool":tool,"arguments":args,"blockers":blockers})
    out["claims"].sort(key=lambda q:q["index"])
    return out
if __name__=="__main__":
    try: print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
    except Exception as e: print(json.dumps({"error":str(e)}))
