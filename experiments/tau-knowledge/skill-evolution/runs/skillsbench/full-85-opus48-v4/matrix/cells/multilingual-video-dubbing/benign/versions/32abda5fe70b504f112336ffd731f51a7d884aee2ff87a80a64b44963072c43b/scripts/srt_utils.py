"""SRT parsing helpers. No benchmark-specific values."""
import re

_TC = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{1,3})")


def tc_to_sec(tc):
    m = _TC.search(tc)
    if not m:
        raise ValueError("bad timecode: %r" % tc)
    h, mn, s, ms = m.groups()
    ms = (ms + "000")[:3]
    return int(h) * 3600 + int(mn) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    """Return list of {'index', 'start', 'end', 'text'} in file order.
    'start'/'end' are seconds (None if a block has no timing line)."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()
    blocks = re.split(r"\n\s*\n", raw.strip())
    out = []
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        idx = None
        start = end = None
        text_lines = []
        i = 0
        if re.fullmatch(r"\d+", lines[0].strip()):
            idx = int(lines[0].strip())
            i = 1
        if i < len(lines) and "-->" in lines[i]:
            left, right = lines[i].split("-->")
            start = tc_to_sec(left)
            end = tc_to_sec(right)
            i += 1
        text_lines = lines[i:]
        text = " ".join(t.strip() for t in text_lines).strip()
        out.append({"index": idx, "start": start, "end": end, "text": text})
    return out


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read().strip()
