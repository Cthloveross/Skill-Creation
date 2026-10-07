#!/usr/bin/env python3
"""End-to-end fake-citation detector.

stdin  (JSON, optional): {"bib_path":str,"out_path":str,"offline":bool}
stdout (JSON): report with per-entry verdicts.
side effect: writes out_path with {"fake_citations":[sorted cleaned titles]}.

Method: DOI resolution (CrossRef + doi.org) -> registrant analysis ->
title search (CrossRef + Semantic Scholar) -> provenance.
"""
import json
import os
import sys
import time
import difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_bib import parse_bibtex, clean_title, normalize_for_match  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- HTTP helpers (requests if available, else urllib) ----
try:
    import requests  # type: ignore
    _HAVE_REQUESTS = True
except Exception:  # pragma: no cover
    _HAVE_REQUESTS = False
    import urllib.request
    import urllib.error

HEADERS = {'User-Agent': 'citation-check/1.0 (mailto:verify@example.org)'}


def _http_get(url, timeout=15, method='GET'):
    """Return (status_code, text) or (None, None) on hard failure."""
    last = (None, None)
    for attempt in range(3):
        try:
            if _HAVE_REQUESTS:
                r = requests.request(method, url, headers=HEADERS,
                                     timeout=timeout, allow_redirects=True)
                return r.status_code, (r.text if method == 'GET' else '')
            else:
                req = urllib.request.Request(url, headers=HEADERS, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode('utf-8', 'replace') if method == 'GET' else ''
                    return resp.getcode(), body
        except Exception as e:  # urllib HTTPError has .code
            code = getattr(e, 'code', None)
            if code is not None:
                return code, ''
            last = (None, None)
            time.sleep(1.0 * (attempt + 1))
    return last


def load_known_registrants():
    codes = set()
    path = os.path.join(HERE, '..', 'references', 'registrants.txt')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                code = line.split()[0].strip()
                if code.startswith('10.'):
                    codes.add(code)
    except Exception:
        pass
    return codes


def doi_registrant(doi):
    doi = doi.strip()
    if '/' not in doi:
        return None
    return doi.split('/', 1)[0]


def resolve_doi(doi):
    """Return 'resolved' | 'absent' | 'unknown'.
    resolved: present in CrossRef or doi.org redirects to publisher.
    absent:   CrossRef 404 AND doi.org 404 (clean negative).
    unknown:  network failure prevents a clean decision.
    """
    doi = doi.strip()
    cr_status, _ = _http_get('https://api.crossref.org/works/' + doi)
    if cr_status == 200:
        return 'resolved'
    do_status, _ = _http_get('https://doi.org/' + doi, method='GET')
    if do_status and 200 <= do_status < 400:
        return 'resolved'
    # Clean negatives
    cr_neg = cr_status == 404
    do_neg = do_status == 404
    if cr_neg and (do_neg or do_status is None):
        # CrossRef is authoritative for scholarly DOIs
        if do_neg:
            return 'absent'
        return 'absent' if cr_neg else 'unknown'
    if cr_neg and do_neg:
        return 'absent'
    return 'unknown'


def title_found(title):
    """Return 'found' | 'absent' | 'unknown' using CrossRef + Semantic Scholar."""
    target = normalize_for_match(title)
    if not target:
        return 'unknown'
    saw_response = False

    # CrossRef bibliographic query
    import urllib.parse as up
    q = up.quote(clean_title(title))
    cr_status, cr_body = _http_get(
        'https://api.crossref.org/works?rows=5&query.bibliographic=' + q)
    if cr_status == 200 and cr_body:
        saw_response = True
        try:
            items = json.loads(cr_body).get('message', {}).get('items', [])
            for it in items:
                for t in it.get('title', []) or []:
                    if _close(target, normalize_for_match(t)):
                        return 'found'
        except Exception:
            pass

    # Semantic Scholar search
    ss_status, ss_body = _http_get(
        'https://api.semanticscholar.org/graph/v1/paper/search?limit=5&fields=title&query=' + q)
    if ss_status == 200 and ss_body:
        saw_response = True
        try:
            for it in json.loads(ss_body).get('data', []) or []:
                t = it.get('title') or ''
                if _close(target, normalize_for_match(t)):
                    return 'found'
        except Exception:
            pass

    return 'absent' if saw_response else 'unknown'


def _close(a, b, threshold=0.9):
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def classify(entry, known_registrants, offline):
    doi = entry.get('doi', '').strip()
    title = entry.get('title', '')
    has_provenance = any(k in entry for k in ('biburl', 'bibsource'))

    if doi:
        reg = doi_registrant(doi)
        reg_known = reg in known_registrants if reg else False
        if offline:
            if reg and not reg_known:
                return 'fake', 'offline: unknown DOI registrant %s' % reg
            return 'unverified', 'offline: cannot resolve DOI'
        status = resolve_doi(doi)
        if status == 'resolved':
            return 'real', 'DOI resolves'
        if status == 'absent':
            note = 'DOI does not resolve (CrossRef/doi.org 404)'
            if reg and not reg_known:
                note += '; unknown registrant %s' % reg
            return 'fake', note
        # unknown resolution
        if reg and not reg_known:
            return 'fake', 'DOI resolution failed + unknown registrant %s' % reg
        return 'unverified', 'DOI resolution network-inconclusive'

    # No DOI
    if offline:
        return 'unverified', 'offline: no DOI, cannot search'
    status = title_found(title)
    if status == 'found':
        return 'real', 'title found in database'
    if status == 'absent':
        if has_provenance:
            return 'unverified', 'no DB match but has DBLP/indexer provenance'
        return 'fake', 'no DOI and title absent from CrossRef + Semantic Scholar'
    return 'unverified', 'title search network-inconclusive'


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    bib_path = req.get('bib_path', '/root/test.bib')
    out_path = req.get('out_path', '/root/answer.json')
    offline = bool(req.get('offline', False))

    if not os.path.exists(bib_path):
        print(json.dumps({'error': 'bib file not found: %s' % bib_path}))
        sys.exit(1)

    with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    entries = parse_bibtex(text)
    known = load_known_registrants()

    details = []
    fake_titles = []
    for e in entries:
        verdict, reason = classify(e, known, offline)
        ctitle = clean_title(e.get('title', ''))
        details.append({
            'key': e.get('key'),
            'title': ctitle,
            'doi': e.get('doi', ''),
            'verdict': verdict,
            'reason': reason,
        })
        if verdict == 'fake' and ctitle:
            fake_titles.append(ctitle)

    fake_titles = sorted(set(fake_titles), key=lambda s: s.lower())
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'fake_citations': fake_titles}, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        'out_path': out_path,
        'num_entries': len(entries),
        'fake_citations': fake_titles,
        'details': details,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
