#!/usr/bin/env python3
"""Read one JSON object and emit a safe incident-transfer plan as JSON."""
import json, re, sys
from datetime import datetime
DEADLINE=datetime(2025,11,15,23,59)
FIRST='initial_transfer_to_human_agent_1822'
SECOND='initial_transfer_to_human_agent_0218'
BOOLS=('paid_statement','deducted_from_checking','not_reflected_in_card_balance','explicit_human_request','first_initial_completed','second_initial_completed')
def out(applicable,status,action,**extra):
    return dict(applicable=applicable,status=status,action=action,**extra)
def stop(status,message): return out(False,status,'stop',message=message)
def main(d):
    if not isinstance(d,dict): return stop('insufficient_information','Input must be a JSON object.')
    for k in BOOLS:
        if type(d.get(k)) is not bool: return stop('insufficient_information','Missing or non-boolean field: '+k)
    n=d.get('prior_transfer_requests')
    if type(n) is not int or n<0: return stop('insufficient_information','prior_transfer_requests must be a nonnegative integer.')
    t=d.get('current_time')
    if not isinstance(t,str): return stop('insufficient_information','current_time is required.')
    m=re.fullmatch(r'\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?\s+EST\s*',t)
    if not m: return stop('insufficient_information','current_time must be YYYY-MM-DD HH:MM[:SS] EST.')
    try: now=datetime.strptime(m.group(1)+' '+m.group(2)+':'+(m.group(3) or '00'),'%Y-%m-%d %H:%M:%S')
    except ValueError: return stop('insufficient_information','current_time is invalid.')
    if now>DEADLINE: return out(False,'outside_incident_window','standard_handling')
    if not all(d[k] for k in BOOLS[:3]): return out(False,'symptoms_do_not_match','standard_handling')
    first,second=d['first_initial_completed'],d['second_initial_completed']
    if second and not first: return stop('invalid_state','Second stage cannot precede first stage.')
    if n==0 and (first or second): return stop('invalid_state','Completed stage conflicts with zero earlier requests.')
    if n==1 and (not first or second): return stop('invalid_state','Second request requires only first stage complete.')
    if n==2 and (not first or not second): return stop('invalid_state','Third request requires both stages complete.')
    if not d['explicit_human_request']: return out(True,'awaiting_explicit_transfer_request','acknowledge_and_offer_human_transfer')
    if n==0: return out(True,'ok','first_initial_transfer',unlock_agent_tool=FIRST,call_agent_tool=FIRST,call_arguments={})
    if n==1: return out(True,'ok','second_initial_transfer',unlock_agent_tool=SECOND,call_agent_tool=SECOND,call_arguments={})
    if n==2: return out(True,'ok','regular_human_transfer',transfer_reason='specialized_department_required')
    return out(True,'transfer_sequence_already_advanced','stop')
try:
    print(json.dumps(main(json.load(sys.stdin)),sort_keys=True))
except (ValueError,json.JSONDecodeError) as e:
    print(json.dumps(stop('insufficient_information',str(e)),sort_keys=True))
