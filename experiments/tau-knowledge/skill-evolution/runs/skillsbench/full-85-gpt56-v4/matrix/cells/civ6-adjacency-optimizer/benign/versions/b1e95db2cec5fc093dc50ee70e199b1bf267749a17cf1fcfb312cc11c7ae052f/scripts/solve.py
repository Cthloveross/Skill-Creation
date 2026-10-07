#!/usr/bin/env python3
"""Map-only Civ6 district placement solver and validator.
stdin: {scenario:path, output?:path} or {scenario:path, solution:path}
stdout: task solution for solve; {valid, errors, ...} for validation.
"""
import argparse, json, os, sqlite3, sys
from collections import defaultdict

SPECIAL = {"CAMPUS","HOLY_SITE","THEATER_SQUARE","COMMERCIAL_HUB","HARBOR",
 "INDUSTRIAL_ZONE","ENTERTAINMENT_COMPLEX","WATER_PARK","ENCAMPMENT","AERODROME",
 "GOVERNMENT_PLAZA","DIPLOMATIC_QUARTER","PRESERVE"}
# Types are unique because the public output placements object is keyed by type.
ACTIVE = ["CAMPUS","INDUSTRIAL_ZONE","HOLY_SITE","COMMERCIAL_HUB","HARBOR",
          "THEATER_SQUARE","ENTERTAINMENT_COMPLEX","WATER_PARK"]
FILL_SPECIAL = ["GOVERNMENT_PLAZA","DIPLOMATIC_QUARTER","AERODROME","ENCAMPMENT","PRESERVE"]
FREE = ["AQUEDUCT","DAM","NEIGHBORHOOD","SPACEPORT"]
STRATEGIC = ("HORSES","IRON","NITER","COAL","OIL","ALUMINUM","URANIUM")
BONUS_RESOURCES = ("WHEAT","RICE","MAIZE","DEER","SHEEP","CATTLE","STONE","BANANAS",
                   "FISH","CRABS","COPPER")
DISTRICTS = SPECIAL | {"AQUEDUCT","DAM","CANAL","SPACEPORT","NEIGHBORHOOD"}
# Standard natural-wonder feature names do not consistently contain WONDER.
NATURAL_FEATURES = {"BARRIER_REEF", "CLIFFS_OF_DOVER", "CRATER_LAKE", "DEAD_SEA",
 "GALAPAGOS", "GIANTS_CAUSEWAY", "IK_KIL", "PANTANAL", "PIOPIOTAHI",
 "TORRES_DEL_PAINE", "TSINGY_DE_BEMARAHA", "YOSEMITE", "DELICATE_ARCH",
 "EYE_OF_THE_SAHARA", "LAKE_RETBA", "MATTERHORN", "MOUNT_RORAIMA"}

