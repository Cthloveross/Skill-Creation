#!/usr/bin/env python3
"""JSON-stdin entrypoint for the ecommerce anomaly/DiD artifact pipeline."""
import sys, json, os, re, math
from pathlib import Path
import numpy as np
import pandas as pd

BASE0, BASE1, TREAT0, TREAT1 = "2020-01-01", "2020-02-29", "2020-03-01", "2020-03-31"

def norm_header(x):
    return re.sub(r"[^a-z0-9]+", "_", str(x).strip().lower()).strip("_")
def safe_name(x):
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(x)).strip("_")[:100] or "value"
def clean_text(s):
    return s.astype("string").fillna("").str.strip().str.replace(r"\s+", " ", regex=True)
def read_csv(path):
    # utf-8-sig handles Excel CSVs; fallback permits legacy exports.
    try: return pd.read_csv(path, dtype="string", encoding="utf-8-sig")
    except UnicodeDecodeError: return pd.read_csv(path, dtype="string", encoding="latin1")
def pick(cols, choices, label):
    lookup = {norm_header(c): c for c in cols}
    for x in choices:
        if x in lookup: return lookup[x]
    # only accept a unique semantic partial match, never arbitrary first column
    hits = [c for n,c in lookup.items() if any(x in n or n in x for x in choices)]
    if len(set(hits)) == 1: return hits[0]
    raise ValueError("Cannot uniquely identify %s column; available columns: %s" % (label, list(cols)))
