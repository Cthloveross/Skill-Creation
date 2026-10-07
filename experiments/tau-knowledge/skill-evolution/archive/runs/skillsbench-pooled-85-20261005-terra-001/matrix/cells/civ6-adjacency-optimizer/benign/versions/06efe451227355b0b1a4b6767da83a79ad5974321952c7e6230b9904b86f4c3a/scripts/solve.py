#!/usr/bin/env python3
"""Read a Civ6 scenario and write a legal, map-only adjacency layout.
stdin: {"scenario_path": str?, "output_path": str?}
stdout: the solution JSON written to output_path.
"""
import json, os, sys, sqlite3
from collections import deque

SPECIAL = {"CAMPUS","HOLY_SITE","THEATER_SQUARE","COMMERCIAL_HUB","HARBOR",
 "INDUSTRIAL_ZONE","ENTERTAINMENT_COMPLEX","WATER_PARK","ENCAMPMENT","AERODROME",
 "GOVERNMENT_PLAZA","DIPLOMATIC_QUARTER","PRESERVE"}
NON_SPECIAL = {"AQUEDUCT","DAM","CANAL","SPACEPORT","NEIGHBORHOOD"}
ORDER = ["CAMPUS","HOLY_SITE","COMMERCIAL_HUB","HARBOR","INDUSTRIAL_ZONE",
 "THEATER_SQUARE","AQUEDUCT","DAM","NEIGHBORHOOD","SPACEPORT",
 "ENTERTAINMENT_COMPLEX","WATER_PARK","GOVERNMENT_PLAZA","DIPLOMATIC_QUARTER",
 "PRESERVE","ENCAMPMENT","AERODROME"]
STRATEGIC = ("IRON","HORSES","NITER","COAL","OIL","ALUMINUM","URANIUM")
LUXURY = ("AMBER","CITRUS","COCOA","COFFEE","COTTON","DYES","DIAMONDS","FURS",
 "GYPSUM","INCENSE","IVORY","JADE","MARBLE","MERCURY","PEARLS","SALT","SILK",
 "SILVER","SPICES","SUGAR","TEA","TOBACCO","TRUFFLES","WHALES","WINE")
KNOWN_NOT_NW = {"FEATURE_FOREST","FEATURE_JUNGLE","FEATURE_MARSH","FEATURE_REEF",
 "FEATURE_ICE","FEATURE_GEOTHERMAL_FISSURE","FEATURE_FLOODPLAINS","FEATURE_OASIS",
 "FEATURE_VOLCANIC_SOIL","FEATURE_BARRIER_REEF"}
NATURAL_NAMES = ("BARRIER_REEF","CRATER_LAKE","DELICATE_ARCH","EYE_OF_THE_SAHARA",
 "GALAPAGOS","GIANTS_CAUSEWAY","HA_LONG_BAY","IK_KIL","MATTERHORN","PANTANAL",
 "PANTHEON","PIOPIOTAHI","TORRES_DEL_PAINE","TSINGY","ULURU","YOSEMITE",
 "RORAIMA","FOUNTAIN_OF_YOUTH","DEAD_SEA","DOHA","KILIMANJARO","EVEREST")

def lowercols(con, table):
    rows = con.execute('PRAGMA table_info("%s")' % table).fetchall()
    return {r[1].lower(): r[1] for r in rows}
def findtable(con, name):
    tabs = con.execute("select name from sqlite_master where type='table'").fetchall()
    for (t,) in tabs:
        if t.lower() == name.lower(): return t
    return None
def col(cols, *names):
    for n in names:
        if n.lower() in cols: return cols[n.lower()]
    return None

