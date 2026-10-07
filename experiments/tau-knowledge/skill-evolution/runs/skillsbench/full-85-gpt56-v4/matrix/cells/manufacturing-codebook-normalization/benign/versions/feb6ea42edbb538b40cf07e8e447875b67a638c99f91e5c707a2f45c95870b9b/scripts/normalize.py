#!/usr/bin/env python3
"""Normalize product-scoped manufacturing defect log CSVs.

Read one JSON configuration object from stdin and write a JSON summary to stdout.
The result document is written to ``output_path``.  Standard library only.
"""
import csv, glob, json, os, re, sys, unicodedata
from collections import defaultdict


def fail(message):
    raise ValueError(message)


def norm(value):
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    s = re.sub(r"[\s_\-./\\,;:|()\[\]{}]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def compact(value):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", norm(value))


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(16384); fh.seek(0)
        try: dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error: dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames: fail("CSV has no header: " + path)
        headers = [(h or "").strip() for h in reader.fieldnames]
        return headers, [{(k or "").strip(): (v or "") for k, v in r.items()} for r in reader]


HEADER_TARGETS = {
    "record_id": ("recordid", "record", "logid", "eventid", "id"),
    "product_id": ("productid", "product", "model", "family", "sku"),
    "station": ("station", "teststation", "stage", "process"),
    "engineer_id": ("engineerid", "engineer", "operator", "author", "user"),
    "raw_reason_text": ("rawreasontext", "reasontext", "reason", "defecttext", "comment", "description", "note", "failure"),
    "code": ("defectcode", "errorcode", "failurecode", "code"),
    "label": ("defectlabel", "standardlabel", "label", "defectname", "standardreason", "reasonname", "name"),
}

def choose_header(headers, role, override=None, required=False):
    if override:
        if override not in headers: fail("Configured %s header is absent: %r" % (role, override))
        return override
    scores = []
    for h in headers:
        nh = norm(h).replace(" ", "")
        score = 0
        for rank, target in enumerate(HEADER_TARGETS[role]):
            if nh == target: score = max(score, 100-rank)
            elif target in nh: score = max(score, 65-rank)
        scores.append((score, h))
    scores.sort(reverse=True)
    if not scores or scores[0][0] == 0:
        if required: fail("Cannot infer required %s column; headers are %s" % (role, headers))
        return None
    tied = [h for score,h in scores if score == scores[0][0]]
    if len(tied) != 1: fail("Ambiguous %s columns %s; set an explicit role mapping" % (role, tied))
    return scores[0][1]


def station_allowed(scope, observed):
    if not str(scope or "").strip() or not str(observed or "").strip(): return True
    actual = norm(observed)
    allowed = [norm(x) for x in re.split(r"[;,/|；\n]", str(scope)) if norm(x)]
    return any(x in ("*", "all", "any", "na", "n a") or x == actual for x in allowed)


def source_keys(path, rows, product_col):
    stem = re.sub(r"^(?:codebook|codes?|defects?)[ _-]*", "", os.path.splitext(os.path.basename(path))[0], flags=re.I)
    keys = {norm(stem), compact(stem)}
    if product_col:
        keys.update(x for r in rows for x in (norm(r.get(product_col,"")), compact(r.get(product_col,""))) if x)
    return {x for x in keys if x}


def select_sources(product, sources):
    pn, pc = norm(product), compact(product)
    exact = [s for s in sources if pn in s["keys"] or pc in s["keys"]]
    if exact: return exact
    possible = [s for s in sources if any(k and (pc.startswith(k) or k.startswith(pc)) for k in s["keys"])]
    return possible if len(possible) == 1 else []

