#!/usr/bin/env python3
"""Read {"paths":[...], "sample_rows": 3} and emit headers and string samples."""
import csv,json,sys

def main():
    q=json.load(sys.stdin); result=[]
    for p in q['paths']:
        with open(p,newline='',encoding='utf-8-sig') as f:
            r=csv.DictReader(f); rows=[]
            for row in r:
                if len(rows)>=q.get('sample_rows',3): break
                rows.append(row)
            result.append({'path':p,'headers':r.fieldnames or [],'sample_rows':rows})
    print(json.dumps({'files':result},ensure_ascii=False))
if __name__=='__main__': main()
