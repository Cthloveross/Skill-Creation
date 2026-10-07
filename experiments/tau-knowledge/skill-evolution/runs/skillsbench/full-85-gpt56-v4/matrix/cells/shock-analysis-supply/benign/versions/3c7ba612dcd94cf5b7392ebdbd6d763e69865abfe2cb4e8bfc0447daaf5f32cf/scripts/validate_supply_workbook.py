#!/usr/bin/env python3
"""Read-only structural check. stdin: {"workbook": "path.xlsx"}; stdout JSON.
It never writes the workbook and never calculates Solver/model values.
"""
import json, sys, zipfile
import xml.etree.ElementTree as ET
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def main():
    req=json.load(sys.stdin); errors=[]; checks={}
    try:
      with zipfile.ZipFile(req['workbook']) as z:
        wb=ET.fromstring(z.read('xl/workbook.xml')); rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets={x.attrib['Id']:x.attrib['Target'] for x in rels}
        sheets={x.attrib['name']:ET.fromstring(z.read('xl/'+targets[x.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']].lstrip('/'))) for x in wb.findall('.//x:sheet',NS)}
    except Exception as e:
      print(json.dumps({'ok':False,'errors':['Unreadable workbook: '+str(e)],'checks':{}})); return
    needed={'Production','Investment','CFC data','PWT','WEO_Data'}
    checks['required_sheets']=needed<=set(sheets)
    if not checks['required_sheets']: errors.append('Missing required sheet(s).')
    def cmap(name): return {c.attrib['r']:c for c in sheets[name].findall('.//x:c',NS)}
    if checks['required_sheets']:
      p,c,w=cmap('Production'),cmap('CFC data'),cmap('WEO_Data')
      def f(m,a):
        x=m.get(a); y=None if x is None else x.find('x:f',NS); return '' if y is None or y.text is None else y.text.upper()
      checks['depreciation_average']='AVERAGE' in f(p,'B3')
      checks['hp_objective']=('100' in f(p,'P5') and ('SUMSQ' in f(p,'P5') or 'SUMXMY2' in f(p,'P5')))
      checks['hp_second_differences']=all(f(p,'M'+str(r)) for r in range(7,27))
      checks['hp_solver_values']=all((p.get('L'+str(r)) is not None and p['L'+str(r)].find('x:v',NS) is not None) for r in range(6,28))
      checks['cfc_formulas']=all(f(c,'E'+str(r)) for r in range(2,30))
      checks['weo_extension']=all(f(w,col+str(r)) for r in range(36,52) for col in ('C','D'))
      checks['scenario_formulas']=all(f(p,col+str(r)) for r in range(36,76) for col in 'EFGHIJKLMNOP')
      for k,v in checks.items():
        if not v: errors.append('Failed structural check: '+k)
    print(json.dumps({'ok':not errors,'errors':errors,'checks':checks},sort_keys=True))
if __name__=='__main__': main()
