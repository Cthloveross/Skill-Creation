#!/usr/bin/env python3
"""Policy-driven reflow calculation. Input is the JSON schema documented in SKILL.md."""
import csv, json, math, os, sys, re
from collections import defaultdict
from datetime import datetime

ALIASES={
 'run_id':['run_id','run','runid','production_run_id'],
 'tc_id':['tc_id','thermocouple_id','sensor_id','tc','thermocouple'],
 'time':['time_s','timestamp_s','timestamp','time','elapsed_s','elapsed_time_s'],
 'temperature':['temperature_c','temp_c','temperature','temp'],
 'board_family':['board_family','family','board_type'],
 'material':['solder','solder_material','alloy','material'],
 'speed':['conveyor_speed_cm_min','conveyor_speed','speed_cm_min','speed'],
}
def fail(s): raise ValueError(s)
def num(x):
    if x is None or str(x).strip()=='': return None
    s=str(x).strip().replace(',','')
    try:return float(s)
    except: return None
def stamp(x):
    n=num(x)
    if n is not None:return n
    s=str(x).strip().replace('Z','+00:00')
    try:return datetime.fromisoformat(s).timestamp()
    except: pass
    try:
        a=s.split(':'); return int(a[0])*3600+int(a[1])*60+float(a[2])
    except: return None
def rnd(x): return None if x is None or not math.isfinite(x) else round(x+0.0,2)
def readcsv(path):
    with open(path,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f)), (csv.DictReader if False else None)
def cmap(rows, supplied, needed):
    if not rows: return {k:(supplied or {}).get(k) for k in needed}
    heads=list(rows[0]); low={h.strip().lower():h for h in heads}; out={}
    for k in needed:
        given=(supplied or {}).get(k)
        if given:
            if given not in heads: fail('Configured column '+given+' not present')
            out[k]=given; continue
        out[k]=next((low[a] for a in ALIASES.get(k,[]) if a in low),None)
        if not out[k]: fail('Cannot resolve required '+k+' column; configure columns explicitly')
    return out