class Map:
 def __init__(self, path):
  self.db = sqlite3.connect(path)
  self.db.row_factory = sqlite3.Row
  self.tables = {r[0].lower(): r[0] for r in self.db.execute("select name from sqlite_master where type='table'")}
  m = self.rows("map")
  if not m: raise ValueError("Map table is missing or empty")
  mr=m[0]; self.w=int(self.val(mr,"Width",0)); self.h=int(self.val(mr,"Height",0))
  self.wrapx=bool(self.val(mr,"WrapX",0)); self.wrapy=bool(self.val(mr,"WrapY",0))
  if not self.w or not self.h: raise ValueError("invalid map dimensions")
  self.plot={}; self.feature={}; self.resource={}; self.rivers={}
  for r in self.rows("plots"):
   i=int(self.val(r,"ID",-1)); self.plot[i]=dict(r)
  for name, dest, field in (("plotfeatures",self.feature,"FeatureType"),("plotresources",self.resource,"ResourceType")):
   for r in self.rows(name): dest[int(self.val(r,"ID",-1))]=str(self.val(r,field,"" ) or "")
  for r in self.rows("plotrivers"):
   self.rivers[int(self.val(r,"ID",-1))]=dict(r)
 def rows(self, logical):
  t=self.tables.get(logical.lower())
  return list(self.db.execute('select * from "'+t+'"')) if t else []
 @staticmethod
 def val(row, key, default=None):
  for k in row.keys():
   if k.lower()==key.lower(): return row[k]
  return default
 def norm(self,x,y):
  if self.wrapx: x%=self.w
  if self.wrapy: y%=self.h
  if not (0<=x<self.w and 0<=y<self.h): return None
  return (x,y)
 def pid(self,p): return p[1]*self.w+p[0]
 def terrain(self,p): return str(self.val(self.plot.get(self.pid(p),{}),"TerrainType","") or "")
 def feat(self,p): return self.feature.get(self.pid(p),"")
 def res(self,p): return self.resource.get(self.pid(p),"")
 def impassable(self,p): return bool(self.val(self.plot.get(self.pid(p),{}),"IsImpassable",0))
 def neigh(self,p):
  x,y=p
  ds=[(1,0),(-1,0),(0,-1),(-1,-1),(-1,1),(0,1)] if y%2==0 else [(1,0),(-1,0),(1,-1),(0,-1),(0,1),(1,1)]
  return [q for dx,dy in ds if (q:=self.norm(x+dx,y+dy)) is not None]
 def cube(self,p):
  x,y=p; q=x-(y-(y&1))//2; return q,y,-q-y
 def dist(self,a,b):
  A=self.cube(a);B=self.cube(b); return max(abs(A[i]-B[i]) for i in range(3))
 def water(self,p):
  t=self.terrain(p); return "COAST" in t or "OCEAN" in t or "LAKE" in t
 def mountain(self,p): return "MOUNTAIN" in self.terrain(p)
 def river_flags(self,p):
  r=self.rivers.get(self.pid(p),{})
  return sum(bool(self.val(r,k,0)) for k in ("IsNEOfRiver","IsWOfRiver","IsNWOfRiver"))
 def river_edges(self,p):
  # A database records only NE/W/NW edges.  The complementary edges are
  # recorded as W on E, NE on SW, and NW on SE neighbours respectively.
  n={q for q in self.neigh(p)}; x,y=p
  east=self.norm(x+1,y)
  sw=self.norm(x+(-1 if y%2==0 else 0),y+1)
  se=self.norm(x+(0 if y%2==0 else 1),y+1)
  count=self.river_flags(p)
  for q,key in ((east,"IsWOfRiver"),(sw,"IsNEOfRiver"),(se,"IsNWOfRiver")):
   if q in n: count+=bool(self.val(self.rivers.get(self.pid(q),{}),key,0))
  return count
 def river(self,p): return self.river_edges(p)>0
 def land(self,p): return not self.water(p) and not self.mountain(p) and not self.impassable(p)
 def natural(self,p):
  f=self.feat(p).upper(); return "NATURAL" in f or "WONDER" in f or any(n in f for n in NATURAL_FEATURES)
 def geo(self,p): return "GEOTHERMAL" in self.feat(p).upper()
 def forbidden_resource(self,p):
  r=self.res(p).upper()
  if not r: return False
  # Bonus resources may be removed by district construction. Everything else
  # is conservatively treated as strategic/luxury unless explicitly BONUS.
  return any(s in r for s in STRATEGIC) or ("BONUS" not in r and not any(s in r for s in BONUS_RESOURCES))

def city_ok(m,p,used=()):
 return m.land(p) and "ICE" not in m.feat(p).upper() and not m.natural(p) and p not in used

def fresh(m,p):
 if m.river(p) or "OASIS" in m.feat(p).upper() or "LAKE" in m.terrain(p): return True
 return any(m.mountain(q) or "OASIS" in m.feat(q).upper() or "LAKE" in m.terrain(q) for q in m.neigh(p))

def district_ok(m, typ, p, centers, occupied):
 if p in occupied or min((m.dist(p,c) for c in centers), default=99)>3: return False
 if typ in ("HARBOR","WATER_PARK"):
  return m.water(p) and "OCEAN" not in m.terrain(p) and any(m.land(q) for q in m.neigh(p))
 if not m.land(p) or m.natural(p) or m.geo(p) or m.forbidden_resource(p): return False
 if typ in ("AERODROME","SPACEPORT") and ("HILLS" in m.terrain(p) or m.water(p)): return False
 if typ in ("ENCAMPMENT","PRESERVE") and any(m.dist(p,c)==1 for c in centers): return False
 if typ=="AQUEDUCT": return any(m.dist(p,c)==1 for c in centers) and fresh(m,p)
 if typ=="DAM": return "FLOODPLAINS" in m.feat(p).upper() and m.river_edges(p)>=2
 # Canal's water-body connection is not recoverable from a simple local test;
 # it is deliberately omitted from the search rather than emitting a dubious placement.
 if typ=="CANAL": return False
 return True

