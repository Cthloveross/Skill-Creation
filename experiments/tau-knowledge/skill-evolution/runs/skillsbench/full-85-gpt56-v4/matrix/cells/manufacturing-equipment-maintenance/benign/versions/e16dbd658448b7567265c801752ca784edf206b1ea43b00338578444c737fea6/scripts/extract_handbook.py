#!/usr/bin/env python3
"""Read {"pdf": path} from stdin and emit {"pages": [{"page": n,"text": str}]}.
Uses pdftotext when installed, then PyPDF2/pypdf if available.
"""
import json, subprocess, sys, tempfile, os

def main():
    req=json.load(sys.stdin); path=req['pdf']
    pages=[]
    try:
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f: out=f.name
        r=subprocess.run(['pdftotext','-layout',path,out],capture_output=True,text=True)
        if r.returncode == 0:
            with open(out,encoding='utf-8',errors='replace') as f: text=f.read()
            pages=[{'page':i+1,'text':x} for i,x in enumerate(text.split('\f')) if x.strip()]
        os.unlink(out)
    except (FileNotFoundError, OSError): pass
    if not pages:
        try:
            try: from pypdf import PdfReader
            except ImportError: from PyPDF2 import PdfReader
            reader=PdfReader(path)
            pages=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(reader.pages)]
        except Exception as e:
            print(json.dumps({'error':'PDF extraction failed: '+str(e)})); return
    print(json.dumps({'pages':pages},ensure_ascii=False))
if __name__=='__main__': main()
