"""Shared helpers for the pptx dangling-title formatter.

All geometry is in EMU (914400 EMU per inch, 12700 EMU per point).
Nothing here is task-specific: paths, titles and sizes are passed in.
"""
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn

EMU_PER_PT = 12700
EMU_PER_IN = 914400
DEFAULT_FALLBACK_PT = 18.0
# default internal text inset on each side (python-pptx default ~0.1in L/R)
SIDE_MARGIN_EMU = int(0.1 * EMU_PER_IN)


def rgb_from_hex(hex_str):
    h = hex_str.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def effective_font_pt(run):
    """Best-effort current font size in points for a run."""
    try:
        if run.font.size is not None:
            return run.font.size.pt
    except Exception:
        pass
    return None


def shape_effective_pt(shape):
    """Representative font size (pt) for a text shape; fallback constant."""
    sizes = []
    if not shape.has_text_frame:
        return DEFAULT_FALLBACK_PT
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            s = effective_font_pt(run)
            if s:
                sizes.append(s)
    if sizes:
        return max(sizes)
    return DEFAULT_FALLBACK_PT


def longest_line(text):
    if not text:
        return ''
    lines = text.replace('\x0b', '\n').split('\n')
    return max(lines, key=len) if lines else ''


def est_text_width_emu(text, font_pt, factor):
    """Estimated single-line pixel-free width (EMU) of text at font_pt.
    factor = average glyph advance as a fraction of the em.
    """
    line = longest_line(text)
    width_pt = len(line) * float(font_pt) * float(factor)
    return int(width_pt * EMU_PER_PT)


def iter_text_shapes(slide):
    for shape in slide.shapes:
        try:
            if shape.has_text_frame and shape.text_frame.text.strip():
                yield shape
        except Exception:
            continue


def norm_text(text):
    return ' '.join((text or '').split())


def shape_info(shape, slide_idx, width_factor):
    ph_type = None
    is_ph = False
    try:
        if shape.is_placeholder:
            is_ph = True
            ph_type = str(shape.placeholder_format.type)
    except Exception:
        pass
    text = shape.text_frame.text if shape.has_text_frame else ''
    font_pt = shape_effective_pt(shape)
    est = est_text_width_emu(text, font_pt, width_factor)
    inner_w = (shape.width or 0) - 2 * SIDE_MARGIN_EMU
    overflow = est > max(inner_w, 1)
    return {
        'slide': slide_idx,
        'shape_id': getattr(shape, 'shape_id', None),
        'name': getattr(shape, 'name', None),
        'is_placeholder': is_ph,
        'ph_type': ph_type,
        'left': int(shape.left) if shape.left is not None else None,
        'top': int(shape.top) if shape.top is not None else None,
        'width': int(shape.width) if shape.width is not None else None,
        'height': int(shape.height) if shape.height is not None else None,
        'text': norm_text(text),
        'eff_font_pt': font_pt,
        'est_text_width_emu': est,
        'overflow': bool(overflow),
    }


def is_title_placeholder(shape):
    try:
        if shape.is_placeholder:
            t = str(shape.placeholder_format.type)
            idx = shape.placeholder_format.idx
            return ('TITLE' in t.upper()) or idx == 0
    except Exception:
        pass
    return False


def _content_text(shape):
    try:
        if shape.has_text_frame:
            return norm_text(shape.text_frame.text)
    except Exception:
        pass
    return ''


def is_decorative_ph(shape):
    """True for date/footer/slide-number placeholders that never hold titles."""
    try:
        if shape.is_placeholder:
            t = str(shape.placeholder_format.type).upper()
            return any(k in t for k in ('DATE', 'FOOTER', 'SLIDE_NUMBER'))
    except Exception:
        pass
    return False


def detect_titles(prs, width_factor=0.52, detect_mode='dangling',
                  min_title_chars=8):
    """Return list of (slide_index, shape) considered dangling paper titles.

    Default mode 'dangling': a *loose* text box, i.e. a non-placeholder
    text-bearing shape carrying meaningful text. Paper-title boxes added on
    top of a slide are not placeholders, which distinguishes them from the
    slide title placeholder and the abstract/body content placeholder.
    Other modes are kept for decks where that heuristic does not hold.
    """
    found = []
    for si, slide in enumerate(prs.slides):
        for shape in iter_text_shapes(slide):
            text = norm_text(shape.text_frame.text)
            if len(text) < min_title_chars:
                continue
            if detect_mode == 'dangling':
                try:
                    if shape.is_placeholder:
                        continue
                except Exception:
                    pass
                found.append((si, shape))
            elif detect_mode == 'overflow':
                font_pt = shape_effective_pt(shape)
                est = est_text_width_emu(text, font_pt, width_factor)
                inner_w = (shape.width or 0) - 2 * SIDE_MARGIN_EMU
                if est <= max(inner_w, 1):
                    continue
                found.append((si, shape))
            else:  # 'textboxes' : every non-title, non-decorative text shape
                if is_title_placeholder(shape) or is_decorative_ph(shape):
                    continue
                found.append((si, shape))
    return found