def score(m, centers, places):
 """Return one exact map-only adjacency value for every placed district."""
 pos_to_type={p:t for t,p in places.items()}
 destroyed=set(pos_to_type) # centers preserve their feature; all districts do not
 def feature(p): return "" if p in destroyed else m.feat(p).upper()
 def is_district(p): return p in pos_to_type or p in centers
 out={}
 for typ,p in places.items():
  ns=m.neigh(p); generic=sum(is_district(q) for q in ns)
  fs=[feature(q) for q in ns]; ts=[m.terrain(q).upper() for q in ns]
  if typ=="CAMPUS":
   out[typ]=2*sum("GEOTHERMAL" in f or "REEF" in f for f in fs)+sum("MOUNTAIN" in t for t in ts)+sum("JUNGLE" in f for f in fs)//2+generic//2
  elif typ=="HOLY_SITE":
   out[typ]=2*sum(m.natural(q) for q in ns)+sum("MOUNTAIN" in t for t in ts)+sum("FOREST" in f for f in fs)//2+generic//2
  elif typ=="COMMERCIAL_HUB": out[typ]=2*int(m.river(p))+2*sum(pos_to_type.get(q)=="HARBOR" for q in ns)+generic//2
  elif typ=="INDUSTRIAL_ZONE":
   out[typ]=2*sum(pos_to_type.get(q) in ("AQUEDUCT","DAM","CANAL") for q in ns)+sum(any(k in m.res(q).upper() for k in STRATEGIC) for q in ns)+generic//2
  elif typ=="HARBOR":
   out[typ]=2*sum(q in centers for q in ns)+sum(bool(m.res(q)) and m.water(q) for q in ns)+generic//2
  elif typ=="THEATER_SQUARE": out[typ]=2*sum(pos_to_type.get(q) in ("ENTERTAINMENT_COMPLEX","WATER_PARK") for q in ns)+generic//2
  else: out[typ]=0
 return out

def quality(m,p):
 ns=m.neigh(p); fs=[m.feat(q).upper() for q in ns]; ts=[m.terrain(q).upper() for q in ns]
 return 5*sum("GEOTHERMAL" in f or "REEF" in f for f in fs)+2*sum("MOUNTAIN" in t for t in ts)+2*int(m.river(p))+sum("FLOODPLAINS" in f for f in fs)+sum("FOREST" in f or "JUNGLE" in f for f in fs)

def candidates(m, centers, typ, occupied):
 ps=[]
 for y in range(m.h):
  for x in range(m.w):
   p=(x,y)
   if district_ok(m,typ,p,centers,occupied): ps.append(p)
 # Keeping all range-three tiles is small (at most 37 per center); order only
 # makes deterministic greedy tie-breaking more useful.
 return sorted(ps,key=lambda p:(-quality(m,p),p[1],p[0]))

def improve(m,centers,places):
 best=sum(score(m,centers,places).values())
 for _ in range(4):
  changed=False
  for typ in list(places):
   old=places.pop(typ); occ=set(centers)|set(places.values())
   bp=old; bv=best
   for p in candidates(m,centers,typ,occ):
    places[typ]=p; v=sum(score(m,centers,places).values())
    if v>bv or (v==bv and p<bp): bp,bv=p,v
   places[typ]=bp
   if bp!=old: changed=True
   best=bv
  if not changed: break
 return places,best

def make_layout(m, centers, cap):
 places={}; chosen_special=0
 # Select scoring specialties adaptively. A type remains unique in output.
 for _ in range(cap):
  best=None
  for typ in ACTIVE+FILL_SPECIAL:
   if typ in places: continue
   for p in candidates(m,centers,typ,set(centers)|set(places.values())):
    trial=dict(places);trial[typ]=p; val=sum(score(m,centers,trial).values())
    key=(val, quality(m,p), -p[1], -p[0])
    if best is None or key>best[0]: best=(key,typ,p)
  if best is None or best[0][0] < sum(score(m,centers,places).values()): break
  _,typ,p=best; places[typ]=p; chosen_special+=1
 # Free infrastructure is always optional, but adding only when it is neutral
 # or beneficial avoids sacrificing a terrain feature just to fill space.
 for typ in FREE:
  bestp=None; base=sum(score(m,centers,places).values())
  for p in candidates(m,centers,typ,set(centers)|set(places.values())):
   trial=dict(places);trial[typ]=p; v=sum(score(m,centers,trial).values())
   if bestp is None or v>bestp[0]: bestp=(v,p)
  if bestp and bestp[0]>=base: places[typ]=bestp[1]
 return improve(m,centers,places)

