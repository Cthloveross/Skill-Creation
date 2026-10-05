#!/usr/bin/env python3
"""Format discovered paper titles and append a deduplicated reference slide.

Input JSON schema:
{
  "input_path": "required existing .pptx path",
  "output_path": "required .pptx output path",
  "selection_mode": "primary_per_slide" | "all_standalone" (optional)
}
Output is a single JSON object as documented in SKILL.md.
"""
import json
import re
import sys
import zipfile
from pathlib import Path


def fail(message):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    return 1

try:
    from pptx import Presentation
    from pptx.enum.shapes import PP_PLACEHOLDER
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from pptx.oxml.xmlchemy import OxmlElement
except Exception as exc:  # Import error is returned as structured output.
    print(json.dumps({"ok": False, "error": "python-pptx is required: %s" % exc}))
    sys.exit(1)

FONT_NAME = "Arial"
FONT_SIZE = Pt(16)
FONT_RGB = RGBColor(0x98, 0x95, 0x96)
BOTTOM_MARGIN = Inches(0.18)
SIDE_MARGIN = Inches(0.25)


def iter_shapes(shapes):
    """Yield text-capable shapes, including those inside group shapes."""
    for shape in shapes:
        if hasattr(shape, "shapes"):
            yield from iter_shapes(shape.shapes)
        if getattr(shape, "has_text_frame", False):
            yield shape


def visible_text(shape):
    return "\n".join(p.text for p in shape.text_frame.paragraphs).strip()


def one_line(text):
    return re.sub(r"\s+", " ", text).strip()


def is_title_placeholder(shape):
    if not getattr(shape, "is_placeholder", False):
        return False
    try:
        kind = shape.placeholder_format.type
        return kind in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)
    except Exception:
        return False


def title_score(shape, slide_width, slide_height):
    """Return (score, reason), or (None, reason) when clearly not a title."""
    text = visible_text(shape)
    flat = one_line(text)
    if not flat:
        return None, "empty"
    paragraphs = [p for p in shape.text_frame.paragraphs if p.text.strip()]
    if len(paragraphs) != 1:
        return None, "multiple_paragraphs"
    if len(flat) < 5 or len(flat) > 500:
        return None, "implausible_length"
    low = flat.casefold()
    if re.search(r"(?:https?://|www\.|doi\.org|@\w+)", low):
        return None, "url_or_handle"
    if re.match(r"^(?:\[?\d+\]?|[-•*])\s+", flat):
        return None, "list_or_citation_marker"
    # Body prose generally contains sentence punctuation and many words. Do not
    # reject paper titles merely because they contain a colon or a question mark.
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’_-]*", flat)
    if len(words) > 30 and re.search(r"[.!]", flat):
        return None, "body_prose"

    score = 0
    reasons = []
    if is_title_placeholder(shape):
        score += 100
        reasons.append("title_placeholder")
    else:
        score += 20
        reasons.append("standalone_single_paragraph")
    if 2 <= len(words) <= 24:
        score += 12
    if not re.search(r"[.!]", flat):
        score += 5
    # Centered, wide, and edge-positioned boxes are common title treatments.
    center_delta = abs((shape.left + shape.width / 2) - slide_width / 2)
    if center_delta <= slide_width * 0.15:
        score += 8
        reasons.append("centered")
    if shape.width >= slide_width * 0.30:
        score += 4
    edge = min(shape.top, max(0, slide_height - (shape.top + shape.height)))
    if edge <= slide_height * 0.30:
        score += 3
    return score, ",".join(reasons)


def discover_titles(prs, selection_mode):
    selected = []
    warnings = []
    for slide_no, slide in enumerate(prs.slides, start=1):
        candidates = []
        for shape in iter_shapes(slide.shapes):
            score, reason = title_score(shape, prs.slide_width, prs.slide_height)
            if score is not None:
                candidates.append((score, shape, reason))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        if selection_mode == "all_standalone":
            # 32 keeps generic short labels out while retaining title placeholders.
            chosen = [c for c in candidates if c[0] >= 32]
        else:
            chosen = [candidates[0]]
        for score, shape, reason in chosen:
            text = one_line(visible_text(shape))
            confidence = "high" if score >= 100 else ("medium" if score >= 40 else "low")
            selected.append({
                "slide": slide_no, "shape": getattr(shape, "name", "unnamed"),
                "text": text, "confidence": confidence, "score": score,
                "reason": reason, "_shape": shape,
            })
            if confidence == "low":
                warnings.append("Low-confidence title selection on slide %d: %s" % (slide_no, text))
    return selected, warnings


def format_title(shape, slide_width, slide_height):
    """Apply requested visual properties without recreating the shape."""
    tf = shape.text_frame
    # A title is treated as a logical single line. Existing content selected by
    # this Skill has one paragraph; normalizing preserves the existing first run
    # where possible and avoids adding a line break that defeats no-wrap.
    text = one_line(visible_text(shape))
    if len(tf.paragraphs) != 1 or tf.paragraphs[0].text != text:
        tf.clear()
        tf.paragraphs[0].text = text
    tf.word_wrap = False
    for para in tf.paragraphs:
        para.alignment = PP_ALIGN.CENTER
        if not para.runs:
            para.add_run()
        for run in para.runs:
            run.font.name = FONT_NAME
            run.font.size = FONT_SIZE
            run.font.bold = False
            run.font.color.rgb = FONT_RGB
    usable_width = max(1, slide_width - 2 * SIDE_MARGIN)
    shape.width = usable_width
    shape.left = int((slide_width - usable_width) / 2)
    # Keep height, because it can include desired internal margins. The title is
    # positioned from actual slide geometry rather than a fixed coordinate.
    shape.top = max(0, slide_height - shape.height - BOTTOM_MARGIN)


