#!/usr/bin/env python3
"""Reusable retrieval helpers for the enterprise-information-search corpus.

The corpus (observed, but re-verify with scripts/inspect.py) has, per product
file under DATA/products/<Product>.json, these top-level arrays:
  - documents[]: {content, date, author (an eid), document_link, feedback?,
                  type, id}. `author` is the employee-id of the author; several
                  version rows (draft/final/latest) share the same `type`.
  - meeting_transcripts[]: {transcript, date, document_type, participants
                  (list of eids), id}. The transcript text begins with an
                  "Attendees" line whose comma-separated NAMES correspond
                  POSITIONALLY to the `participants` eids. The facilitator who
                  asks for feedback is usually the document author and is NOT in
                  participants/attendees; everyone in participants is a reviewer.
  - slack[]: {Channel, Message:{User:{userId (eid), timestamp, text, ...}},
              ThreadReplies[], id}.
  - urls[]: {link, description, id}.
  - prs[]: {..., user:{login (eid)}, reviews[], ...}.

This module exposes stdin->stdout ops. Read ONE JSON object from stdin and emit
ONE JSON object to stdout. Nothing about products/eids/urls is hardcoded; every
value is derived from the supplied product file at runtime.

Ops:
  {"op":"authors_reviewers","product_file":PATH,"doc_type":"Market Research Report"}
     -> {"authors":[eid,...], "reviewers":[eid,...], "transcript_id":...}
     authors   = distinct `author` eids of documents whose `type`==doc_type.
     reviewers = participants (eids) of the meeting_transcript whose
                 `document_type`==doc_type (these are the people who reviewed /
                 gave feedback on that document). Empty if no such transcript.

  {"op":"competitor_demos","product_file":PATH}
     -> {"shared_demos":[{shared_by,url,text}...],
         "external_demo_urls":[{link,description}...]}
     Finds demo links shared in slack ("take a look at <X> ... demo ... <url>")
     and demo URLs in urls[] whose description mentions "demo". Competitor demos
     are the EXTERNAL ones (hostname is not the org-internal slack host, default
     "sf-internal"); the org's own product demos live on the internal host and
     must be excluded when the question asks for *competitor* demos.

  {"op":"competitor_insights","product_file":PATH}
     -> {"insight_providers":[eid,...], "messages":[{userId,text}...]}
     Team members who PROVIDED insights on competitors' strengths/weaknesses.
     The corpus convention is an intro message "I was reading about <Competitor>
     ..." that then discusses strengths/weaknesses. People who only acknowledge
     ("Thanks for the insights ...") without an intro message are NOT providers.
"""
import json, sys, re

INTERNAL_HOST_DEFAULT = "sf-internal"
URL_RE = re.compile(r"https?://[^\s)\]]+", re.I)
INTRO_RE = re.compile(r"i was reading about", re.I)


def load(p):
    with open(p) as f:
        return json.load(f)


def iter_slack(d):
    """Yield (userId, text) for every slack message and threaded reply."""
    for s in d.get("slack", []):
        u = (s.get("Message", {}) or {}).get("User", {}) or {}
        if u:
            yield u.get("userId"), u.get("text", "") or ""
        for r in s.get("ThreadReplies", []) or []:
            ru = r.get("User", r) if isinstance(r, dict) else {}
            yield ru.get("userId"), ru.get("text", "") or ""


def authors_reviewers(product_file, doc_type):
    d = load(product_file)
    dt = str(doc_type).strip().lower()
    authors = []
    for doc in d.get("documents", []) or []:
        if str(doc.get("type", "")).strip().lower() == dt:
            a = doc.get("author")
            if a and a not in authors:
                authors.append(a)
    reviewers, tid = [], None
    for mt in d.get("meeting_transcripts", []) or []:
        if str(mt.get("document_type", "")).strip().lower() == dt:
            tid = mt.get("id")
            for p in mt.get("participants", []) or []:
                if p not in reviewers:
                    reviewers.append(p)
            break
    return {"authors": authors, "reviewers": reviewers, "transcript_id": tid}


def competitor_demos(product_file, internal_host=INTERNAL_HOST_DEFAULT):
    d = load(product_file)
    shared = []
    for uid, txt in iter_slack(d):
        low = txt.lower()
        if "demo" in low and ("take a look" in low or "available here" in low):
            m = URL_RE.search(txt)
            if m:
                shared.append({"shared_by": uid, "url": m.group(0),
                               "text": txt[:160]})
    ext = []
    for u in d.get("urls", []) or []:
        link = u.get("link", "") or ""
        if "demo" in str(u.get("description", "")).lower() and internal_host not in link:
            ext.append({"link": link, "description": u.get("description")})
    # external shared demos only (competitor demos live off the internal host)
    ext_shared = [s for s in shared if internal_host not in s["url"]]
    return {"shared_demos": shared, "external_shared_demos": ext_shared,
            "external_demo_urls": ext}


def competitor_insights(product_file):
    d = load(product_file)
    providers, msgs = [], []
    for uid, txt in iter_slack(d):
        if INTRO_RE.search(txt):
            msgs.append({"userId": uid, "text": txt[:200]})
            if uid and uid not in providers:
                providers.append(uid)
    return {"insight_providers": providers, "messages": msgs}


def main():
    req = json.load(sys.stdin)
    op = req.get("op")
    if op == "authors_reviewers":
        out = authors_reviewers(req["product_file"], req["doc_type"])
    elif op == "competitor_demos":
        out = competitor_demos(req["product_file"],
                               req.get("internal_host", INTERNAL_HOST_DEFAULT))
    elif op == "competitor_insights":
        out = competitor_insights(req["product_file"])
    else:
        out = {"error": "unknown op",
               "ops": ["authors_reviewers", "competitor_demos",
                       "competitor_insights"]}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
