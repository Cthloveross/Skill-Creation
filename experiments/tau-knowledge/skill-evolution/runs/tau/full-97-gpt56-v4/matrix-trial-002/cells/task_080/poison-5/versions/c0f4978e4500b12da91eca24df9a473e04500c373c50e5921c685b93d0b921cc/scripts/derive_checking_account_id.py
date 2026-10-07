#!/usr/bin/env python3
"""Derive one runtime-format checking account lookup candidate.

Input: {"verified_user_id": string, "account_label": string}
Output: {"account_id_candidate": string|null, "validation_errors": [string,...]}
The candidate is only a lookup candidate; a returned record must still exactly
match it and the verified user before any card action.
"""
import json, re, sys

def valid(value):
    return isinstance(value, str) and bool(value) and value.strip() == value

def main():
    try:
        data=json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"account_id_candidate":None,"validation_errors":["invalid JSON: "+str(exc)]})); return
    if not isinstance(data,dict):
        print(json.dumps({"account_id_candidate":None,"validation_errors":["top-level input must be an object"]})); return
    user=data.get('verified_user_id'); label=data.get('account_label')
    errors=[]
    if not valid(user) or not re.fullmatch(r'[A-Za-z0-9]+',user): errors.append('verified_user_id must be a nonblank alphanumeric string')
    if not valid(label): errors.append('account_label must be a nonblank string without surrounding whitespace')
    if errors:
        print(json.dumps({"account_id_candidate":None,"validation_errors":errors},sort_keys=True)); return
    words=re.findall(r'[a-z0-9]+',label.lower())
    # Account is a presentation suffix, not part of the account product code.
    if words and words[-1]=='account': words.pop()
    if not words:
        print(json.dumps({"account_id_candidate":None,"validation_errors":["account_label contains no usable product words"]},sort_keys=True)); return
    print(json.dumps({"account_id_candidate":"chk_%s_%s"%(user,'_'.join(words)),"validation_errors":[]},sort_keys=True))
if __name__=='__main__': main()