def num(s):
    return pd.to_numeric(clean_text(s).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")
def dates(s):
    # Task dates are US-oriented; pandas also recognizes ISO exports.
    return pd.to_datetime(clean_text(s), errors="coerce")
def finite(x):
    x = float(x)
    return x if math.isfinite(x) else 0.0

def find_shared_id(survey, purchase):
    candidates = ["survey_responseid","survey_response_id","responseid","response_id","customer_id","customerid","user_id","userid","client_id"]
    scols, pcols = {norm_header(c):c for c in survey.columns}, {norm_header(c):c for c in purchase.columns}
    pairs = [(scols[x],pcols[x]) for x in candidates if x in scols and x in pcols]
    if pairs: return pairs[0]
    # If vendor changed header labels, choose the declared identifier pair with greatest overlap.
    ss = [c for n,c in scols.items() if any(k in n for k in ("response","customer","user","client")) and "id" in n]
    ps = [c for n,c in pcols.items() if any(k in n for k in ("response","customer","user","client")) and "id" in n]
    scored=[]
    for a in ss:
        av=set(clean_text(survey[a]))-{""}
        for b in ps:
            bv=set(clean_text(purchase[b]))-{""}
            scored.append((len(av & bv),a,b))
    if scored and max(scored)[0] > 0:
        _,a,b=max(scored); return a,b
    raise ValueError("No shared stable survey/purchase identifier could be found")

def clean_inputs(survey_path, purchase_path):
    s0, p0 = read_csv(survey_path), read_csv(purchase_path)
    sid, pid = find_shared_id(s0,p0)
    s = s0.copy(); s.columns=[str(c).strip() for c in s.columns]
    s["Survey ResponseID"] = clean_text(s[sid])
    s = s[s["Survey ResponseID"] != ""].copy()
    # Deterministically retain the most populated record for each respondent.
    completeness=s.replace("", pd.NA).notna().sum(axis=1)
    s = s.assign(_complete=completeness).sort_values(["Survey ResponseID","_complete"], ascending=[True,False], kind="mergesort")
    s = s.drop_duplicates("Survey ResponseID", keep="first").drop(columns="_complete")
    pdate=pick(p0.columns,["order_date","purchase_date","transaction_date","date","orderdate"],"purchase date")
    pcat=pick(p0.columns,["product_category","category","productcategory","product_type","department"],"category")
    pamt=pick(p0.columns,["purchase_price","total_spend","amount","sales","price","order_total","spend"],"spend")
    p=pd.DataFrame({"Survey ResponseID":clean_text(p0[pid]), "Purchase_Date":dates(p0[pdate]),
                    "Category":clean_text(p0[pcat]), "Spend":num(p0[pamt])})
    p=p[(p["Survey ResponseID"]!="") & p["Purchase_Date"].notna() & (p["Category"]!="") & p["Spend"].notna() & (p["Spend"]>=0)].copy()
    p=p[p["Survey ResponseID"].isin(set(s["Survey ResponseID"]))].copy()
    p["Purchase_Date"]=p["Purchase_Date"].dt.normalize()
    p["Spend"]=p["Spend"].astype(float)
    p=p.drop_duplicates(["Survey ResponseID","Purchase_Date","Category","Spend"]).sort_values(["Purchase_Date","Survey ResponseID","Category"],kind="mergesort")
    if p.empty: raise ValueError("No valid linked purchase rows remain after cleaning")
    return s.reset_index(drop=True),p.reset_index(drop=True)

def features(s):
    out=pd.DataFrame({"Survey ResponseID":s["Survey ResponseID"].astype(str)})
    used=set()
    for c in s.columns:
        if c=="Survey ResponseID": continue
        v=clean_text(s[c]); n=num(v); nonblank=(v!="").sum()
        if nonblank==0: continue
        stem=safe_name(c)
        if n.notna().sum() >= max(3, int(.85*nonblank)) and n.nunique(dropna=True)>1:
            med=float(n.median()); z=n.fillna(med); sd=float(z.std(ddof=0))
            name="num__"+stem
            out[name]=(z-z.mean())/sd if sd>0 else 0.0
            out["missing__"+stem]=n.isna().astype(int)
        else:
            # Text/question-answer fields with nearly respondent-level uniqueness are not demographics.
            vv=v.mask(v=="", "__MISSING__").str.casefold()
            counts=vv.value_counts(dropna=False)
            levels=sorted([x for x,nc in counts.items() if nc>=2])
            if len(levels)<2 or len(levels)>20: continue
            for lev in levels:
                name="cat__%s__%s"%(stem,safe_name(lev))
                if name in used: continue
                out[name]=(vv==lev).astype(int); used.add(name)
    cols=[c for c in out.columns if c!="Survey ResponseID" and out[c].nunique()>1]
    out=out[["Survey ResponseID"]+cols]
    if not cols: raise ValueError("No usable demographic features after cleaning")
    return out

def anomaly_index(p):
    cutoff=pd.Timestamp(TREAT0); end=pd.Timestamp(TREAT1)
    cats=sorted(p["Category"].unique())
    records=[]
    for cat in cats:
        q=p[p.Category==cat].groupby("Purchase_Date").Spend.sum()
        hist=q[q.index<cutoff]
        march=q[(q.index>=cutoff)&(q.index<=end)]
        if hist.empty:
            records.append((cat,0.0)); continue
        all_days=pd.date_range(hist.index.min(), end, freq="D")
        y=hist.reindex(pd.date_range(hist.index.min(), cutoff-pd.Timedelta(days=1),freq="D"),fill_value=0.0).astype(float)
        d=y.index; t=(d-d.min()).days.astype(float)
        X=np.column_stack([np.ones(len(d)), t/max(float(t.max()),1), pd.get_dummies(d.dayofweek).reindex(columns=range(7),fill_value=0).to_numpy()[:,1:]])
        if len(y)<14: records.append((cat,0.0)); continue
        beta=np.linalg.lstsq(X,y.to_numpy(),rcond=None)[0]
        rmse=float(np.sqrt(np.mean((y.to_numpy()-X@beta)**2)))
        md=pd.date_range(cutoff,end,freq="D"); mt=(md-d.min()).days.astype(float)
        MX=np.column_stack([np.ones(len(md)),mt/max(float(t.max()),1),pd.get_dummies(md.dayofweek).reindex(columns=range(7),fill_value=0).to_numpy()[:,1:]])
        actual=march.reindex(md,fill_value=0.0).to_numpy(float)
        z=(actual-MX@beta).mean()/(rmse/max(math.sqrt(len(md)),1) if rmse>1e-9 else max(np.std(y),1.0)/math.sqrt(len(md)))
        records.append((cat,finite(100*math.tanh(float(z)/3.0))))
    return pd.DataFrame(records,columns=["Category","Anomaly_Index"]).sort_values(["Anomaly_Index","Category"],ascending=[False,True],kind="mergesort")

def ols(y,X):
    y=np.asarray(y,float); X=np.asarray(X,float); n=len(y); rank=np.linalg.matrix_rank(X)
    b=np.linalg.pinv(X)@y; resid=y-X@b; dof=max(n-rank,1)
    cov=(float(resid@resid)/dof)*np.linalg.pinv(X.T@X)
    se=np.sqrt(np.maximum(np.diag(cov),0)); p=np.array([math.erfc(abs(bi/si)/math.sqrt(2)) if si>1e-12 else 1.0 for bi,si in zip(b,se)])
    return b,p

def choose_independent(F, names, nmax):
    keep=[]; cur=np.ones((len(F),1))
    for j,name in enumerate(names):
        if len(keep)>=nmax: break
        test=np.column_stack([cur,F[:,j]])
        if np.linalg.matrix_rank(test)>np.linalg.matrix_rank(cur): keep.append(j);cur=test
    return keep

def category_report(cat, score, panel, feat):
    z=panel.merge(feat,on="Survey ResponseID",how="left",validate="many_to_one")
    fcols=[c for c in feat.columns if c!="Survey ResponseID"]
    F=z[fcols].fillna(0).to_numpy(float); T=(z.Period=="treatment").astype(float).to_numpy()
    # conditional purchases define intensive margin
    active=z.Has_Purchase.to_numpy(int)==1
    intensive=[]
    for j,name in enumerate(fcols):
        idx=active & (np.std(F[:,j])>0)
        if idx.sum()>=8 and np.std(F[idx,j])>0:
            b,pv=ols(z.loc[idx,"Total_Spend"],np.column_stack([np.ones(idx.sum()),T[idx],F[idx,j],T[idx]*F[idx,j]]))
            intensive.append({"feature":name,"did_estimate":finite(b[3]),"p_value":finite(pv[3]),"method":"Univariate DiD"})
    # Multivariate model: retain identifiable features and enough observations for interaction terms.
    keep=choose_independent(F,fcols,max(1,(len(z)-4)//2)); extensive=[]
    if keep:
        FF=F[:,keep]; X=np.column_stack([np.ones(len(z)),T,FF,T[:,None]*FF]); b,pv=ols(z.Has_Purchase,X)
        k=len(keep)
        extensive=[{"feature":fcols[j],"did_estimate":finite(b[2+k+i]),"p_value":finite(pv[2+k+i]),"method":"Multivariate Heterogeneous DiD"} for i,j in enumerate(keep)]
    reverse=score>=0
    intensive=sorted(intensive,key=lambda x:(x["did_estimate"],x["feature"]),reverse=reverse)[:3]
    extensive=sorted(extensive,key=lambda x:(x["did_estimate"],x["feature"]),reverse=reverse)[:3]
    def metrics(period):
        a=z[z.Period==period]; buyers=a[a.Has_Purchase==1]
        return (finite(buyers.Total_Spend.mean()) if len(buyers) else 0.0, int(len(buyers)), finite(a.Has_Purchase.mean()))
    ba,bn,br=metrics("baseline"); ta,tn,tr=metrics("treatment")
    return {"category":str(cat),"anomaly_index":finite(score),"baseline_avg_spend":ba,"treatment_avg_spend":ta,"n_purchasers_baseline":bn,"n_purchasers_treatment":tn,"baseline_purchase_rate":br,"treatment_purchase_rate":tr,"n_at_risk":int(z["Survey ResponseID"].nunique()),"intensive_margin":intensive,"extensive_margin":extensive}

def validate(out, survey, anom, ip, ep, report):
    required=["survey_cleaned.csv","amazon-purchases-2019-2020-filtered.csv","category_anomaly_index.csv","survey_feature_engineered.csv","user_category_period_aggregated_intensive.csv","user_category_period_aggregated_extensive.csv","causal_analysis_report.json"]
    if not all((out/x).is_file() for x in required): raise ValueError("Required artifact was not written")
    if survey["Survey ResponseID"].duplicated().any(): raise ValueError("Survey IDs are not unique")
    if list(anom.columns)!=["Category","Anomaly_Index"] or not np.isfinite(anom.Anomaly_Index).all(): raise ValueError("Invalid anomaly artifact")
    for d,col in ((ip,"Total_Spend"),(ep,"Has_Purchase")):
        if list(d.columns) != ["Survey ResponseID","Category","Period",col] or d.duplicated(["Survey ResponseID","Category","Period"]).any(): raise ValueError("Invalid panel artifact")
    for group,descending in ((report["surge_categories"],True),(report["slump_categories"],False)):
        for r in group:
            for key in ("intensive_margin","extensive_margin"):
                vals=[x["did_estimate"] for x in r[key]]
                if vals != sorted(vals,reverse=descending): raise ValueError("Driver ordering invalid")

def run(cfg):
    out=Path(cfg.get("output_dir","/app/output")); out.mkdir(parents=True,exist_ok=True)
    survey,purch=clean_inputs(cfg.get("survey_path","/app/data/survey_dirty.csv"),cfg.get("purchase_path","/app/data/amazon-purchases-2019-2020_dirty.csv"))
    feat=features(survey); anom=anomaly_index(purch)
    n=min(10,len(anom)); surge=anom.head(n); slump=anom.tail(n).sort_values(["Anomaly_Index","Category"],kind="mergesort")
    selected=pd.concat([surge,slump]).drop_duplicates("Category"); cats=selected.Category.tolist(); users=survey["Survey ResponseID"].tolist()
    grid=pd.MultiIndex.from_product([users,cats,["baseline","treatment"]],names=["Survey ResponseID","Category","Period"]).to_frame(index=False)
    pp=purch[(purch.Purchase_Date>=pd.Timestamp(BASE0))&(purch.Purchase_Date<=pd.Timestamp(TREAT1))].copy()
    pp["Period"]=np.where(pp.Purchase_Date<pd.Timestamp(TREAT0),"baseline","treatment")
    agg=pp[pp.Category.isin(cats)].groupby(["Survey ResponseID","Category","Period"],as_index=False).Spend.sum().rename(columns={"Spend":"Total_Spend"})
    ip=grid.merge(agg,on=["Survey ResponseID","Category","Period"],how="left"); ip.Total_Spend=ip.Total_Spend.fillna(0.0).astype(float)
    ep=ip[["Survey ResponseID","Category","Period"]].copy(); ep["Has_Purchase"]=(ip.Total_Spend>0).astype(int)
    scoremap=dict(zip(anom.Category,anom.Anomaly_Index)); records={c:category_report(c,scoremap[c],ip[ip.Category==c],feat) for c in cats}
    sur=[records[c] for c in surge.Category if c in records]; slo=[records[c] for c in slump.Category if c in records]
    report={"metadata":{"baseline_start":"01-01-2020","baseline_end":"02-29-2020","treatment_start":"03-01-2020","treatment_end":"03-31-2020","total_features_analyzed":int(len(feat.columns)-1)},"surge_categories":sur,"slump_categories":slo,"summary":{"surge":{"total_categories":len(sur),"total_intensive_drivers":sum(len(x["intensive_margin"]) for x in sur),"total_extensive_drivers":sum(len(x["extensive_margin"]) for x in sur)},"slump":{"total_categories":len(slo),"total_intensive_drivers":sum(len(x["intensive_margin"]) for x in slo),"total_extensive_drivers":sum(len(x["extensive_margin"]) for x in slo)}}}
    survey.to_csv(out/"survey_cleaned.csv",index=False); purch.to_csv(out/"amazon-purchases-2019-2020-filtered.csv",index=False); anom.to_csv(out/"category_anomaly_index.csv",index=False); feat.to_csv(out/"survey_feature_engineered.csv",index=False); ip.to_csv(out/"user_category_period_aggregated_intensive.csv",index=False); ep.to_csv(out/"user_category_period_aggregated_extensive.csv",index=False)
    with open(out/"causal_analysis_report.json","w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
    validate(out,survey,anom,ip,ep,report)
    return {"ok":True,"output_dir":str(out),"n_survey":len(survey),"n_purchase":len(purch),"n_features":len(feat.columns)-1,"n_categories":len(anom),"n_surge":len(sur),"n_slump":len(slo)}
if __name__=="__main__":
    try:
        cfg=json.load(sys.stdin) if not sys.stdin.isatty() else {}
        print(json.dumps(run(cfg)))
    except Exception as e:
        print(json.dumps({"ok":False,"error":str(e)})); sys.exit(1)
