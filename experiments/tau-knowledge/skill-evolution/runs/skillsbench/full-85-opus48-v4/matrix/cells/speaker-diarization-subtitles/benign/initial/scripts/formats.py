"""Formatting helpers for RTTM and ASS outputs and time conversions.

Pure functions, no heavy imports, so they can be unit-reasoned and reused.
"""
from __future__ import annotations


def ass_time(t: float) -> str:
    """Seconds -> ASS timestamp 'H:MM:SS.cc' (centiseconds, 2 decimals)."""
    if t < 0:
        t = 0.0
    total_cs = int(round(t * 100))
    h = total_cs // 360000
    total_cs %= 360000
    m = total_cs // 6000
    total_cs %= 6000
    s = total_cs // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def rttm_line(file_id: str, start: float, dur: float, spk: str,
              channel: int = 1) -> str:
    """One RTTM SPEAKER line (ten fields)."""
    return (f"SPEAKER {file_id} {channel} {start:.6f} {dur:.6f} "
            f"<NA> <NA> {spk} <NA> <NA>")


def write_rttm(path: str, segments, file_id: str = "input") -> None:
    """segments: iterable of (start, end, speaker_label_str)."""
    lines = []
    for start, end, spk in segments:
        dur = end - start
        if dur <= 0:
            continue
        lines.append(rttm_line(file_id, start, dur, spk))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        if lines:
            fh.write("\n")


ASS_HEADER = (
    "[Script Info]\n"
    "Title: Diarized Subtitles\n"
    "ScriptType: v4.00+\n"
    "WrapStyle: 0\n"
    "ScaledBorderAndShadow: yes\n"
    "PlayResX: 1280\n"
    "PlayResY: 720\n"
    "\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
    "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
    "MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,"
    "0,0,100,100,0,0,1,2,0,2,10,10,20,1\n"
    "\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
    "Effect, Text\n"
)


def dialogue_line(start: float, end: float, label: str, text: str) -> str:
    text = " ".join(str(text).split())  # collapse whitespace / newlines
    safe = text.replace("\n", " ")
    return (f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,"
            f"{label}: {safe}")


def write_ass(path: str, cues) -> None:
    """cues: iterable of (start, end, label_str, text_str)."""
    lines = [ASS_HEADER]
    for start, end, label, text in cues:
        if end <= start:
            end = start + 0.5
        if not str(text).strip():
            continue  # avoid empty-text cues
        lines.append(dialogue_line(start, end, label, text) + "\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