def select(items, rule, value=lambda x:x[1]):
    if not items:return None
    items=sorted(items,key=lambda z:str(z[0]))
    vals=[(a,value(x)) for a,x in items if value(x) is not None]
    if not vals:return None
    if rule.startswith('tc_id:'):
        want=rule[6:]; return next((x for x in items if str(x[0])==want),None)
    if rule=='max': return max(vals,key=lambda z:(z[1],str(z[0])))
    if rule=='min': return min(vals,key=lambda z:(z[1],str(z[0])))
    if rule=='median':
        vals.sort(key=lambda z:(z[1],str(z[0]))); return vals[(len(vals)-1)//2]
    fail('Unknown representative selector '+str(rule))
def material_value(policy, material, base, mapping):
    d=policy.get(mapping,{})
    return d.get(str(material),policy.get(base))
def interval_ok(x, lo, hi, inclusive=True):
    if x is None:return False
    return (x>=lo and x<=hi) if inclusive else (x>lo and x<hi)
def tal(points, threshold):
    total=0.0
    for (t1,y1),(t2,y2) in zip(points,points[1:]):
        if t2<=t1: continue
        a=y1>threshold; b=y2>threshold
        if a and b: total+=t2-t1
        elif a!=b and y2!=y1:
            cross=t1+(t2-t1)*(threshold-y1)/(y2-y1)
            total+=(cross-t1 if a else t2-cross)
    return total
def preheat(points,p):
    ans=[]; lo,hi=p['lower_c'],p['upper_c']
    for (t1,y1),(t2,y2) in zip(points,points[1:]):
        if t2<=t1:continue
        if p.get('segment_mode','within')=='within':
            if not (lo<=y1<=hi and lo<=y2<=hi):continue
        elif p.get('segment_mode')=='clip':
            # A monotonic line intersects the closed temperature band iff its range overlaps it.
            if max(min(y1,y2),lo)>min(max(y1,y2),hi):continue
        else: fail('Unknown preheat segment_mode')
        r=(y2-y1)/(t2-t1); mode=p.get('ramp_mode','heating')
        if mode=='heating':
            if r<0:continue
        elif mode=='absolute':r=abs(r)
        elif mode!='signed':fail('Unknown ramp_mode')
        ans.append(r)
    return max(ans) if ans else None
def main():
 try:
    q=json.load(sys.stdin); paths=q['paths']; pol=q['policy']
    for section in ('preheat','tal','peak','conveyor','ranking'):
        if section not in pol:fail('Missing policy.'+section)
    for k in ('lower_c','upper_c','ramp_limit_c_per_s'):
        if k not in pol['preheat']:fail('Missing preheat.'+k)
    for k in ('min_s','max_s'):
        if k not in pol['tal']:fail('Missing tal.'+k)
    if 'liquidus_c' not in pol['tal'] and not pol['tal'].get('liquidus_by_material'):fail('No TAL liquidus')
    if 'required_min_c' not in pol['peak'] and not pol['peak'].get('required_min_by_material'):fail('No peak requirement')
    for k in ('heated_length_cm','max_dwell_s'):
        if k not in pol['conveyor']:fail('Missing conveyor.'+k)
    tc,_=readcsv(paths['thermocouples']); mes,_=readcsv(paths['mes']); defects,_=readcsv(paths.get('defects','/dev/null')) if paths.get('defects') else ([],None)
    cols=q.get('columns',{}); ct=cmap(tc,cols.get('thermocouples'),['run_id','tc_id','time','temperature']); cm=cmap(mes,cols.get('mes'),['run_id','board_family','material','speed'])
    cd=cmap(defects,cols.get('defects'),['run_id']) if defects else {'run_id':None}
    runs={}
    for r in mes:
        rid=str(r[cm['run_id']]).strip()
        if rid in runs:fail('Duplicate MES run_id '+rid)
        runs[rid]=r
    traces=defaultdict(list)
    for r in tc:
        rid=str(r.get(ct['run_id'],'')).strip(); sid=str(r.get(ct['tc_id'],'')).strip(); t=stamp(r.get(ct['time'])); y=num(r.get(ct['temperature']))
        if rid and sid and t is not None and y is not None: traces[(rid,sid)].append((t,y))
    for k in list(traces):
        # duplicate timestamp is unusable; retain no arbitrary row
        p=sorted(traces[k]); traces[k]=[x for i,x in enumerate(p) if (i==0 or x[0]!=p[i-1][0])]
        if len(traces[k])<2:del traces[k]
    byrun=defaultdict(list)
    for (rid,sid),pts in traces.items(): byrun[rid].append((sid,pts))
    def mat(rid):return runs.get(rid,{}).get(cm['material'],'')
    # Q1
    q1map={}; violations=[]
    for rid in sorted(runs):
        vals=[(sid,preheat(pts,pol['preheat'])) for sid,pts in byrun.get(rid,[])]
        pick=select(vals,pol['preheat'].get('representative','max'))
        if pick is None: q1map[rid]={'tc_id':None,'max_preheat_ramp_c_per_s':None}
        else:
            q1map[rid]={'tc_id':pick[0],'max_preheat_ramp_c_per_s':rnd(pick[1])}
            if pick[1] > float(pol['preheat']['ramp_limit_c_per_s']):violations.append(rid)
    q1={'ramp_rate_limit_c_per_s':rnd(float(pol['preheat']['ramp_limit_c_per_s'])),'violating_runs':violations,'max_ramp_by_run':q1map}
    # Q2
    q2=[]
    for rid in sorted(runs):
        threshold=material_value(pol['tal'],mat(rid),'liquidus_c','liquidus_by_material')
        if threshold is None:fail('No liquidus for material '+str(mat(rid)))
        vals=[(sid,tal(pts,float(threshold))) for sid,pts in byrun.get(rid,[])]
        scope=pol['tal'].get('output_scope','all')
        use=vals if scope=='all' else ([select(vals,pol['tal'].get('representative','min'))] if select(vals,pol['tal'].get('representative','min')) else [])
        for sid,v in use:
            ok=interval_ok(v,float(pol['tal']['min_s']),float(pol['tal']['max_s']),pol['tal'].get('inclusive',True))
            q2.append({'run_id':rid,'tc_id':sid,'tal_s':rnd(v),'required_min_tal_s':rnd(float(pol['tal']['min_s'])),'required_max_tal_s':rnd(float(pol['tal']['max_s'])),'status':'compliant' if ok else 'non-compliant'})
    # Q3
    q3map={}; failing=[]
    for rid in sorted(runs):
        req=material_value(pol['peak'],mat(rid),'required_min_c','required_min_by_material')
        if req is None:fail('No peak requirement for material '+str(mat(rid)))
        vals=[(sid,max(y for t,y in pts)) for sid,pts in byrun.get(rid,[])]
        pick=select(vals,pol['peak'].get('representative','min'))
        if pick is None:
            q3map[rid]={'tc_id':None,'peak_temp_c':None,'required_min_peak_c':rnd(float(req))}; failing.append(rid)
        else:
            q3map[rid]={'tc_id':pick[0],'peak_temp_c':rnd(pick[1]),'required_min_peak_c':rnd(float(req))}
            if pick[1] < float(req):failing.append(rid)
    q3={'failing_runs':failing,'min_peak_by_run':q3map}
    # Q4
    c=pol['conveyor']; dwell=float(c['max_dwell_s']);
    if dwell<=0:fail('max_dwell_s must be positive')
    required=float(c['heated_length_cm'])/dwell*60; q4=[]
    for rid in sorted(runs):
        actual=num(runs[rid].get(cm['speed'])); ok=actual is not None and actual>=required
        if c.get('machine_min_speed_cm_min') is not None:ok=ok and actual>=float(c['machine_min_speed_cm_min'])
        if c.get('machine_max_speed_cm_min') is not None:ok=ok and actual<=float(c['machine_max_speed_cm_min'])
        q4.append({'run_id':rid,'required_min_speed_cm_min':rnd(required),'actual_speed_cm_min':rnd(actual),'meets':bool(ok)})
    # Q5 aggregate stated ranking fields
    rules=pol['ranking'].get('rules',[])
    if not rules:fail('No handbook-derived ranking rules')
    drows=defaultdict(list)
    for r in defects:drows[str(r.get(cd['run_id'],'')).strip()].append(r)
    def metric(rid, rule):
        source=rule.get('source'); field=rule.get('field'); rows=[runs[rid]] if source=='mes' else drows[rid] if source=='defects' else None
        if rows is None:fail('ranking source must be mes or defects')
        if rule.get('aggregate')=='count':return float(len(rows))
        vals=[num(x.get(field)) for x in rows]; vals=[x for x in vals if x is not None]
        if not vals:return None
        agg=rule.get('aggregate','mean' if source=='mes' else 'sum')
        return {'sum':sum(vals),'mean':sum(vals)/len(vals),'min':min(vals),'max':max(vals)}.get(agg) if agg in ('sum','mean','min','max') else fail('Bad ranking aggregate')
    fam=defaultdict(list)
    for rid,r in runs.items():fam[str(r.get(cm['board_family'],'')).strip()].append(rid)
    q5=[]
    for family,ids in sorted(fam.items()):
        def key(rid):
            out=[]
            for rule in rules:
                v=metric(rid,rule); direction=rule.get('direction')
                if direction not in ('asc','desc'):fail('ranking direction must be asc or desc')
                # Missing evidence ranks after usable evidence; no invented favorable value.
                out.append((v is None, (v if direction=='asc' else -v) if v is not None else 0))
            return tuple(out)+(rid,)
        ids=sorted(ids,key=key); q5.append({'board_family':family,'best_run_id':ids[0] if ids else None,'runner_up_run_ids':ids[1:]})
    out=paths.get('output_dir','/app/output');os.makedirs(out,exist_ok=True)
    for name,obj in [('q01.json',q1),('q02.json',q2),('q03.json',q3),('q04.json',q4),('q05.json',q5)]:
        with open(os.path.join(out,name),'w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'output_dir':out,'files':['q01.json','q02.json','q03.json','q04.json','q05.json']}))
 except Exception as e:
    print(json.dumps({'error':str(e)})); sys.exit(1)
if __name__=='__main__':main()
