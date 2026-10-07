"""Shared helpers for display-formula cleaning, bracket checking, typos.

Pure-Python, no third-party dependencies.
"""
import re
import difflib

# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"\\tag\*?\s*\{[^{}]*\}")
# trailing equation numbers like \quad (1)  \qquad (2.3)  \, (4)
_TRAIL_NUM_CMD_RE = re.compile(
    r"(?:\\(?:quad|qquad|,|;|:|!|\s))*\s*\(\s*[0-9][0-9A-Za-z.\-]*\s*\)\s*$"
)
# a bare trailing (1) / (2.3) equation number
_TRAIL_NUM_RE = re.compile(r"\(\s*[0-9][0-9A-Za-z.\-]*\s*\)\s*$")


def clean_formula(s):
    """Apply the standard cleaning steps to one raw formula string.

    Removes surrounding $$, \\tag{...}, trailing equation numbers and trailing
    grammatical comma/period, then collapses whitespace. Mathematical content
    is preserved.
    """
    if s is None:
        return ""
    s = s.strip()
    # strip surrounding $$ or $ delimiters if the caller left them in
    if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
        s = s[2:-2]
    elif s.startswith("$") and s.endswith("$") and len(s) >= 2:
        s = s[1:-1]
    s = s.strip()
    # remove \tag{...}
    s = _TAG_RE.sub(" ", s)
    # remove trailing equation-number artifacts (loop in case of leftovers)
    for _ in range(3):
        new = _TRAIL_NUM_CMD_RE.sub("", s).rstrip()
        new = _TRAIL_NUM_RE.sub("", new).rstrip()
        if new == s:
            break
        s = new
    # strip a single trailing grammatical comma or period (and spacing before)
    s = re.sub(r"(?:\\[,;:! ])*\s*[,.]\s*$", "", s).rstrip()
    # collapse internal whitespace / newlines to single spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Delimiter / bracket checking for \left ... \right
# ---------------------------------------------------------------------------

# ordered longest-first so multi-char tokens match before single chars
_DELIMS = [
    (r"\langle", "angle", "open"),
    (r"\rangle", "angle", "close"),
    (r"\lvert", "vert", "open"),
    (r"\rvert", "vert", "close"),
    (r"\lVert", "Vert", "open"),
    (r"\rVert", "Vert", "close"),
    (r"\lceil", "ceil", "open"),
    (r"\rceil", "ceil", "close"),
    (r"\lfloor", "floor", "open"),
    (r"\rfloor", "floor", "close"),
    (r"\{", "brace", "open"),
    (r"\}", "brace", "close"),
    (r"\|", "Vert", "both"),
    (r"\.", "dot", "both"),  # \right. etc.
    ("(", "paren", "open"),
    (")", "paren", "close"),
    ("[", "square", "open"),
    ("]", "square", "close"),
    ("<", "angle", "open"),
    (">", "angle", "close"),
    ("|", "vert", "both"),
    (".", "dot", "both"),
]

# canonical open/close token for each group when writing a fix
_GROUP_OPEN = {
    "paren": "(", "square": "[", "brace": "\\{", "angle": "\\langle",
    "vert": "|", "Vert": "\\|", "ceil": "\\lceil", "floor": "\\lfloor",
    "dot": ".",
}
_GROUP_CLOSE = {
    "paren": ")", "square": "]", "brace": "\\}", "angle": "\\rangle",
    "vert": "|", "Vert": "\\|", "ceil": "\\rceil", "floor": "\\rfloor",
    "dot": ".",
}


def _read_delim(s, i):
    """Return (token, group, side, new_index) for the delimiter at position i,
    skipping leading spaces. Returns None if nothing matches."""
    j = i
    while j < len(s) and s[j] in " \t":
        j += 1
    for tok, group, side in _DELIMS:
        if s.startswith(tok, j):
            return tok, group, side, j + len(tok)
    return None


def find_left_right(s):
    """Return a list of events: dicts with keys
    kind ('left'|'right'), group, side, token, cmd_pos (index of backslash),
    delim_pos (index of the delimiter token)."""
    events = []
    for m in re.finditer(r"\\(left|right)\b", s):
        kind = m.group(1)
        after = m.end()
        rd = _read_delim(s, after)
        if rd is None:
            events.append({"kind": kind, "group": None, "side": None,
                           "token": None, "cmd_pos": m.start(),
                           "delim_pos": after})
            continue
        tok, group, side, _end = rd
        delim_pos = _end - len(tok)
        events.append({"kind": kind, "group": group, "side": side,
                       "token": tok, "cmd_pos": m.start(),
                       "delim_pos": delim_pos})
    return events