def normalized_key(text):
    return re.sub(r"[^\w]+", "", one_line(text).casefold(), flags=re.UNICODE)


def choose_layout(prs):
    # Prefer a layout designed for a title/body slide, but never assume an index.
    for layout in prs.slide_layouts:
        name = (getattr(layout, "name", "") or "").casefold()
        if "title" in name and ("content" in name or "body" in name):
            return layout
    for layout in prs.slide_layouts:
        if "blank" in (getattr(layout, "name", "") or "").casefold():
            return layout
    return prs.slide_layouts[0]


def add_auto_numbering(paragraph):
    ppr = paragraph._p.get_or_add_pPr()
    # New textbox paragraphs have no list markup, but remove any inherited list
    # settings defensively before adding OOXML automatic numbering.
    for child in list(ppr):
        if child.tag.rsplit("}", 1)[-1] in {"buNone", "buChar", "buAutoNum", "buBlip"}:
            ppr.remove(child)
    auto = OxmlElement("a:buAutoNum")
    auto.set("type", "arabicPeriod")
    ppr.append(auto)


def append_reference_slide(prs, titles):
    slide = prs.slides.add_slide(choose_layout(prs))
    # Add explicit shapes so this works even when a custom layout lacks usable
    # title/body placeholders.
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.28), prs.slide_width - Inches(1), Inches(0.55))
    title_box.name = "Reference Title"
    title_p = title_box.text_frame.paragraphs[0]
    title_p.text = "Reference"
    title_p.alignment = PP_ALIGN.CENTER
    for run in title_p.runs:
        run.font.name = FONT_NAME
        run.font.bold = False
    body_top = Inches(1.05)
    body_box = slide.shapes.add_textbox(Inches(0.7), body_top, prs.slide_width - Inches(1.4), prs.slide_height - body_top - Inches(0.35))
    body_box.name = "Reference Body"
    tf = body_box.text_frame
    tf.clear()
    for i, title in enumerate(titles):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = title
        p.level = 0
        add_auto_numbering(p)
    return slide


def validate(path, expected_titles):
    result = {"zip_ok": False, "reopen_ok": False, "reference_slide_ok": False, "formatted_titles_ok": False}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            result["zip_ok"] = archive.testzip() is None
    except Exception:
        return result
    try:
        prs = Presentation(str(path))
        result["reopen_ok"] = True
        if not prs.slides:
            return result
        last = prs.slides[-1]
        texts = [one_line(visible_text(s)) for s in iter_shapes(last.shapes)]
        has_reference = "Reference" in texts
        has_expected = all(t in "\n".join(texts) for t in expected_titles)
        result["reference_slide_ok"] = has_reference and has_expected
        # Every expected edit was made before save. Verify by inspecting shapes
        # on all non-reference slides using their current visible text.
        checked = 0
        good = 0
        expected_set = set(expected_titles)
        for slide in list(prs.slides)[:-1]:
            for shape in iter_shapes(slide.shapes):
                if one_line(visible_text(shape)) in expected_set:
                    checked += 1
                    runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
                    if runs and all(r.font.name == FONT_NAME and r.font.size == FONT_SIZE and r.font.bold is False and r.font.color.rgb == FONT_RGB for r in runs):
                        good += 1
        result["formatted_titles_ok"] = checked > 0 and checked == good
    except Exception:
        pass
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        return fail("stdin must contain a JSON object: %s" % exc)
    if not isinstance(payload, dict):
        return fail("stdin JSON must be an object")
    source = Path(str(payload.get("input_path", "")))
    destination = Path(str(payload.get("output_path", "")))
    mode = payload.get("selection_mode", "primary_per_slide")
    if mode not in ("primary_per_slide", "all_standalone"):
        return fail("selection_mode must be primary_per_slide or all_standalone")
    if not source.is_file() or source.suffix.casefold() != ".pptx":
        return fail("input_path must name an existing .pptx file")
    if not destination.parent.is_dir():
        return fail("output_path parent directory does not exist")
    if source.resolve() == destination.resolve():
        return fail("output_path must differ from input_path to preserve the original")
    try:
        prs = Presentation(str(source))
        selected, warnings = discover_titles(prs, mode)
        if not selected:
            return fail("no likely standalone paper titles were detected")
        for entry in selected:
            format_title(entry["_shape"], prs.slide_width, prs.slide_height)
        unique = []
        seen = set()
        for entry in selected:
            key = normalized_key(entry["text"])
            if key and key not in seen:
                seen.add(key)
                unique.append(entry["text"])
        if not unique:
            return fail("detected titles were empty after normalization")
        append_reference_slide(prs, unique)
        prs.save(str(destination))
        validation = validate(destination, unique)
        if not all(validation.values()):
            return fail("output validation failed: %s" % json.dumps(validation, sort_keys=True))
        report_entries = [{k: v for k, v in entry.items() if k != "_shape"} for entry in selected]
        print(json.dumps({
            "ok": True, "output_path": str(destination),
            "titles_detected": len(selected), "unique_titles": len(unique),
            "selected": report_entries, "warnings": warnings,
            "validation": validation,
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        return fail("processing failed: %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
