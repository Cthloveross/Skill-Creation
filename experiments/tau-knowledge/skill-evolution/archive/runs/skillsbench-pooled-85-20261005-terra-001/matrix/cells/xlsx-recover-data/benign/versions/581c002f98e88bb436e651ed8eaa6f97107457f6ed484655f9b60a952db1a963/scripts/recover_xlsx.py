#!/usr/bin/env python3
"""Conservative inspection, derivation, and safe repair of xlsx marker cells.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json, math, os, re, sys
from pathlib import Path
try:
    import openpyxl
    from openpyxl.utils import range_boundaries
except ImportError as exc:
    print(json.dumps({"ok":False,"error":"openpyxl is required","detail":str(exc)})); raise SystemExit(1)

MARKER = "???"
SUM_RE = re.compile(r"^\s*=\s*SUM\(\s*(\$?[A-Z]{1,3}\$?\d+\s*:\s*\$?[A-Z]{1,3}\$?\d+)\s*\)\s*$", re.I)
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

def out(x, code=0):
    print(json.dumps(x, ensure_ascii=False, default=str, allow_nan=False)); raise SystemExit(code)
def fail(msg, **kw): out(dict(ok=False, error=msg, **kw), 1)
def number(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))
def norm(x): return re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip() if isinstance(x,str) else ""
def val(x): return x.isoformat() if hasattr(x,"isoformat") else x

def load(path, data_only=False):
    if not isinstance(path,str) or not path: fail("input_path must be a nonempty string")
    if not Path(path).is_file(): fail("workbook does not exist", input_path=path)
    try: return openpyxl.load_workbook(path, data_only=data_only, keep_links=True)
    except Exception as e: fail("unable to load workbook", input_path=path, detail=str(e))
def targets(wb, marker):
    return [f"{ws.title}!{c.coordinate}" for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value == marker]
def split(wb, target):
    if not isinstance(target,str) or "!" not in target: fail("address must be Sheet!A1", target=target)
    sh, addr = target.rsplit("!",1)
    if sh not in wb.sheetnames: fail("unknown worksheet", target=target)
    try:
        c=wb[sh][addr]
        if not hasattr(c,"coordinate"): raise ValueError()
    except Exception: fail("invalid single-cell address", target=target)
    return sh,c.coordinate
def left_label(ws,row,col):
    for j in range(col-1,0,-1):
        x=ws.cell(row,j).value
        if isinstance(x,str) and x.strip(): return norm(x)
    return ""
def header_text(ws,row,col):
    for i in range(row-1,0,-1):
        x=ws.cell(i,col).value
        if isinstance(x,str) and x.strip(): return norm(x)
    return ""
def year_above(ws,row,col):
    for i in range(row-1,0,-1):
        m=YEAR_RE.search(str(ws.cell(i,col).value or ""))
        if m: return int(m.group(1))
    return None
def is_rate_sheet(ws):
    title=norm(ws.title)
    return any(x in title for x in ("yoy","year over year","change","growth","percent","percentage","rate"))
def is_budget_sheet(ws):
    t=norm(ws.title)
    return "budget" in t and not is_rate_sheet(ws)
def displayed_decimals(fmt):
    # Count mandatory/optional decimal placeholders in the first numeric section.
    first=(fmt or "").split(";")[0]
    m=re.search(r"[0#]+\.([0#]+)", first)
    return len(m.group(1)) if m else None
def rounded_for_cell(value, cell):
    d=displayed_decimals(cell.number_format)
    return round(value,d) if d is not None else value
def label_score(target, source):
    if not target or not source: return 0
    if target==source: return 3
    # Only accept a containment relation after removing generic reporting words.
    stop={"nasa","budget","total","amount","program","funding","funds"}
    a=" ".join(x for x in target.split() if x not in stop)
    b=" ".join(x for x in source.split() if x not in stop)
    return 1 if a and b and (a in b or b in a) else 0

def inspect(wb, marker):
    sheets=[]; formulas=[]
    for ws in wb.worksheets:
        cells=[]
        for row in ws.iter_rows():
            for c in row:
                if c.value is None: continue
                e={"coordinate":c.coordinate,"value":val(c.value),"data_type":c.data_type,"number_format":c.number_format}
                if c.data_type=="f": formulas.append({"cell":f"{ws.title}!{c.coordinate}","formula":c.value})
                cells.append(e)
        sheets.append({"name":ws.title,"max_row":ws.max_row,"max_column":ws.max_column,
          "merged_ranges":[str(x) for x in ws.merged_cells.ranges],"hidden_rows":[i for i,d in ws.row_dimensions.items() if d.hidden],
          "hidden_columns":[i for i,d in ws.column_dimensions.items() if d.hidden],"nonempty_cells":cells})
    return {"ok":True,"marker":marker,"marker_count":len(targets(wb,marker)),"targets":targets(wb,marker),"sheet_names":wb.sheetnames,"sheets":sheets,"formulas":formulas}

def budget_candidates(wb, label, year):
    ans=[]
    for ws in wb.worksheets:
        if not is_budget_sheet(ws): continue
        for row in ws.iter_rows():
            for c in row:
                if not number(c.value) or year_above(ws,c.row,c.column)!=year: continue
                score=label_score(label,left_label(ws,c.row,c.column))
                if score: ans.append((score,ws.title,c.coordinate,float(c.value),left_label(ws,c.row,c.column)))
    return ans
def unique_best(candidates):
    if not candidates: return None
    best=max(x[0] for x in candidates); chosen=[x for x in candidates if x[0]==best]
    values={round(x[3],12) for x in chosen}
    return chosen[0] if len(values)==1 else None

def simple_formula_repairs(wb, cached, marker):
    ans={}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for total in row:
                if not isinstance(total.value,str): continue
                m=SUM_RE.match(total.value)
                if not m: continue
                try: minc,minr,maxc,maxr=range_boundaries(m.group(1).replace("$",""))
                except ValueError: continue
                # A simple one-dimensional SUM with exactly one unknown component.
                components=[ws.cell(r,c) for r in range(minr,maxr+1) for c in range(minc,maxc+1)]
                unknown=[c for c in components if c.value==marker]
                cached_total=cached[ws.title][total.coordinate].value
                known=[c.value for c in components if c.value!=marker]
                if len(unknown)==1 and number(cached_total) and all(number(x) for x in known):
                    key=f"{ws.title}!{unknown[0].coordinate}"
                    ans[key]=(float(cached_total)-sum(float(x) for x in known), {"kind":"cached_simple_sum","formula_cell":f"{ws.title}!{total.coordinate}","formula":total.value,"cached_total":cached_total})
    return ans
def repeated_repairs(wb, marker):
    facts={}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if number(c.value):
                    key=(left_label(ws,c.row,c.column),header_text(ws,c.row,c.column))
                    if all(key): facts.setdefault(key,[]).append((ws.title,c.coordinate,float(c.value)))
    ans={}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value!=marker: continue
                key=(left_label(ws,c.row,c.column),header_text(ws,c.row,c.column)); other=[x for x in facts.get(key,[]) if x[0]!=ws.title]
                values={round(x[2],12) for x in other}
                if all(key) and len(values)==1:
                    ans[f"{ws.title}!{c.coordinate}"]=(other[0][2], {"kind":"repeated_labeled_fact","source":f"{other[0][0]}!{other[0][1]}","row_label":key[0],"column_label":key[1]})
    return ans
def yoy_repairs(wb, marker):
    ans={}
    for ws in wb.worksheets:
        if not is_rate_sheet(ws): continue
        for row in ws.iter_rows():
            for c in row:
                if c.value!=marker: continue
                label=left_label(ws,c.row,c.column); year=year_above(ws,c.row,c.column)
                if not label or year is None: continue
                current=unique_best(budget_candidates(wb,label,year)); prior=unique_best(budget_candidates(wb,label,year-1))
                if not current or not prior or prior[3]==0: continue
                rate=100.0*(current[3]-prior[3])/prior[3]
                # Excel percentage formats store 4.79% as 0.0479; ordinary 0.00 stores 4.79.
                if "%" in (c.number_format or ""): rate/=100.0
                rate=rounded_for_cell(rate,c)
                ans[f"{ws.title}!{c.coordinate}"]=(rate,{"kind":"budget_yoy_change","entity":label,"year":year,"current_source":f"{current[1]}!{current[2]}","current":current[3],"prior_source":f"{prior[1]}!{prior[2]}","prior":prior[3],"formula":"100 * (current - prior) / prior","label_match_scores":[current[0],prior[0]]})
    return ans
def derive(wb, marker, input_path):
    cached=load(input_path,True); found={}
    # Formula evidence has priority, then exact repeated facts, then rate evidence.
    for source in (simple_formula_repairs(wb,cached,marker), repeated_repairs(wb,marker), yoy_repairs(wb,marker)):
        for key,item in source.items():
            if key not in found: found[key]=item
    repairs={}; evidence=[]
    for key,(x,e) in sorted(found.items()):
        if number(x): repairs[key]=x; evidence.append(dict(target=key,value=x,**e))
    unresolved=sorted(set(targets(wb,marker))-set(repairs))
    return {"ok":True,"input_path":input_path,"marker":marker,"repairs":repairs,"evidence":evidence,"unresolved_targets":unresolved,"complete":not unresolved}

def snapshot(wb, excluded):
    return {f"{ws.title}!{c.coordinate}":(c.value,c.data_type) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None and f"{ws.title}!{c.coordinate}" not in excluded}
def apply(payload, repairs=None):
    marker=payload.get("marker",MARKER); inp=payload.get("input_path"); dest=payload.get("output_path")
    if not isinstance(marker,str): fail("marker must be a string")
    if not isinstance(dest,str) or not dest: fail("output_path must be a nonempty string")
    if os.path.abspath(str(inp))==os.path.abspath(dest): fail("output_path must differ from input_path")
    if not Path(dest).parent.is_dir(): fail("output directory does not exist", output_path=dest)
    wb=load(inp); raw=repairs if repairs is not None else payload.get("repairs")
    if not isinstance(raw,dict) or not raw: fail("repairs must be a nonempty object")
    original=set(targets(wb,marker)); clean={}
    for target,x in raw.items():
        if not number(x): fail("each repair value must be a finite JSON number",target=target)
        sh,addr=split(wb,target); key=f"{sh}!{addr}"
        if key in clean: fail("duplicate repair after normalization",target=target)
        if key not in original: fail("repairs may change only original marker cells",target=key)
        clean[key]=x
    partial=payload.get("allow_partial",False)
    if not isinstance(partial,bool): fail("allow_partial must be boolean")
    missing=sorted(original-set(clean))
    if missing and not partial: fail("repair set does not cover every marker",missing_targets=missing)
    before=snapshot(wb,set(clean)); formats={}
    for key,x in clean.items():
        sh,addr=key.rsplit("!",1); formats[key]=wb[sh][addr].number_format; wb[sh][addr]=x
    try: wb.save(dest)
    except Exception as e: fail("unable to save repaired workbook",detail=str(e),output_path=dest)
    afterbook=load(dest); changed=sorted(k for k in set(before)|set(snapshot(afterbook,set(clean))) if before.get(k)!=snapshot(afterbook,set(clean)).get(k))
    remaining=targets(afterbook,marker); report=[]
    for key in sorted(clean):
        sh,addr=key.rsplit("!",1); c=afterbook[sh][addr]
        report.append({"target":key,"value":val(c.value),"data_type":c.data_type,"number_format":c.number_format,"is_numeric":number(c.value),"format_preserved":c.number_format==formats[key]})
    if changed: fail("verification detected changed non-target cell values or types",changed_non_target_cells=changed)
    if remaining and not partial: fail("verification found markers after complete repair",remaining_targets=remaining)
    if any(not x["is_numeric"] or not x["format_preserved"] for x in report): fail("verification failed for repaired cell",repaired_cells=report)
    return {"ok":True,"output_path":dest,"repaired_cells":report,"remaining_targets":remaining,"non_target_value_or_type_changes":[]}
def validate(payload):
    wb=load(payload.get("input_path")); marker=payload.get("marker",MARKER)
    expected=payload.get("expected_repairs",{})
    if not isinstance(expected,dict): fail("expected_repairs must be an object")
    checked=[]
    for target in expected:
        sh,addr=split(wb,target); c=wb[sh][addr]; checked.append({"target":f"{sh}!{addr}","value":val(c.value),"data_type":c.data_type,"number_format":c.number_format,"is_numeric":number(c.value)})
    return {"ok":True,"marker":marker,"marker_count":len(targets(wb,marker)),"remaining_targets":targets(wb,marker),"checked_cells":checked}
def main():
    try: p=json.load(sys.stdin)
    except Exception as e: fail("stdin must contain one JSON object",detail=str(e))
    if not isinstance(p,dict): fail("stdin JSON must be an object")
    action=p.get("action"); marker=p.get("marker",MARKER)
    if not isinstance(marker,str): fail("marker must be a string")
    if action=="inspect": result=inspect(load(p.get("input_path")),marker)
    elif action=="derive": result=derive(load(p.get("input_path")),marker,p.get("input_path"))
    elif action=="apply": result=apply(p)
    elif action=="recover":
        d=derive(load(p.get("input_path")),marker,p.get("input_path"))
        if d["unresolved_targets"]: fail("not all markers have uniquely evidenced repairs",unresolved_targets=d["unresolved_targets"],evidence=d["evidence"])
        result=apply(p,d["repairs"]); result["derivation_evidence"]=d["evidence"]
    elif action=="validate": result=validate(p)
    else: fail("action must be inspect, derive, recover, apply, or validate")
    out(result)
if __name__=="__main__": main()