def solve(m,ncity,pop):
 cap_each=1+max(0,(int(pop)-1)//3); cap=ncity*cap_each
 allp=[(x,y) for y in range(m.h) for x in range(m.w) if city_ok(m,(x,y))]
 if len(allp)<ncity: raise ValueError("map has fewer valid city-center tiles than requested cities")
 # Center ranking is a broad prefilter, followed by full placement evaluation.
 ranked=sorted(allp,key=lambda p:(-quality(m,p),p[1],p[0]))[:min(180,len(allp))]
 best=None
 for first in ranked:
  centers=[first]
  # Additional centers are districts too; choose nearby valid tiles when possible
  # so they can contribute generic adjacency while still satisfying the count.
  for _ in range(1,ncity):
   opts=[p for p in allp if p not in centers]
   if not opts: break
   centers.append(max(opts,key=lambda p:(quality(m,p)+sum(3-int(m.dist(p,c)==1) for c in centers),-p[1],-p[0])))
  places,val=make_layout(m,centers,cap)
  key=(val, tuple(centers), tuple(sorted(places.items())))
  if best is None or key>best[0]: best=(key,centers,places)
 if best is None: raise ValueError("no candidate layout")
 _,centers,places=best; adj=score(m,centers,places)
 if ncity==1: result={"city_center":list(centers[0])}
 else: result={"cities":[{"center":list(c)} for c in centers]}
 result.update({"placements":{t:list(p) for t,p in sorted(places.items())},"adjacency_bonuses":adj,"total_adjacency":sum(adj.values())})
 return result

def validate(m, scenario, sol):
 errors=[]; n=int(scenario.get("num_cities",1)); pop=scenario.get("population",1)
 if n==1:
  centers=[tuple(sol.get("city_center",()))]
 else: centers=[tuple(x.get("center",())) for x in sol.get("cities",[]) if isinstance(x,dict)]
 if len(centers)!=n: errors.append("wrong number of city centers")
 if len(set(centers))!=len(centers): errors.append("overlapping city centers")
 for p in centers:
  if len(p)!=2 or not all(isinstance(z,int) for z in p) or not city_ok(m,p,set(centers)-{p}): errors.append("invalid city center: %r"%(p,))
 places={}
 for t,p in sol.get("placements",{}).items():
  if t not in DISTRICTS: errors.append("unsupported district type: "+str(t)); continue
  if not isinstance(p,list) or len(p)!=2 or not all(isinstance(z,int) for z in p): errors.append("bad coordinate for "+t); continue
  places[t]=tuple(p)
 if len(set(places.values()))!=len(places) or set(places.values())&set(centers): errors.append("overlapping district placement")
 if sum(t in SPECIAL for t in places)>n*(1+(int(pop)-1)//3): errors.append("specialty district cap exceeded")
 for t,p in places.items():
  if not district_ok(m,t,p,centers,set(centers)|({q for a,q in places.items() if a!=t})): errors.append("invalid placement for "+t)
 actual=score(m,centers,places)
 if sol.get("adjacency_bonuses")!=actual: errors.append("adjacency_bonuses do not equal recomputed values")
 if sol.get("total_adjacency")!=sum(actual.values()): errors.append("total_adjacency does not equal adjacency sum")
 return {"valid":not errors,"errors":errors,"recomputed_adjacency":actual,"recomputed_total":sum(actual.values())}

def main():
 raw=sys.stdin.read().strip()
 if not raw: raise SystemExit("expected JSON configuration on stdin")
 cfg=json.loads(raw); sp=cfg["scenario"]
 with open(sp,encoding="utf-8") as f: scenario=json.load(f)
 mp=scenario["map_file"]
 if not os.path.isabs(mp):
  local=os.path.normpath(os.path.join(os.path.dirname(sp),mp))
  # Scenario manifests commonly use paths relative to the data root (e.g. maps/foo)
  # while scenarios themselves live in data/scenario_N.
  data_root=os.path.dirname(os.path.dirname(os.path.abspath(sp)))
  rooted=os.path.normpath(os.path.join(data_root,mp))
  mp=local if os.path.exists(local) else rooted
 m=Map(mp)
 if "solution" in cfg:
  src=cfg["solution"]
  sol=json.load(open(src,encoding="utf-8")) if isinstance(src,str) else src
  out=validate(m,scenario,sol)
 else:
  out=solve(m,scenario.get("num_cities",1),scenario.get("population",1))
  check=validate(m,scenario,out)
  if not check["valid"]: raise RuntimeError("internal output validation failed: "+"; ".join(check["errors"]))
  if cfg.get("output"):
   os.makedirs(os.path.dirname(os.path.abspath(cfg["output"])),exist_ok=True)
   with open(cfg["output"],"w",encoding="utf-8") as f: json.dump(out,f,indent=2); f.write("\n")
 print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__": main()