def load_map(path):
    con = sqlite3.connect(path)
    mt = findtable(con,"Map"); pt = findtable(con,"Plots")
    if not mt or not pt: raise ValueError("Civ6Map lacks Map or Plots table")
    mc = lowercols(con,mt); pc = lowercols(con,pt)
    wcol, hcol = col(mc,"Width"), col(mc,"Height")
    if not wcol or not hcol: raise ValueError("Map table lacks Width/Height")
    mr = con.execute('select * from "%s" limit 1' % mt).fetchone()
    names = [x[0] for x in con.execute('select * from "%s" limit 1' % mt).description]
    md = dict(zip(names,mr)); W,H = int(md[wcol]),int(md[hcol])
    wrapx = bool(md.get(col(mc,"WrapX"),0)); wrapy = bool(md.get(col(mc,"WrapY"),0))
    idc, tc, ic = col(pc,"ID"),col(pc,"TerrainType"),col(pc,"IsImpassable")
    plots = {}
    for row in con.execute('select * from "%s"' % pt):
        d=dict(zip([x[0] for x in con.execute('select * from "%s" limit 1' % pt).description],row))
        i=int(d[idc]); plots[(i%W,i//W)]={"terrain":str(d.get(tc) or ""),"imp":bool(d.get(ic,0)),"feature":"","resource":"","river":(0,0,0)}
    for table, field in (("PlotFeatures","feature"),("PlotResources","resource")):
        t=findtable(con,table)
        if t:
            cs=lowercols(con,t); ic2,colv=col(cs,"ID"),col(cs,"FeatureType","ResourceType")
            if ic2 and colv:
                for i,v in con.execute('select "%s","%s" from "%s"' % (ic2,colv,t)):
                    xy=(int(i)%W,int(i)//W)
                    if xy in plots: plots[xy][field]=str(v or "")
    t=findtable(con,"PlotRivers")
    if t:
        cs=lowercols(con,t); ic2=col(cs,"ID"); ns=[col(cs,"IsNEOfRiver"),col(cs,"IsWOfRiver"),col(cs,"IsNWOfRiver")]
        if ic2:
            selected=','.join('"%s"' % x if x else '0' for x in [ic2]+ns)
            for row in con.execute('select %s from "%s"' % (selected,t)):
                xy=(int(row[0])%W,int(row[0])//W)
                if xy in plots: plots[xy]["river"]=tuple(bool(x) for x in row[1:])
    con.close(); return W,H,wrapx,wrapy,plots

class Solver:
 def __init__(self,W,H,wx,wy,p): self.W,self.H,self.wx,self.wy,self.p=W,H,wx,wy,p; self.centers=[]; self.place={}; self.owner={}
 def nbs(self,a):
  x,y=a; ds=[(1,0),(-1,0)] + ([(0,-1),(-1,-1),(-1,1),(0,1)] if y%2==0 else [(1,-1),(0,-1),(0,1),(1,1)])
  out=[]
  for dx,dy in ds:
   X,Y=x+dx,y+dy
   if self.wx: X%=self.W
   if self.wy: Y%=self.H
   if 0<=X<self.W and 0<=Y<self.H and (X,Y) in self.p: out.append((X,Y))
  return out
 def radius(self,a,n=3):
  seen={a}; q=deque([(a,0)])
  while q:
   z,d=q.popleft()
   if d==n: continue
   for v in self.nbs(z):
    if v not in seen: seen.add(v);q.append((v,d+1))
  return seen
 def dist(self,a,b,cap=20):
  if a==b:return 0
  seen={a};q=deque([(a,0)])
  while q:
   z,d=q.popleft()
   if d>=cap:continue
   for v in self.nbs(z):
    if v==b:return d+1
    if v not in seen:seen.add(v);q.append((v,d+1))
  return cap+1
 def water(self,a): return any(k in self.p[a]["terrain"] for k in ("COAST","OCEAN","LAKE"))
 def mountain(self,a): return "MOUNTAIN" in self.p[a]["terrain"]
 def nw(self,a):
  f=self.p[a]["feature"]
  return f not in KNOWN_NOT_NW and ("NATURAL_WONDER" in f or any(x in f for x in NATURAL_NAMES))
 def strategic(self,a): return any(x in self.p[a]["resource"] for x in STRATEGIC)
 def luxury(self,a): return any(x in self.p[a]["resource"] for x in LUXURY)
 def river_edges(self,a):
  r=self.p[a]["river"]; count=sum(r)
  ns=self.nbs(a)
  # own NE/W/NW, plus E.W, SW.NE, SE.NW. Match neighbors by offset direction.
  x,y=a
  for b in ns:
   dx=b[0]-x
   if self.wx and dx>1:dx-=self.W
   if self.wx and dx<-1:dx+=self.W
   dy=b[1]-y
   br=self.p[b]["river"]
   if (dx,dy)==(1,0): count+=bool(br[1])
   elif (dy==1 and ((y%2==0 and dx==-1) or (y%2==1 and dx==0))): count+=bool(br[0])
   elif (dy==1 and ((y%2==0 and dx==0) or (y%2==1 and dx==1))): count+=bool(br[2])
  return count
 def river(self,a): return self.river_edges(a)>0
 def city_ok(self,a):
  t=self.p[a]; return not t["imp"] and not self.water(a) and not self.mountain(a) and not self.nw(a) and "ICE" not in t["feature"]
 def base_ok(self,a,water=False):
  t=self.p[a]
  if t["imp"] or a in self.centers or a in self.place.values():return False
  if self.water(a)!=water:return False
  return not self.mountain(a) and not self.nw(a) and not self.strategic(a) and not self.luxury(a) and "GEOTHERMAL" not in t["feature"]
 def in_city(self,a): return [i for i,c in enumerate(self.centers) if a in self.radius(c)]
 def fresh(self,a):
  for b in self.nbs(a):
   if self.mountain(b) or self.water(b) or "OASIS" in self.p[b]["feature"] or self.river(b):return True
  return False
 def legal(self,k,a):
  if not self.in_city(a):return False
  if k in ("HARBOR","WATER_PARK"):
   return self.base_ok(a,True) and any(not self.water(b) for b in self.nbs(a))
  if not self.base_ok(a,False):return False
  if k in ("AERODROME","SPACEPORT") and ("HILLS" in self.p[a]["terrain"]):return False
  if k in ("ENCAMPMENT","PRESERVE") and any(a in self.nbs(c) for c in self.centers):return False
  if k=="AQUEDUCT":return any(a in self.nbs(c) for c in self.centers) and self.fresh(a)
  if k=="DAM":return "FLOODPLAINS" in self.p[a]["feature"] and self.river_edges(a)>=2
  if k=="CANAL":return False # omit rather than claim an unverifiable water-body connection
  return True
 def destroyed(self,a): return a in self.place.values() and self.p[a]["feature"] in ("FEATURE_FOREST","FEATURE_JUNGLE","FEATURE_MARSH")
 def score_one(self,k,a):
  ns=self.nbs(a); ds=set(self.centers)|set(self.place.values()); dc=sum(b in ds for b in ns)
  f=lambda s:sum((self.p[b]["feature"]==s and not self.destroyed(b)) for b in ns)
  if k=="CAMPUS":return 2*f("FEATURE_GEOTHERMAL_FISSURE")+2*f("FEATURE_REEF")+sum(self.mountain(b) for b in ns)+f("FEATURE_JUNGLE")//2+dc//2
  if k=="HOLY_SITE":return 2*sum(self.nw(b) for b in ns)+sum(self.mountain(b) for b in ns)+f("FEATURE_FOREST")//2+dc//2
  if k=="COMMERCIAL_HUB":return (2 if self.river(a) else 0)+2*sum(self.place.get("HARBOR")==b for b in ns)+dc//2
  if k=="INDUSTRIAL_ZONE":return 2*sum(any(self.place.get(x)==b for x in ("AQUEDUCT","DAM","CANAL")) for b in ns)+sum(self.strategic(b) for b in ns)+dc//2
  if k=="HARBOR":return 2*sum(b in self.centers for b in ns)+sum(bool(self.p[b]["resource"]) and self.water(b) for b in ns)+dc//2
  if k=="THEATER_SQUARE":return 2*sum(any(self.place.get(x)==b for x in ("ENTERTAINMENT_COMPLEX","WATER_PARK")) for b in ns)+dc//2
  return 0
 def total(self): return sum(self.score_one(k,a) for k,a in self.place.items())
 def capacity(self): return 1+(self.population-1)//3
 def addable_owner(self,k,a):
  if k not in SPECIAL:return -1
  used=[0]*len(self.centers)
  for q,o in self.owner.items():
   if q in SPECIAL:used[o]+=1
  for i in self.in_city(a):
   if used[i]<self.capacity():return i
  return None
 def rank_center(self,c):
  best=0
  for a in self.radius(c):
   if not self.base_ok_center_site(a):continue
   ns=self.nbs(a); val=sum(self.mountain(b) for b in ns)+2*sum(self.p[b]["feature"] in ("FEATURE_REEF","FEATURE_GEOTHERMAL_FISSURE") for b in ns)
   val=max(val, 2 if self.river(a) else 0)
   best=max(best,val)
  return best
 def base_ok_center_site(self,a): return self.city_ok(a)
 def validate(self):
  if len(self.centers)!=self.numcities:raise ValueError("could not place requested city centers")
  if len(set(self.centers)|set(self.place.values()))!=len(self.centers)+len(self.place):raise ValueError("overlapping placements")
  for k,a in self.place.items():
   if not self.legal_final(k,a):raise ValueError("invalid placement: "+k)
  used=[0]*len(self.centers)
  for k,o in self.owner.items():
   if k in SPECIAL:used[o]+=1
  if any(v>self.capacity() for v in used):raise ValueError("specialty cap exceeded")
  bonuses={k:self.score_one(k,a) for k,a in self.place.items()}
  if sum(bonuses.values())!=self.total():raise ValueError("adjacency sum mismatch")
  return bonuses
 def legal_final(self,k,a):
  # temporarily remove itself so overlap check used by legal does not reject it
  old=self.place.pop(k); ok=self.legal(k,a); self.place[k]=old; return ok
 def solve(self,numcities,pop):
  self.numcities,self.population=numcities,pop
  candidates=[a for a in self.p if self.city_ok(a)]
  ranked=sorted(((self.rank_center(a),a) for a in candidates),reverse=True)
  for _,a in ranked:
   if len(self.centers)==numcities:break
   # Civ normally requires four hexes between centers. Relax only if map geometry demands it.
   if all(self.dist(a,c,6)>=4 for c in self.centers):self.centers.append(a)
  if len(self.centers)<numcities:
   for _,a in ranked:
    if len(self.centers)==numcities:break
    if a not in self.centers:self.centers.append(a)
  if len(self.centers)!=numcities:raise ValueError("insufficient legal city center tiles")
  # Greedy whole-layout evaluation. Zero-gain infrastructure is permitted only if it touches
  # an existing district, so it can unlock independently floored district adjacency.
  for step in range(len(ORDER)):
   base=self.total(); best=None
   for k in ORDER:
    if k in self.place:continue
    for a in set().union(*(self.radius(c) for c in self.centers)):
     if not self.legal(k,a):continue
     own=self.addable_owner(k,a)
     if own is None:continue
     self.place[k]=a
     val=self.total(); self.place.pop(k)
     touch=sum(b in set(self.centers)|set(self.place.values()) for b in self.nbs(a))
     item=(val-base, val, touch, -a[1], -a[0], k, a, own)
     if best is None or item>best:best=item
   if best is None:break
   gain,_,touch,_,_,k,a,own=best
   if gain<0 or (gain==0 and touch==0):break
   self.place[k]=a
   if k in SPECIAL:self.owner[k]=own
  bonuses=self.validate()
  if numcities==1: out={"city_center":list(self.centers[0])}
  else: out={"cities":[{"center":list(c)} for c in self.centers]}
  out.update({"placements":{k:list(v) for k,v in self.place.items()},"adjacency_bonuses":bonuses,"total_adjacency":sum(bonuses.values())})
  return out

def main():
 req=json.load(sys.stdin)
 sp=req.get("scenario_path","/data/scenario_3/scenario.json"); op=req.get("output_path","/output/scenario_3.json")
 with open(sp,encoding="utf-8") as f: sc=json.load(f)
 mp=sc["map_file"]
 if not os.path.isabs(mp):mp=os.path.normpath(os.path.join(os.path.dirname(sp),mp))
 W,H,wx,wy,p=load_map(mp)
 sol=Solver(W,H,wx,wy,p).solve(int(sc["num_cities"]),int(sc["population"]))
 os.makedirs(os.path.dirname(op) or ".",exist_ok=True)
 with open(op,"w",encoding="utf-8") as f:json.dump(sol,f,indent=2);f.write("\n")
 json.dump(sol,sys.stdout);sys.stdout.write("\n")
if __name__=="__main__":main()
