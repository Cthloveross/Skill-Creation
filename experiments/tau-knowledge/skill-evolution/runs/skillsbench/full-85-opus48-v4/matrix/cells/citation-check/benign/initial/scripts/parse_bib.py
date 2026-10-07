#!/usr/bin/env python3
"""Parse BibTeX and clean titles.

Standalone: stdin {"bib_path": "..."} -> stdout JSON list of entries.
Importable: parse_bibtex(text) -> [ {key,type, field:value...} ],
            clean_title(raw) -> cleaned str.
"""
import json
import re
import sys


def _split_entries(text):
    entries = []
    i = 0
    n = len(text)
    while i < n:
        at = text.find('@', i)
        if at == -1:
            break
        brace = text.find('{', at)
        if brace == -1:
            break
        etype = text[at + 1:brace].strip().lower()
        # Skip @comment/@string/@preamble as citation entries but still balance
        depth = 0
        j = brace
        while j < n:
            c = text[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[brace + 1:j]
        entries.append((etype, body))
        i = j + 1
    return entries


def _parse_fields(body):
    # First token up to first comma is the citation key
    comma = body.find(',')
    if comma == -1:
        return None, {}
    key = body[:comma].strip()
    rest = body[comma + 1:]
    fields = {}
    i = 0
    n = len(rest)
    while i < n:
        eq = rest.find('=', i)
        if eq == -1:
            break
        fname = rest[i:eq].strip().strip(',').lower()
        j = eq + 1
        while j < n and rest[j] in ' \t\r\n':
            j += 1
        if j >= n:
            break
        if rest[j] == '{':
            depth = 0
            k = j
            while k < n:
                if rest[k] == '{':
                    depth += 1
                elif rest[k] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            value = rest[j + 1:k]
            i = k + 1
        elif rest[j] == '"':
            k = j + 1
            while k < n and rest[k] != '"':
                k += 1
            value = rest[j + 1:k]
            i = k + 1
        else:
            k = j
            while k < n and rest[k] not in ',\n':
                k += 1
            value = rest[j:k]
            i = k + 1
        # advance past trailing comma/whitespace
        while i < n and rest[i] in ' \t\r\n,':
            i += 1
        if fname:
            fields[fname] = value.strip()
    return key, fields


def parse_bibtex(text):
    out = []
    for etype, body in _split_entries(text):
        if etype in ('comment', 'string', 'preamble'):
            continue
        key, fields = _parse_fields(body)
        if key is None:
            continue
        entry = {'key': key, 'type': etype}
        entry.update(fields)
        out.append(entry)
    return out


def clean_title(raw):
    if not raw:
        return ''
    s = raw
    # Remove LaTeX commands like \emph{..}, \textbf{..} keeping arg content
    s = re.sub(r'\\[a-zA-Z]+\s*\{', '{', s)
    # Remove remaining backslash commands/escapes
    s = re.sub(r'\\[a-zA-Z]+', '', s)
    s = s.replace('\\&', '&').replace('\\%', '%').replace('\\_', '_')
    s = s.replace('\\$', '$').replace('\\#', '#')
    s = s.replace('\\', '')
    # Drop braces
    s = s.replace('{', '').replace('}', '')
    # Collapse whitespace/newlines
    s = re.sub(r'\s+', ' ', s).strip()
    # Trim trailing punctuation artifacts
    return s


def normalize_for_match(title):
    s = clean_title(title).lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


if __name__ == '__main__':
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    path = req.get('bib_path', '/root/test.bib')
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    entries = parse_bibtex(text)
    for e in entries:
        e['clean_title'] = clean_title(e.get('title', ''))
    print(json.dumps(entries, ensure_ascii=False, indent=2))
