#!/usr/bin/env python3
"""Validate a debit-card dispute from JSON stdin; emit JSON to stdout.

Input keys: now, identity_verified, account, card, transaction,
open_dispute_count, claim, user_id. Dates are MM/DD/YYYY. account accepts
account_class or level. claim needs category, transaction_type, discovery_date,
card_in_possession, pin_compromised, contacted_merchant, police_report_filed,
written_statement_provided, fraud_suspected, optionally disputed_amount, and optionally
reported_within_60_days_of_statement. Output provides ready_to_file, errors,
warnings, filing_draft, card action, and provisional-credit assessment. It does
not call bank tools or decide any unsupported live-tool-only parameter.
"""
import json, sys
from datetime import datetime

CATS={"unauthorized_transaction","atm_cash_discrepancy","atm_deposit_not_credited","duplicate_charge","incorrect_amount","goods_services_not_received","recurring_charge_after_cancellation","card_present_fraud","card_not_present_fraud"}
TYPES={"pin_purchase","signature_purchase","online_purchase","atm_withdrawal","atm_deposit","recurring_payment","person_to_person"}
PINS={"yes_shared","yes_observed","no","unknown"}
LIMITS={"entry":2,"mid":3,"premium":4,"elite":5}
PC_CATS={"unauthorized_transaction","card_present_fraud","card_not_present_fraud","atm_cash_discrepancy","duplicate_charge"}
FRAUD={"card_present_fraud","card_not_present_fraud"}

def dt(v,label,errors):
    try: return datetime.strptime(v,"%m/%d/%Y").date()
    except (TypeError,ValueError): errors.append(f"{label} must be a valid MM/DD/YYYY date."); return None

def main(d):
    errors=[]; warnings=[]
    need=("now","identity_verified","account","card","transaction","open_dispute_count","claim","user_id")
    missing=[x for x in need if x not in d]
    if missing: return {"ready_to_file":False,"errors":[f"Missing top-level field: {x}." for x in missing],"warnings":[]}
    a,c,t,q=d["account"],d["card"],d["transaction"],d["claim"]
    now=dt(d["now"],"now",errors); txdate=dt(t.get("date"),"transaction.date",errors); disc=dt(q.get("discovery_date"),"claim.discovery_date",errors); opened=dt(a.get("date_opened"),"account.date_opened",errors)
    if d["identity_verified"] is not True: errors.append("Customer identity has not been verified and logged.")
    if str(a.get("account_type",a.get("class",""))).lower()!="checking": errors.append("The linked account is not a checking account.")
    if str(a.get("status","")).upper()!="OPEN": errors.append("The linked checking account is not OPEN.")
    if not c.get("linked") or not c.get("owned_by_customer"): errors.append("Card linkage and customer ownership are not confirmed.")
    if not t.get("transaction_id"): errors.append("No exact transaction ID was identified from account history.")
    try:
        transaction_amount=abs(float(t.get("amount")))
    except (TypeError,ValueError): transaction_amount=None; errors.append("transaction.amount must be numeric.")
    try:
        amount=abs(float(q.get("disputed_amount", transaction_amount)))
        if amount<1: errors.append("Disputed amount must be at least $1.00.")
        if transaction_amount is not None and amount>transaction_amount: errors.append("Disputed amount cannot exceed the transaction amount.")
    except (TypeError,ValueError): amount=None; errors.append("claim.disputed_amount must be numeric when supplied.")
    if now and txdate:
        age=(now-txdate).days
        if age<0: errors.append("Transaction date cannot be in the future.")
        elif age>60: errors.append("Transaction is more than 60 days old.")
    if str(t.get("status","")).lower()=="pending": warnings.append("Selected transaction is pending; reconfirm it before filing.")
    try: count=int(d["open_dispute_count"])
    except (TypeError,ValueError): count=-1; errors.append("open_dispute_count must be an integer.")
    raw=str(a.get("account_class",a.get("level",""))).lower().replace(" tier","").strip()
    tier=next((x for x in LIMITS if x in raw),None)
    if tier and count>=LIMITS[tier]: errors.append(f"Open-dispute limit reached for {tier} ({LIMITS[tier]}).")
    elif not tier and count>=2: errors.append("Account tier is unmapped and count is not safely below every dispute limit.")
    elif not tier: warnings.append("Account tier label is unmapped; count below two is safely below all stated limits.")
    cat=q.get("category"); typ=q.get("transaction_type")
    if cat not in CATS: errors.append("claim.category is not permitted.")
    if typ not in TYPES: errors.append("claim.transaction_type is not permitted.")
    if q.get("pin_compromised") not in PINS: errors.append("claim.pin_compromised is invalid.")
    for key in ("card_in_possession","contacted_merchant","police_report_filed","written_statement_provided"):
        if not isinstance(q.get(key),bool): errors.append(f"claim.{key} must be boolean.")
    if cat in FRAUD and q.get("fraud_suspected") is not True: errors.append("Fraud categories require suspected fraud.")
    if cat=="unauthorized_transaction" and q.get("fraud_suspected") is True: errors.append("Suspected fraud requires a fraud category.")
    if cat not in FRAUD and q.get("contacted_merchant") is False: warnings.append("No merchant/ATM-operator contact; this does not bar filing but provisional credit is not required for a non-fraud claim.")
    if cat in FRAUD and amount and amount>500 and not q.get("police_report_filed"): warnings.append("Recommend a police report for suspected fraud over $500.")
    timely=q.get("reported_within_60_days_of_statement")
    if not isinstance(timely,bool): warnings.append("Statement-date timeliness is unknown; do not promise provisional credit or state an unauthorized-use liability tier."); timely=False
    new=bool(now and opened and 0 <= (now-opened).days <30)
    provisional=bool(timely and cat in PC_CATS and q.get("written_statement_provided") is True and str(a.get("status","")).upper()=="OPEN" and not a.get("has_holds_or_restrictions",False) and q.get("pin_compromised")!="yes_shared" and not(cat=="card_not_present_fraud" and new) and (cat in FRAUD or q.get("contacted_merchant") is True))
    action="close_and_reissue" if cat in FRAUD else "freeze_pending_investigation" if cat=="unauthorized_transaction" else "keep_active"
    ready=not errors
    draft=None
    if ready:
        draft={"transaction_id":t["transaction_id"],"account_id":a.get("account_id"),"card_id":c.get("card_id"),"user_id":d["user_id"],"dispute_category":cat,"transaction_date":t.get("date"),"discovery_date":q.get("discovery_date"),"disputed_amount":amount,"transaction_type":typ,"card_in_possession":q.get("card_in_possession"),"pin_compromised":q.get("pin_compromised"),"contacted_merchant":q.get("contacted_merchant"),"police_report_filed":q.get("police_report_filed"),"written_statement_provided":q.get("written_statement_provided"),"provisional_credit_eligible":provisional,"card_action":action}
        absent=[k for k in ("account_id","card_id","user_id") if not draft.get(k)]
        if absent: errors.extend(f"Filing draft lacks {x}." for x in absent); ready=False; draft=None
    return {"ready_to_file":ready,"errors":errors,"warnings":warnings,"mapped_card_action":action if cat in CATS else None,"provisional_credit_eligible":provisional,"provisional_credit_timeline_business_days":20 if new else 10,"filing_draft":draft}
if __name__=="__main__":
    try: print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
    except json.JSONDecodeError as e: print(json.dumps({"ready_to_file":False,"errors":[f"Invalid input JSON: {e.msg}"],"warnings":[]}))
