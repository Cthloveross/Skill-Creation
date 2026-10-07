#!/usr/bin/env python3
"""Validate structural hard requirements of an itinerary artifact.
Input stdin: {"output":"/app/output/itinerary.json", "days":7}.
Output stdout: {"valid": true} or {"valid": false, "errors":[...]}.
"""
import json, sys

def main(c):
    errors=[]
    try:
        with open(c.get("output", "/app/output/itinerary.json"), encoding="utf-8") as f: x=json.load(f)
    except Exception as e:
        return {"valid":False,"errors":["cannot parse artifact: "+str(e)]}
    if set(x) != {"plan","tool_called"}: errors.append("top-level keys must be plan and tool_called")
    plan=x.get("plan")
    if not isinstance(plan,list) or len(plan)!=int(c.get("days",7)): errors.append("wrong plan length")
    required={"day","current_city","transportation","breakfast","lunch","dinner","attraction","accommodation"}
    if isinstance(plan,list):
        for i,d in enumerate(plan,1):
            if not isinstance(d,dict) or set(d)!=required: errors.append("day %d has wrong keys"%i); continue
            if d["day"]!=i: errors.append("day numbers are not sequential")
            if not all(isinstance(d[k],str) for k in required-{"day"}): errors.append("day %d has non-string fields"%i)
            if "flight" in d["transportation"].lower(): errors.append("flight found")
            if not d["attraction"].endswith(";"): errors.append("attraction lacks final semicolon")
            if "pet-friendly" not in d["accommodation"].lower(): errors.append("lodging is not labeled pet-friendly")
    if not isinstance(x.get("tool_called"),list) or not all(isinstance(v,str) for v in x.get("tool_called",[])): errors.append("tool_called invalid")
    return {"valid":not errors,"errors":errors}
if __name__=="__main__": print(json.dumps(main(json.load(sys.stdin))))
