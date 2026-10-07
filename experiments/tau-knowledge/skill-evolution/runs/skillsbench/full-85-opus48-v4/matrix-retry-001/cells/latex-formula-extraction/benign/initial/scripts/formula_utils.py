"""Reusable helpers for LaTeX display-formula extraction cleanup and validation.

All functions are pure and task-independent. They operate on the LaTeX content
between the $$ delimiters (not the wrappers themselves).
"""
import re

# ---------------------------------------------------------------------------
# Delimiter model for \left / \right validation.
# Longest / multi-character commands must precede single characters in the regex
# alternation so that e.g. \langle is not split into \ + l...
# ---------------------------------------------------------------------------
_DELIM_ALTS = [
    r"\\langle", r"\\rangle",
    r"\\lvert", r"\\rvert", r"\\lVert", r"\\rVert",
    r"\\\{", r"\\\}", r"\\\|",
    r"\|", r"\(", r"\)", r"\[", r"\]", r"<", r">", r"\.",
]
_LR_RE = re.compile(r"\\(left|right)\s*(" + "|".join(_DELIM_ALTS) + r")")

# Canonical closing delimiter for a given opening delimiter token (as matched).
_CLOSE_OF = {
    "(": ")",
    "[": "]",
    "\\{": "\\}",
    "\\langle": "\\rangle",
    "\\lvert": "\\rvert",
    "\\lVert": "\\rVert",
    "|": "|",
    "\\|": "\\|",
    ".": ".",
    "<": ">",
}


def canonical_close(delim):
    """Expected closing delimiter for an opener; identity if unknown/symmetric."""
    return _CLOSE_OF.get(delim, delim)


def strip_dollars(s):
    """Remove surrounding $$ (or $) wrappers and outer whitespace."""
    s = s.strip()
    for d in ("$$", "$"):
        if s.startswith(d) and s.endswith(d) and len(s) >= 2 * len(d):
            s = s[len(d):-len(d)]
            s = s.strip()
            break
    return s


def clean_formula(raw):
    """Apply the standard cleaning steps described in the background.

    - strip $$ wrappers
    - remove \\tag{...} / \\tag*{...}
    - remove trailing \\quad(n) / \\qquad(n) numbering
    - remove a trailing bare (n) equation number
    - strip trailing sentence punctuation (commas/periods)
    - normalize internal whitespace to single spaces
    Mathematical content is otherwise preserved exactly.
    """
    s = strip_dollars(raw)
    # equation tags anywhere
    s = re.sub(r"\\tag\*?\s*\{[^{}]*\}", "", s)
    changed = True
    while changed:
        before = s
        s = s.strip()
        # trailing \quad (1) / \qquad(2.3) / \, (1)
        s = re.sub(r"(\\q?quad|\\,|\\;|\\:|\\!)*\s*\(\s*[\d.]+\s*\)\s*$", "", s)
        # trailing standalone spacing command then nothing useful
        s = s.strip()
        # trailing sentence punctuation
        s = re.sub(r"[\s,\.]+$", lambda m: ("" if re.fullmatch(r"[\s,\.]+", m.group(0)) else m.group(0)), s)
        changed = (s != before)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def dedup(seq):
    """Order-preserving de-duplication."""
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def scan_delims(s):
    """Return list of dicts for each \\left/\\right delimiter in order."""
    toks = []
    for m in _LR_RE.finditer(s):
        toks.append({
            "kind": m.group(1),            # 'left' or 'right'
            "delim": m.group(2),           # matched delimiter text
            "delim_start": m.start(2),
            "delim_end": m.end(2),
        })
    return toks


def validate_brackets(s):
    """Validate \\left/\\right pairing.

    Returns dict with:
      tokens: scanned delimiter tokens
      mismatches: list of {open_delim, close_delim, expected_close, close_delim_start, close_delim_end}
      unmatched: list describing stray \\left or \\right
    """
    toks = scan_delims(s)
    stack = []
    mismatches = []
    unmatched = []
    for t in toks:
        if t["kind"] == "left":
            stack.append(t)
        else:  # right
            if not stack:
                unmatched.append({"type": "stray_right", "delim": t["delim"]})
                continue
            opener = stack.pop()
            expected = canonical_close(opener["delim"])
            if t["delim"] != expected:
                mismatches.append({
                    "open_delim": opener["delim"],
                    "close_delim": t["delim"],
                    "expected_close": expected,
                    "close_delim_start": t["delim_start"],
                    "close_delim_end": t["delim_end"],
                })
    for opener in stack:
        unmatched.append({"type": "unclosed_left", "delim": opener["delim"]})
    return {"tokens": toks, "mismatches": mismatches, "unmatched": unmatched}


def auto_fix_brackets(s):
    """Produce a candidate fix: force each \\right to match its \\left opener.

    Replacements are applied from the end of the string backward so earlier
    indices stay valid. Returns the (possibly unchanged) string. This is only a
    default heuristic; the correct delimiter may be inferred from context and
    should then be supplied as an explicit manual correction.
    """
    res = validate_brackets(s)
    if not res["mismatches"]:
        return s
    out = s
    for mm in sorted(res["mismatches"], key=lambda m: m["close_delim_start"], reverse=True):
        start, end = mm["close_delim_start"], mm["close_delim_end"]
        out = out[:start] + mm["expected_close"] + out[end:]
    return out
