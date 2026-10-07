#!/usr/bin/env python3
"""Download the public IMF commodity-price Excel file, reporting JSON."""
import argparse,json,re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen

def download(url,dest):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=120) as r: data=r.read()
    if data[:2]==b'PK' or url.lower().split('?')[0].endswith(('.xlsx','.xls')):
        Path(dest).write_bytes(data); return {'downloaded':url,'output':dest,'bytes':len(data)}
    links=re.findall(r'''(?:href|src)=["']([^"']+)["']''',data.decode('utf-8','replace'),re.I)
    choices=[urljoin(url,x.replace('&amp;','&')) for x in links if re.search(r'(?:\.xlsx?(?:\?|$)|pcps|commodity.*(?:download|data))',x,re.I)]
    if not choices: raise ValueError('No downloadable Excel link found; provide the direct public IMF .xlsx URL with --url')
    return download(choices[0],dest)
p=argparse.ArgumentParser();p.add_argument('--url',default='https://www.imf.org/en/research/commodity-prices');p.add_argument('--output',required=True);x=p.parse_args()
try: print(json.dumps(download(x.url,x.output),indent=2))
except Exception as e: print(json.dumps({'ok':False,'error':str(e)}));raise SystemExit(2)