# Families are semantic, not codebook-specific: a new codebook can still supply its
# own aliases and identifiers, while these cover common noisy manufacturing wording.
FAMILY_PATTERNS = {
 "open": ("open", "开路"), "short": ("short", "短路", "bridge", "连锡", "桥连"),
 "cold": ("cold solder", "虚焊", "浮高", "intermittent", "功能不稳"),
 "fixture_contact": ("fixture contact", "contact unstable", "接触不良", "pogo", "reseat", "治具", "探针接触"),
 "program": ("program", "flash write", "flash fail", "烧录失败", "写入失败", "重烧"),
 "hipot": ("hipot", "leakage", "漏电", "漏點", "绝缘不良"),
 "idle": ("idle current", "current high", "功耗高", "静态电流", "icc"),
 "verify": ("checksum", "crc", "verify fail", "校验失败"),
 "boot": ("boot fail", "os fail", "启动失败", "启动不了", "卡logo", "cannot boot", "stuck"),
 "version": ("version mismatch", "版本不符", "wrong fw", "下错程序"),
 "high_res": ("high res", "highres"),
 "cal_data": ("cal data", "rf cal", "校准数据", "写读失败", "recal"),
 "connector": ("connector wear", "insertion loss", "插拔", "sma"),
 "contamination": ("contamination", "residue", "助焊剂", "清洗"),
 "missing": ("missing", "少件", "漏贴"), "reverse": ("reversed", "polarity", "反向", "装反", "极性"),
 "pressure": ("pressure mark", "pad damage", "压伤", "trace damage"),
 "esd": ("esd", "静电", "handling"), "probe_worn": ("probe worn", "探针磨损", "replace pin", "换针"),
}
GENERIC_ALIAS = {"open","开路","short","短路","bridge","连锡","桥连","cold solder","虚焊","浮高","fixture","pogo","接触不良","探针","reseat","flash fail","烧录失败","write fail","program fail","hipot","leakage","漏电","绝缘不良","current high","icc","功耗高","静态电流","missing","少件","reversed","polarity","反向","pressure mark","压伤","pad damage","esd","静电","handling","pin"}


def phrase_family(label, aliases):
    text = " ".join([norm(label)] + [norm(a) for a in aliases])
    # Avoid classing pressure-mark reports as generic fixture-contact reports.
    if any(x in text for x in ("pressure mark", "pad damage", "压伤")): return "pressure"
    if "probe worn" in text or "探针磨损" in text: return "probe_worn"
    if "fixture contact" in text or "contact unstable" in text: return "fixture_contact"
    for family, patterns in FAMILY_PATTERNS.items():
        if any(norm(p) in text for p in patterns): return family
    return "other"


def identifier_terms(label, aliases):
    """Extract component and net references without retaining surrounding label prose."""
    terms=set()
    for phrase in [label] + list(aliases):
        # Nets are usually underscore-separated; component designators normally end
        # in a digit. Both forms are meaningful only as exact compact substrings.
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b|\b[A-Za-z]{1,5}\d+\b", phrase):
            c=compact(token)
            if len(c)>=2: terms.add(c)
    return sorted(terms, key=lambda x: (-len(x), x))

def build_sources(paths, config):
    cfg = config.get("codebook_roles") or {}; sources=[]
    for path in paths:
        headers, rows=read_csv(path)
        code_col=choose_header(headers,"code",cfg.get("code"),True)
        label_col=choose_header(headers,"label",cfg.get("label"),True)
        prod_col=choose_header(headers,"product_id",cfg.get("product_id"),False)
        station_col=choose_header(headers,"station",cfg.get("station"),False)
        exclude={code_col,label_col,prod_col,station_col}
        by_label=defaultdict(list)
        for r in rows:
            code,label=r.get(code_col,"").strip(),r.get(label_col,"").strip()
            if not code or not label: continue
            aliases=[]
            for h in headers:
                if h in exclude: continue
                # Examples/aliases/descriptions are free-text evidence. Category and
                # taxonomy fields describe the codebook row, not phrases engineers wrote.
                hn=norm(h)
                if any(x in hn for x in ("category", "class", "level", "severity", "priority", "type")):
                    continue
                v=r.get(h,"").strip()
                if v and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)",v):
                    aliases.extend(x.strip() for x in re.split(r"[,;；|\n]",v) if x.strip())
            by_label[label].append({"code":code,"label":label,"scope":r.get(station_col,"") if station_col else "","aliases":aliases})
        if not by_label: fail("No usable code/label rows in " + path)
        groups=[]
        for label, entries in by_label.items():
            aliases=[a for e in entries for a in e["aliases"]]
            groups.append({"label":label,"entries":entries,"family":phrase_family(label,aliases),"identifiers":identifier_terms(label,aliases),"aliases":aliases})
        sources.append({"path":path,"keys":source_keys(path,rows,prod_col),"groups":groups})
    return sources


def has_pattern(ntext, pattern):
    p=norm(pattern)
    if not p:return False
    if re.fullmatch(r"[a-z0-9]+",p): return bool(re.search(r"(?<![a-z0-9])"+re.escape(p)+r"(?![a-z0-9])",ntext))
    return p in ntext

