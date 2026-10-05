#!/usr/bin/env python3
"""Run ACC using runtime-loaded tuning gains and write CSV plus measured report."""
import argparse, csv, math, statistics, yaml
from pathlib import Path
from acc_system import AdaptiveCruiseControl
FIELDS = ["time","ego_speed","acceleration_cmd","mode","distance_error","distance","ttc"]
def number(value):
    if value is None or str(value).strip() == "": return None
    x=float(value)
    if not math.isfinite(x): raise ValueError("non-finite sensor value")
    return x
def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd=csv.DictReader(f)
        if not rd.fieldnames or any(k not in rd.fieldnames for k in ("time","ego_speed","lead_speed","distance")): raise ValueError("sensor CSV lacks required columns")
        rows=[]; last=None
        for n,r in enumerate(rd,2):
            t=number(r["time"])
            if t is None or (last is not None and t<=last): raise ValueError(f"invalid timestamp at sensor row {n}")
            lead,dist=number(r["lead_speed"]),number(r["distance"])
            if (lead is None)!=(dist is None): raise ValueError(f"incomplete lead observation at sensor row {n}")
            if dist is not None and dist<0: raise ValueError(f"negative lead distance at sensor row {n}")
            rows.append({"time":t,"lead_speed":lead,"distance":dist}); last=t
    if not rows: raise ValueError("sensor CSV has no data rows")
    return rows
def config_with_gains(config,gains):
    result=dict(config); result["_pid_gains"]=gains; return result
def simulate_rows(rows, config):
    acc=AdaptiveCruiseControl(config)
    initial=config.get("initial_speed", config.get("vehicle",{}).get("initial_speed",0.0))
    ego=max(0.0,float(initial)); output=[]
    for i,row in enumerate(rows):
        dt=(rows[i+1]["time"]-row["time"]) if i+1<len(rows) else (rows[i]["time"]-rows[i-1]["time"] if i else .1)
        if dt<=0: raise ValueError("non-positive dt")
        cmd,mode,err=acc.compute(ego,row["lead_speed"],row["distance"],dt)
        output.append({"time":row["time"],"ego_speed":ego,"acceleration_cmd":cmd,"mode":mode,"distance_error":err,"distance":row["distance"] if mode!="cruise" else None,"ttc":acc.last_ttc})
        ego=max(0.0, ego+cmd*dt)
    return output
def fmt(x): return "" if x is None else f"{x:.6f}"
def report(trace, acc, path):
    cruise=[r for r in trace if r["mode"]=="cruise"]; follow=[r for r in trace if r["mode"]!="cruise"]
    rise=next((r["time"] for r in cruise if r["ego_speed"]>=.9*acc.set_speed),None)
    overshoot=(max((r["ego_speed"] for r in cruise),default=acc.set_speed)-acc.set_speed)/acc.set_speed*100
    tail=cruise[-100:]; speed_sse=statistics.fmean(abs(r["ego_speed"]-acc.set_speed) for r in tail) if tail else None
    d_tail=follow[-100:]; dist_sse=statistics.fmean(abs(r["distance_error"]) for r in d_tail) if d_tail else None
    gaps=[r["distance"] for r in follow if r["distance"] is not None]
    val=lambda x:"N/A" if x is None else f"{x:.3f}"
    lines=["# ACC Simulation Report","","## System design","","The controller has mutually exclusive cruise, follow, and TTC-priority emergency modes. Cruise uses the speed PID. Follow uses a separate distance PID with `d_safe = 1.5 * ego_speed + 10.0` unless overridden by configuration. Commands are physically clamped, speed is nonnegative, controller state resets at mode transitions, and emergency commands maximum configured braking.","","## PID tuning methodology and final gains","",f"A deterministic bounded grid search on the supplied sensor trace selected: speed `{acc.speed_pid.kp:.4g}, {acc.speed_pid.ki:.4g}, {acc.speed_pid.kd:.4g}`; distance `{acc.distance_pid.kp:.4g}, {acc.distance_pid.ki:.4g}, {acc.distance_pid.kd:.4g}` (kp, ki, kd). The simulator loads these from `tuning_results.yaml` at runtime.","","## Simulation results and performance metrics","",f"Records: {len(trace)}; duration: {trace[-1]['time']-trace[0]['time']:.3f} s.",f"Cruise rise time to 90%: {val(rise)} s (target <10 s).",f"Cruise overshoot: {overshoot:.3f}% (target <5%).",f"Cruise tail mean absolute speed error: {val(speed_sse)} m/s (target <0.5 m/s).",f"Follow tail mean absolute distance error: {val(dist_sse)} m (target <2 m).",f"Minimum observed lead distance: {val(min(gaps) if gaps else None)} m (target >5 m)."]
    Path(path).write_text("\n".join(lines)+"\n",encoding="utf-8")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--sensor",required=True); ap.add_argument("--config",required=True); ap.add_argument("--tuning",required=True); ap.add_argument("--output",required=True); ap.add_argument("--report",required=True); a=ap.parse_args()
    rows=load_rows(a.sensor); base=yaml.safe_load(Path(a.config).read_text()) or {}; gains=yaml.safe_load(Path(a.tuning).read_text()) or {}
    if not all(k in gains for k in ("pid_speed","pid_distance")): raise ValueError("tuning file missing PID sections")
    config=config_with_gains(base,gains); trace=simulate_rows(rows,config)
    with open(a.output,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader()
        for r in trace: w.writerow({k:fmt(r[k]) if k!="mode" else r[k] for k in FIELDS})
    report(trace,AdaptiveCruiseControl(config),a.report)
if __name__=="__main__": main()
