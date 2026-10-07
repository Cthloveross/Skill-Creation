#!/usr/bin/env python3
"""Populate a reserve-at-risk workbook using source values and Excel formulas.
The program writes no calculated result literals: price observations are copied from
an IMF source workbook and all derived results are worksheet formulas.
"""
import argparse, datetime as dt, json, math, re, shutil, sys
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

YEAR=2025

def out(x): print(json.dumps(x, indent=2, default=str))
def clean(x): return '' if x is None else str(x).strip()
def numeric(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def qsheet(s): return "'"+s.replace("'","''")+"'"
def ref(c,r,absolute=False):
    l=get_column_letter(c); return f'${l}${r}' if absolute else f'{l}{r}'
def rng(sheet,c1,r1,c2,r2): return f"{qsheet(sheet)}!${get_column_letter(c1)}${r1}:${get_column_letter(c2)}${r2}"
def key(s):
    s=clean(s).split(':',1)[0].lower()
    s=re.sub(r'[^a-z0-9]+',' ',s).strip()
    aliases={'czech republic':'czechia','kyrgyz rep':'kyrgyz republic','russian federation':'russia'}
    return aliases.get(s,s)
def country_from_heading(x):
    """Extract the geographic prefix from IMF descriptor text, including descriptors
    that omit a colon (for example, 'Czechia International Reserves')."""
    h=clean(x).split('(',1)[0].strip()
    h=h.split(':',1)[0].strip()
    stop=r'\b(?:international reserves|intl reserves|official reserve assets|foreign reserves|reserve assets|gross international reserves|gold reserves|gold volume|gold)\b'
    return re.split(stop,h,1,flags=re.I)[0].strip(' :-')

def period(x):
    """Return (year, month), accepting dates and common IMF period labels."""
    if isinstance(x,(dt.datetime,dt.date)): return x.year,x.month
    if isinstance(x,(int,float)) and not isinstance(x,bool) and int(x)==x and 1900<=x<=2100: return int(x),None
    s=clean(x)
    m=re.fullmatch(r'(\d{4})\s*[mM]0?(\d{1,2})',s)
    if m: return int(m.group(1)),int(m.group(2))
    m=re.fullmatch(r'(\d{4})[-/]?(\d{1,2})(?:[-/]\d{1,2})?',s)
    if m: return int(m.group(1)),int(m.group(2))
    for f in ('%b-%Y','%B-%Y','%Y-%b','%Y-%B'):
        try:
            d=dt.datetime.strptime(s,f); return d.year,d.month
        except ValueError: pass
    return None

def scan_template_periods(ws):
    ans={}
    for r in range(1,ws.max_row+1):
        p=period(ws.cell(r,1).value)
        if p and p[1]:
            if p in ans: raise ValueError(f'duplicate template month {p}')
            ans[p]=r
    if len(ans)<12: raise ValueError('Gold price sheet has no usable monthly period labels in column A')
    return ans

def source_series(path, require_pm=False):
    """Find the uniquely strongest monthly USD/troy-ounce gold row or column."""
    wb=load_workbook(path,data_only=True,read_only=True)
    candidates=[]
    for ws in wb.worksheets:
        # Wide time-series: a gold-labelled row, with a nearby row of date headers.
        for r in range(1,ws.max_row+1):
            label=' '.join(clean(ws.cell(r,c).value) for c in range(1,min(ws.max_column,12)+1)).lower()
            if 'gold' not in label: continue
            score_text=100 + (50 if ('troy' in label or 'ounce' in label or 'oz' in label) else 0) + (50 if ('us$' in label or 'usd' in label or 'u.s.' in label) else 0) + (30 if re.search(r'\bp\.?m\.?\b',label) else 0)
            for hr in range(max(1,r-5),min(ws.max_row,r+5)+1):
                obs=[]
                for c in range(1,ws.max_column+1):
                    p=period(ws.cell(hr,c).value); x=ws.cell(r,c).value
                    if p and p[1] and numeric(x): obs.append((p,float(x)))
                if len(obs)>=12:
                    candidates.append((score_text+len(obs),ws.title,f'row {r}, header {hr}',obs,label))
        # Vertical time-series: a gold-labelled column whose rows have dates in another column.
        for c in range(1,ws.max_column+1):
            label=' '.join(clean(ws.cell(r,c).value) for r in range(1,min(ws.max_row,12)+1)).lower()
            if 'gold' not in label: continue
            score_text=100 + (50 if ('troy' in label or 'ounce' in label or 'oz' in label) else 0) + (50 if ('us$' in label or 'usd' in label or 'u.s.' in label) else 0) + (30 if re.search(r'\bp\.?m\.?\b',label) else 0)
            for dc in range(1,min(ws.max_column,12)+1):
                obs=[]
                for r in range(1,ws.max_row+1):
                    p=period(ws.cell(r,dc).value); x=ws.cell(r,c).value
                    if p and p[1] and numeric(x): obs.append((p,float(x)))
                if len(obs)>=12: candidates.append((score_text+len(obs),ws.title,f'column {c}, dates {dc}',obs,label))
    if not candidates: raise ValueError('No dated numeric gold series was found in the supplied IMF workbook')
    # Deduplicate same coordinate/header variants and choose only an unambiguously best source.
    if require_pm:
        pm=[z for z in candidates if re.search(r'\bp\.?m\.?\b',z[4])]
        if not pm: raise ValueError('Template requests PM gold fixing but source has no explicit PM candidate')
        candidates=pm
    candidates.sort(key=lambda z:z[0],reverse=True)
    best=candidates[0]
    # Require clearly USD and troy-ounce information in its nearby label; never assume a different gold series.
    if not (('us$' in best[4] or 'usd' in best[4] or 'u.s.' in best[4]) and ('troy' in best[4] or 'ounce' in best[4] or 'oz' in best[4])):
        raise ValueError('Gold candidate is not explicitly identified as USD per troy ounce')
    vals={}
    for p,x in best[3]: vals[p]=x
    if len(vals)<12: raise ValueError('Gold candidate lacks monthly observations')
    return vals,{'sheet':best[1],'location':best[2],'label':best[4][:300],'observations':len(vals)}

def source_table(ws):
    """Discover an IMF-style table: descriptor headers by column and a 2025 data row."""
    # The annual IMF extracts identify observations by a year in their first (or
    # occasionally second) column.  Do not choose the fullest historical row.
    rows=[]
    for r in range(1,ws.max_row+1):
        p=period(ws.cell(r,1).value) or period(ws.cell(r,2).value)
        if p and p[0]==YEAR: rows.append(r)
    if len(rows)!=1: raise ValueError(f'{ws.title}: expected one 2025 observation row, found {len(rows)}')
    r=rows[0]
    headers=[]
    for c in range(1,ws.max_column+1):
        # Descriptor normally is row 1. Fall back to first descriptive text above the data row.
        h=clean(ws.cell(1,c).value)
        if not h:
            for rr in range(2,r):
                z=clean(ws.cell(rr,c).value)
                if z and not z.startswith('.'):
                    h=z; break
        headers.append(h)
    ycols=[c for c in range(1,ws.max_column+1) if clean(ws.cell(r,c).value)==str(YEAR) or (period(ws.cell(r,c).value) and period(ws.cell(r,c).value)==(YEAR,None))]
    if len(ycols)!=1: raise ValueError(f'{ws.title}: expected one literal 2025 key in its 2025 row')
    return r,ycols[0],headers

def gold_columns(ws, kind):
    r,ycol,headers=source_table(ws); records=[]
    for c,h in enumerate(headers,1):
        x=ws.cell(r,c).value; lo=h.lower()
        if not numeric(x): continue
        if kind != 'total' and 'gold' not in lo: continue
        country=country_from_heading(h)
        if not country or country.startswith('.'): continue
        if kind=='value' and not (('us$' in lo or 'usd' in lo or 'mil.us' in lo) and 'mil' in lo): continue
        if kind=='volume' and not ('troy' in lo or 'fine' in lo or 'ounce' in lo or 'oz' in lo): continue
        if kind=='total' and not (('us$' in lo or 'usd' in lo or 'mil.us' in lo) and 'reserve' in lo): continue
        records.append({'country':country,'key':key(country),'col':c,'header':h,'value':float(x)})
    d={}
    for rec in records:
        if rec['key'] in d: raise ValueError(f'{ws.title}: ambiguous country {rec["country"]}')
        d[rec['key']]=rec
    return r,ycol,d

def unit_multiplier(header):
    lo=header.lower()
    if 'thous' in lo: return 1000
    if re.search(r'\bmil(?:lion)?\b|mil\.',lo): return 1000000
    # An explicit troy-ounce label without a scale represents individual ounces.
    if 'troy' in lo or 'ounce' in lo or 'oz' in lo: return 1
    raise ValueError('cannot infer troy-ounce scale from '+header)

def find_sheet(wb, wanted):
    for ws in wb.worksheets:
        if ws.title.strip().lower()==wanted.lower(): return ws
    raise ValueError(f'missing worksheet {wanted}')

def build(template,imf,output):
    shutil.copy2(template,output)
    wb=load_workbook(output,data_only=False)
    ans=find_sheet(wb,'Answer'); price=find_sheet(wb,'Gold price'); value=find_sheet(wb,'Value'); volume=find_sheet(wb,'Volume'); total=find_sheet(wb,'Total Reserves')
    templ=scan_template_periods(price)
    # Locate B/C/D/E from visible column labels, preserving layout if formula headings are translated.
    cols={}
    for c in range(1,price.max_column+1):
        h=clean(price.cell(1,c).value).lower()
        if 'monthly log' in h: cols['ret']=c
        elif '3-month' in h and 'volatility' in h: cols['v3']=c
        elif '12-month' in h and 'volatility' in h: cols['v12']=c
        elif 'gold' in h: cols['price']=c
    for k in ('price','ret','v3','v12'):
        if k not in cols: raise ValueError('Gold price sheet missing '+k+' column label')
    require_pm=bool(re.search(r'\b(?:3\s*)?p\.?m\.?\b', clean(price.cell(1,cols['price']).value),re.I))
    series,meta=source_series(imf,require_pm=require_pm)
    missing=sorted(set(templ)-set(series))
    if missing: raise ValueError(f'IMF source lacks {len(missing)} months required by template (first {missing[:3]})')
    ordered=sorted(templ.items())
    for i,(p,r) in enumerate(ordered):
        price.cell(r,cols['price']).value=series[p]
        if i:
            price.cell(r,cols['ret']).value=f'=LN({ref(cols["price"],r)}/{ref(cols["price"],ordered[i-1][1])})*100'
        if i>=3: price.cell(r,cols['v3']).value=f'=STDEV.S({ref(cols["ret"],ordered[i-2][1])}:{ref(cols["ret"],r)})'
        if i>=12: price.cell(r,cols['v12']).value=f'=STDEV.S({ref(cols["ret"],ordered[i-11][1])}:{ref(cols["ret"],r)})'
    latestrow=ordered[-1][1]
    # Answer labels determine rows; value cells start in the column immediately right of labels.
    labels={}
    for r in range(1,ans.max_row+1):
        for c in range(1,ans.max_column+1):
            t=clean(ans.cell(r,c).value).lower().replace('\n',' ')
            if 'z-score' in t: labels['z']=(r,c)
            elif '3-month volatility annualized' in t: labels['v3a']=(r,c)
            elif '3-month volatility' in t: labels['v3']=(r,c)
            elif '12-month volatility' in t: labels['v12']=(r,c)
            elif t=='country': labels.setdefault('countries',[]).append((r,c))
    for x in ('z','v3','v3a','v12'):
        if x not in labels: raise ValueError('Answer label missing '+x)
    answer_col=labels['z'][1]+1
    ans.cell(labels['z'][0],answer_col).value='=NORM.S.INV(0.95)'
    ans.cell(labels['v3'][0],answer_col).value=f'={qsheet(price.title)}!{ref(cols["v3"],latestrow)}'
    ans.cell(labels['v3a'][0],answer_col).value=f'={ref(answer_col,labels["v3"][0])}*SQRT(12)'
    ans.cell(labels['v12'][0],answer_col).value=f'={qsheet(price.title)}!{ref(cols["v12"],latestrow)}'
    country_rows=sorted(r for r,c in labels['countries'])
    if len(country_rows)!=2: raise ValueError('Answer must contain exactly two Country rows')
    s2country,s3country=country_rows
    s2value=s2country+1; s2exposure=s2country+2
    s3value=s3country+1; s3exposure=s3country+2; s3total=s3country+3; s3rar=s3country+4
    vr,vycol,vrec=gold_columns(value,'value'); mr,mycol,mrec=gold_columns(volume,'volume'); tr,tycol,trec=gold_columns(total,'total')
    allrecs=list(vrec.values())
    allrecs += [dict(x,source='volume') for k,x in mrec.items() if k not in vrec]
    # Clear only answer table cells, allowing a rebuild when the eligible country set changes.
    for r in (s2country,s2value,s2exposure,s3country,s3value,s3exposure,s3total,s3rar):
        for c in range(answer_col,ans.max_column+1): ans.cell(r,c).value=None
    jansep=[templ[(YEAR,m)] for m in range(1,10) if (YEAR,m) in templ]
    if len(jansep)!=9: raise ValueError('template does not contain January--September 2025')
    jansep_formula=f'AVERAGE({qsheet(price.title)}!{ref(cols["price"],jansep[0])}:{ref(cols["price"],jansep[-1])})'
    # Bounds for INDEX/MATCH explicitly cover the discovered data row and descriptor headings.
    def indexmatch(ws,data_row,year_col,countrycell):
        # Two independent MATCH keys keep the lookup tied to both the requested
        # country and the literal 2025 row rather than the current row order.
        ykey='"2025"' if isinstance(ws.cell(data_row,year_col).value,str) else '2025'
        return f'INDEX({rng(ws.title,1,1,ws.max_column,data_row)},MATCH({ykey},{rng(ws.title,year_col,1,year_col,data_row)},0),MATCH("*"&{countrycell}&"*",{rng(ws.title,1,1,ws.max_column,1)},0))'
    step2=[]
    for rec in allrecs:
        c=answer_col+len(step2); countrycell=ref(c,s2country); ans.cell(s2country,c).value=rec['country']
        if rec['key'] in vrec:
            formula='='+indexmatch(value,vr,vycol,countrycell)
        else:
            mult=unit_multiplier(rec['header'])
            formula=f'={indexmatch(volume,mr,mycol,countrycell)}*{mult}*{jansep_formula}/1000000'
        ans.cell(s2value,c).value=formula
        ans.cell(s2exposure,c).value=f'={ref(c,s2value)}*{ref(answer_col,labels["z"][0])}*{ref(answer_col,labels["v3a"][0])}'
        step2.append(rec)
    step3=[]
    for i,rec in enumerate(step2):
        if rec['key'] not in trec: continue
        c=answer_col+len(step3); old=answer_col+i
        ans.cell(s3country,c).value=f'={ref(old,s2country)}'
        ans.cell(s3value,c).value=f'={ref(old,s2value)}'
        ans.cell(s3exposure,c).value=f'={ref(old,s2exposure)}'
        ans.cell(s3total,c).value='='+indexmatch(total,tr,tycol,ref(c,s3country))
        ans.cell(s3rar,c).value=f'={ref(c,s3exposure)}/{ref(c,s3total)}*100'
        step3.append(rec)
    wb.calculation.fullCalcOnLoad=True
    wb.calculation.forceFullCalc=True
    wb.calculation.calcMode='auto'
    wb.save(output)
    return {'output':output,'price_rows':len(templ),'imf_series':meta,'step2_countries':[x['country'] for x in step2],'step3_countries':[x['country'] for x in step3]}

def inspect(path):
    wb=load_workbook(path,data_only=False,read_only=True)
    return {'sheets':[{'name':w.title,'max_row':w.max_row,'max_column':w.max_column} for w in wb.worksheets]}

def validate(path):
    wb=load_workbook(path,data_only=False); ans=find_sheet(wb,'Answer'); price=find_sheet(wb,'Gold price')
    periods=scan_template_periods(price); problems=[]
    for p,r in periods.items():
        if not numeric(price.cell(r,2).value): problems.append(f'missing numeric gold price at {p}')
    for r in sorted(periods.values())[1:]:
        if not str(price.cell(r,3).value or '').startswith('='): problems.append(f'missing log-return formula C{r}')
    for cell in ('C3','C4','C5','C6'):
        if not str(ans[cell].value or '').startswith('='): problems.append(f'missing Step 1 formula {cell}')
    # The answer table formula cells must be populated through its last listed country.
    listed=[c for c in range(3,ans.max_column+1) if ans.cell(11,c).value is not None]
    for c in listed:
        for r in (12,13):
            if not str(ans.cell(r,c).value or '').startswith('='): problems.append(f'missing Step 2 formula {ref(c,r)}')
    result={'ok':not problems,'problems':problems,'step2_countries':len(listed)}
    if problems: raise ValueError('; '.join(problems[:5]))
    return result

def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest='command',required=True)
    a=sp.add_parser('build'); a.add_argument('--workbook',required=True); a.add_argument('--imf-xlsx',required=True); a.add_argument('--output',required=True)
    a=sp.add_parser('inspect'); a.add_argument('--workbook',required=True)
    a=sp.add_parser('validate'); a.add_argument('--workbook',required=True)
    x=p.parse_args()
    try:
        if x.command=='build': result=build(x.workbook,x.imf_xlsx,x.output)
        elif x.command=='validate': result=validate(x.workbook)
        else: result=inspect(x.workbook)
        out(result)
    except Exception as e:
        out({'ok':False,'error':str(e)}); raise SystemExit(2)
if __name__=='__main__': main()