def family_strength(text, family):
    n=norm(text)
    if family == "pressure": return 1.0 if any(has_pattern(n,p) for p in FAMILY_PATTERNS[family]) else 0.0
    if family == "probe_worn": return 1.0 if any(has_pattern(n,p) for p in FAMILY_PATTERNS[family]) else 0.0
    if family == "fixture_contact":
        return 1.0 if any(has_pattern(n,p) for p in FAMILY_PATTERNS[family]) else 0.0
    pats=FAMILY_PATTERNS.get(family,())
    return min(1.0, 0.72 + .14*sum(has_pattern(n,p) for p in pats)) if any(has_pattern(n,p) for p in pats) else 0.0

def rank_groups(text, groups, station):
    ct=compact(text); ranked=[]
    for g in groups:
        compatible=[e for e in g["entries"] if station_allowed(e["scope"],station)]
        if not compatible: continue
        fs=family_strength(text,g["family"])
        refs=[r for r in g["identifiers"] if r in ct]
        # A codebook phrase can be a useful additional signal for unfamiliar families.
        alias_hit=any(len(compact(a))>=4 and norm(a) not in GENERIC_ALIAS and compact(a) in ct for a in g["aliases"])
        if g["family"] == "other" and alias_hit: fs=.78
        score=fs + min(.12,.06*len(refs))
        ranked.append((min(score,1.0),len(refs),g,compatible))
    return sorted(ranked,key=lambda x:(-x[0],-x[1],x[2]["label"]))

def choose_decision(span, groups, station, accept, margin):
    ranked=rank_groups(span,groups,station)
    if not ranked or ranked[0][0] <= 0:
        return "UNKNOWN","",round(.07+min(.22,len(compact(span))/180),4),"No compatible product-codebook concept is evidenced by verbatim span %r."%span,None
    score, refs, g, entries=ranked[0]
    runner=ranked[1][0] if len(ranked)>1 else 0.0
    # Identifier-bearing concepts need a reference when their family is inherently
    # component-specific. A single unique reference is allowed; tied references route review.
    needs_ref=g["family"] in {"open","short","cold","missing","reverse"} and bool(g["identifiers"])
    enough=not needs_ref or (refs >= (2 if g["family"] in {"open","short"} and len(g["identifiers"]) >= 2 else 1))
    ambiguous=runner>0 and score-runner<margin and ranked[1][2]["label"] != g["label"]
    if score<accept or not enough or ambiguous:
        why="missing a distinguishing component/net reference" if not enough else ("too close to another product-scoped concept" if ambiguous else "below configured acceptance score")
        conf=round(min(.56,.10+.34*score+.05*max(0,score-runner)),4)
        return "UNKNOWN","",conf,"Verbatim span %r is routed to review: best applicable candidate %r scored %.3f (runner-up %.3f; %s)."%(span,g["label"],score,runner,why),g["label"]
    entry=sorted(entries,key=lambda e:e["code"])[0]
    conf=round(min(.995,.70+.22*score+.06*min(1,(score-runner)/max(margin,.01))),4)
    return entry["code"],entry["label"],conf,"Verbatim span %r matched applicable product-codebook label %r using %s evidence (score %.3f; runner-up %.3f)."%(span,entry["label"],g["family"],score,runner),g["label"]

def semantic_families(text):
    """Concept families visible in a punctuation fragment, without forcing a code."""
    n = norm(text)
    return {family for family in FAMILY_PATTERNS if family_strength(n, family) > 0}

def split_segments(raw, groups, station):
    """Split list-like punctuation while retaining modifiers and bilingual restatements.

    Code-level certainty is intentionally not required for a boundary: an unsupported
    electrical observation before a supported fixture observation must remain its own
    UNKNOWN segment rather than swallowing the fixture mention.
    """
    raw=str(raw or "")
    if not raw.strip(): return []
    parts=[]; last=0
    for m in re.finditer(r"(?:\r?\n|[;；&+、]|\s+/\s+|[,，])",raw):
        if raw[last:m.start()].strip(): parts.append((last,m.start()))
        last=m.end()
    if raw[last:].strip(): parts.append((last,len(raw)))
    if not parts: return [raw.strip()]
    out=[]; cur_start,cur_end=parts[0]; current=semantic_families(raw[cur_start:cur_end])
    for start,end in parts[1:]:
        observed=semantic_families(raw[start:end])
        # Cold-solder wording often explains an open/short observation; it is not a
        # second list item merely because a comma precedes it.
        modifier = observed <= {"cold"} and bool(current & {"open","short"})
        same = bool(current & observed)
        if current and observed and not same and not modifier:
            span=raw[cur_start:cur_end].strip()
            if span: out.append(span)
            cur_start,cur_end,current=start,end,observed
        else:
            cur_end=end
            current |= observed
    span=raw[cur_start:cur_end].strip()
    if span: out.append(span)
    return out or [raw.strip()]