def check_brackets(s):
    """Return list of mismatch dicts for \\left/\\right pairs.

    Each mismatch has: open (token), close (token), open_pos, close_pos,
    open_group, close_group, fix_match_close, fix_match_open.
    """
    events = find_left_right(s)
    stack = []
    mismatches = []
    for ev in events:
        if ev["kind"] == "left":
            stack.append(ev)
        else:  # right
            if not stack:
                continue
            op = stack.pop()
            og, cg = op["group"], ev["group"]
            if og is None or cg is None:
                continue
            if og == "dot" or cg == "dot":
                continue  # invisible delimiter matches anything
            if og != cg:
                fix_close = _replace_token(
                    s, ev["delim_pos"], ev["token"], _GROUP_CLOSE[og])
                fix_open = _replace_token(
                    s, op["delim_pos"], op["token"], _GROUP_OPEN[cg])
                mismatches.append({
                    "open": op["token"], "close": ev["token"],
                    "open_pos": op["delim_pos"], "close_pos": ev["delim_pos"],
                    "open_group": og, "close_group": cg,
                    "fix_match_close": fix_close,
                    "fix_match_open": fix_open,
                })
    return mismatches


def _replace_token(s, pos, old, new):
    return s[:pos] + new + s[pos + len(old):]


# ---------------------------------------------------------------------------
# Typo / unknown-command detection
# ---------------------------------------------------------------------------

KNOWN_COMMANDS = set("""
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi
psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
sin cos tan cot sec csc sinh cosh tanh coth arcsin arccos arctan log ln lg exp
lim limsup liminf max min sup inf arg deg det dim gcd hom ker Pr
frac dfrac tfrac cfrac binom dbinom tbinom sqrt sum prod int iint iiint oint
bigcup bigcap bigvee bigwedge bigoplus bigotimes bigsqcup coprod
partial nabla infty forall exists nexists emptyset varnothing in notin ni
subset supset subseteq supseteq subsetneq supsetneq cup cap setminus
smallsetminus cdot cdots ldots dots vdots ddots times div pm mp ast star circ
bullet oplus ominus otimes oslash odot leq geq neq equiv approx cong sim simeq
propto perp parallel mid nmid langle rangle lceil rceil lfloor rfloor lvert
rvert lVert rVert vert Vert lbrace rbrace lbrack rbrack backslash
leftarrow rightarrow Leftarrow Rightarrow leftrightarrow Leftrightarrow
longleftarrow longrightarrow Longleftarrow Longrightarrow mapsto to gets
uparrow downarrow updownarrow implies iff hookrightarrow hookleftarrow
hat widehat tilde widetilde bar overline underline vec dot ddot acute grave
check breve mathring overrightarrow overleftarrow overbrace underbrace
mathrm mathbf mathit mathcal mathbb mathfrak mathsf mathtt boldsymbol bm
text textbf textit textrm textsf texttt operatorname
left right big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr
langle rangle quad qquad hspace vspace phantom quad
begin end array matrix pmatrix bmatrix vmatrix Vmatrix cases aligned align
gather split equation displaystyle textstyle scriptstyle scriptscriptstyle
prime ell hbar imath jmath Re Im wp aleph beth
leftrightharpoons rightleftharpoons leqslant geqslant ll gg
lor land lnot neg top bot angle triangle square diamond
frac left right over choose atop overset underset stackrel
mathop limits nolimits displaystyle
colon semicolon ne le ge
notag nonumber label ref eqref
dfrac tfrac
norm abs
""".split())

_CMD_RE = re.compile(r"\\([A-Za-z]+)")


def detect_unknown_commands(s):
    """Flag \\command tokens not in the known list with a closest suggestion.

    Heuristic only: custom macros defined in a paper are legitimate, so always
    confirm a flagged command against the rendered PDF before correcting.
    """
    out = []
    seen = set()
    for m in _CMD_RE.finditer(s):
        name = m.group(1)
        if name in KNOWN_COMMANDS:
            continue
        if name in seen:
            continue
        seen.add(name)
        sugg = difflib.get_close_matches(name, KNOWN_COMMANDS, n=1, cutoff=0.6)
        out.append({"command": "\\" + name, "pos": m.start(),
                    "suggestion": ("\\" + sugg[0]) if sugg else None})
    return out


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------

def dedup_preserve_order(items):
    seen = set()
    out = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def build_markdown(originals, corrected):
    """originals and corrected are lists of cleaned raw formula strings.
    Returns the markdown file content."""
    lines = ["$$" + f + "$$" for f in originals]
    text = "\n".join(lines)
    if corrected:
        text += "\n\n" + "\n".join("$$" + f + "$$" for f in corrected)
    return text + "\n"