def format_title_runs(shape, font_name, font_pt, hex_color):
    color = rgb_from_hex(hex_color)
    tf = shape.text_frame
    for para in tf.paragraphs:
        runs = list(para.runs)
        if not runs and para.text:
            # ensure a run exists so formatting is stored
            run = para.add_run()
            run.text = para.text
            runs = [run]
        for run in runs:
            f = run.font
            f.name = font_name
            f.size = Pt(font_pt)
            f.bold = False
            try:
                f.color.rgb = color
            except Exception:
                pass


def fit_to_one_line(shape, font_pt, width_factor, slide_width):
    """Disable wrap and widen box to a single line. Returns new width (EMU)."""
    tf = shape.text_frame
    try:
        tf.word_wrap = False
    except Exception:
        pass
    try:
        from pptx.enum.text import MSO_AUTO_SIZE
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    est = est_text_width_emu(tf.text, font_pt, width_factor)
    new_w = est + 2 * SIDE_MARGIN_EMU + int(0.05 * EMU_PER_IN)
    new_w = min(new_w, int(slide_width))
    new_w = max(new_w, int(0.5 * EMU_PER_IN))
    shape.width = Emu(int(new_w))
    return int(new_w)


def place_bottom_center(shape, slide_width, slide_height, bottom_margin_emu):
    w = int(shape.width or 0)
    h = int(shape.height or 0)
    left = int((slide_width - w) / 2)
    left = max(0, left)
    top = int(slide_height - h - bottom_margin_emu)
    top = max(0, top)
    shape.left = Emu(left)
    shape.top = Emu(top)


def set_auto_number(paragraph, fmt='arabicPeriod'):
    pPr = paragraph._p.get_or_add_pPr()
    for tag in ('a:buNone', 'a:buChar', 'a:buAutoNum'):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    bu = pPr.makeelement(qn('a:buAutoNum'), {'type': fmt})
    anchor = None
    for tag in ('a:tabLst', 'a:defRPr', 'a:extLst'):
        f = pPr.find(qn(tag))
        if f is not None:
            anchor = f
            break
    if anchor is not None:
        anchor.addprevious(bu)
    else:
        pPr.append(bu)


def _is_content_body_ph(ph):
    """A real list/body/content placeholder (not subtitle/date/footer/number)."""
    try:
        pidx = ph.placeholder_format.idx
        t = str(ph.placeholder_format.type).upper()
    except Exception:
        return False
    if pidx == 0 or 'TITLE' in t:
        return False
    if any(k in t for k in ('DATE', 'FOOTER', 'SLIDE_NUMBER', 'PICTURE')):
        return False
    if not getattr(ph, 'has_text_frame', False):
        return False
    return True


def pick_title_body_layout(prs):
    """Return (layout, has_body) preferring a layout with a title and a real
    content/body placeholder (e.g. "Title and Content"). Subtitle-only
    layouts (title slide) are used only as a last resort."""
    preferred = None   # title + BODY/OBJECT/CONTENT
    fallback = None    # title + subtitle-like text placeholder
    title_only = None
    for layout in prs.slide_layouts:
        has_title = False
        body_kind = None  # 'content' or 'other'
        for ph in layout.placeholders:
            try:
                t = str(ph.placeholder_format.type).upper()
                pidx = ph.placeholder_format.idx
            except Exception:
                continue
            if 'TITLE' in t or pidx == 0:
                has_title = True
            elif _is_content_body_ph(ph):
                if any(k in t for k in ('BODY', 'OBJECT', 'CONTENT')):
                    body_kind = 'content'
                elif body_kind is None:
                    body_kind = 'other'
        if has_title and body_kind == 'content' and preferred is None:
            preferred = layout
        elif has_title and body_kind == 'other' and fallback is None:
            fallback = layout
        elif has_title and title_only is None:
            title_only = layout
    if preferred is not None:
        return preferred, True
    if fallback is not None:
        return fallback, True
    if title_only is not None:
        return title_only, False
    layouts = list(prs.slide_layouts)
    if len(layouts) > 1:
        return layouts[1], False
    return layouts[0], False


def find_body_placeholder(slide):
    """Prefer a BODY/OBJECT/CONTENT placeholder; fall back to any non-title,
    non-decorative text placeholder."""
    content = None
    other = None
    for ph in slide.placeholders:
        if not _is_content_body_ph(ph):
            continue
        try:
            t = str(ph.placeholder_format.type).upper()
        except Exception:
            t = ''
        if any(k in t for k in ('BODY', 'OBJECT', 'CONTENT')):
            if content is None:
                content = ph
        elif other is None:
            other = ph
    return content or other