def validate(output, source_rows, sources):
    records=output.get("records")
    if not isinstance(records,list) or len(records)!=len(source_rows):fail("Validation failed: output does not represent every input record exactly once")
    ids=set()
    for rec in records:
        rid=str(rec.get("record_id", "")); product=str(rec.get("product_id", "")); raw=str(rec.get("raw_reason_text", ""))
        if rid in ids:fail("Validation failed: duplicate record_id "+rid)
        ids.add(rid)
        selected=select_sources(product,sources)
        allowed={e["code"]:e for s in selected for g in s["groups"] for e in g["entries"]}
        seen=set()
        for i,item in enumerate(rec.get("normalized",[]),1):
            expected=rid+"-S"+str(i)
            if item.get("segment_id")!=expected or expected in seen:fail("Validation failed: invalid segment identifier for "+rid)
            seen.add(expected); span=item.get("span_text",""); conf=item.get("confidence")
            if not isinstance(span,str) or not span or span not in raw:fail("Validation failed: non-verbatim or empty span for "+rid)
            if not isinstance(conf,(int,float)) or not 0<=conf<=1:fail("Validation failed: confidence out of range for "+rid)
            if not isinstance(item.get("rationale"),str) or not item["rationale"].strip():fail("Validation failed: empty rationale for "+rid)
            if item.get("pred_code")=="UNKNOWN":
                if item.get("pred_label")!="":fail("Validation failed: UNKNOWN must have empty label")
            else:
                e=allowed.get(item.get("pred_code"))
                if not e or item.get("pred_label")!=e["label"]:fail("Validation failed: code/label outside product codebook for "+rid)
                if not station_allowed(e["scope"],rec.get("station","")):fail("Validation failed: station-incompatible code for "+rid)

def main():
    config=json.loads(sys.stdin.read() or "{}")
    paths=config.get("codebook_paths") or sorted(glob.glob(config.get("codebook_glob","/app/data/codebook_*.csv")))
    if not paths:fail("No codebook files found")
    accept=float(config.get("accept_score",.70)); margin=float(config.get("ambiguity_margin",.055))
    if not 0<=accept<=1 or margin<0:fail("accept_score must be in [0,1] and ambiguity_margin must be nonnegative")
    headers,rows=read_csv(config.get("logs_path","/app/data/test_center_logs.csv")); cfg=config.get("log_roles") or {}
    roles={r:choose_header(headers,r,cfg.get(r),True) for r in ("record_id","product_id","station","engineer_id","raw_reason_text")}
    sources=build_sources(paths,config); records=[]; accepted=unknown=0
    for row in rows:
        rec={k:str(row.get(v,"")) for k,v in roles.items()}; selected=select_sources(rec["product_id"],sources)
        groups=[g for s in selected for g in s["groups"]]; normalized=[]
        for i,span in enumerate(split_segments(rec["raw_reason_text"],groups,rec["station"]),1):
            code,label,conf,rationale,_=choose_decision(span,groups,rec["station"],accept,margin)
            normalized.append({"segment_id":rec["record_id"]+"-S"+str(i),"span_text":span,"pred_code":code,"pred_label":label,"confidence":conf,"rationale":rationale})
            if code=="UNKNOWN":unknown+=1
            else:accepted+=1
        rec["normalized"]=normalized; records.append(rec)
    output={"records":records};validate(output,rows,sources)
    output_path=config.get("output_path","/app/output/solution.json"); parent=os.path.dirname(output_path)
    if parent:os.makedirs(parent,exist_ok=True)
    with open(output_path,"w",encoding="utf-8") as fh:json.dump(output,fh,ensure_ascii=False,indent=2);fh.write("\n")
    print(json.dumps({"output_path":output_path,"records":len(records),"accepted_segments":accepted,"unknown_segments":unknown,"resolved_log_roles":roles},ensure_ascii=False))
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(json.dumps({"error":str(exc)}),file=sys.stderr);sys.exit(2)
