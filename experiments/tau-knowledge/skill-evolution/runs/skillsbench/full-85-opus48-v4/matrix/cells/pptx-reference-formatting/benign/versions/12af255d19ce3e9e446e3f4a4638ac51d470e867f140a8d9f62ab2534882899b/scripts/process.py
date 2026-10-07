#!/usr/bin/env python3
"""Detect dangling paper titles, reformat/relocate them, append a Reference
slide with auto-numbered unique titles, save and validate.

stdin JSON keys (all optional):
  input_pptx   (default /root/Awesome-Agent-Papers.pptx)
  output_pptx  (default /root/Awesome-Agent-Papers_processed.pptx)
  width_factor (default 0.52)
  detect_mode  ('overflow' default | 'textboxes')
  min_title_chars (default 8)
  bottom_margin_in (default 0.2)
  number_format (default 'arabicPeriod')
  font_name (default 'Arial'), font_pt (default 16), font_hex (default '989596')

stdout JSON: summary + validation. On error: {"error":...} exit 1.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

EMU_PER_IN = helpers.EMU_PER_IN


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    inp = cfg.get('input_pptx') or '/root/Awesome-Agent-Papers.pptx'
    out = cfg.get('output_pptx') or '/root/Awesome-Agent-Papers_processed.pptx'
    width_factor = float(cfg.get('width_factor', 0.52))
    detect_mode = cfg.get('detect_mode', 'dangling')
    min_title_chars = int(cfg.get('min_title_chars', 8))
    bottom_margin = int(float(cfg.get('bottom_margin_in', 0.2)) * EMU_PER_IN)
    number_format = cfg.get('number_format', 'arabicPeriod')
    font_name = cfg.get('font_name', 'Arial')
    font_pt = float(cfg.get('font_pt', 16))
    font_hex = cfg.get('font_hex', '989596')

    if not os.path.exists(inp):
        print(json.dumps({'error': 'input not found: %s' % inp}))
        return 1
    try:
        from pptx import Presentation
        prs = Presentation(inp)
    except Exception as e:
        print(json.dumps({'error': 'cannot open pptx: %s' % e}))
        return 1

    sw, sh = int(prs.slide_width), int(prs.slide_height)

    titles = helpers.detect_titles(prs, width_factor=width_factor,
                                   detect_mode=detect_mode,
                                   min_title_chars=min_title_chars)

    detected_texts = []
    formatted = 0
    for si, shape in titles:
        text = helpers.norm_text(shape.text_frame.text)
        detected_texts.append(text)
        helpers.format_title_runs(shape, font_name, font_pt, font_hex)
        helpers.fit_to_one_line(shape, font_pt, width_factor, sw)
        helpers.place_bottom_center(shape, sw, sh, bottom_margin)
        formatted += 1

    # unique titles, first-occurrence order
    seen = set()
    unique = []
    for t in detected_texts:
        key = t.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(t)

    # append Reference slide
    ref_added = False
    try:
        layout, has_body = helpers.pick_title_body_layout(prs)
        slide = prs.slides.add_slide(layout)
        # title
        title_ph = None
        try:
            title_ph = slide.shapes.title
        except Exception:
            title_ph = None
        if title_ph is not None:
            title_ph.text = 'Reference'
        else:
            from pptx.util import Emu
            tb = slide.shapes.add_textbox(Emu(int(0.5 * EMU_PER_IN)),
                                          Emu(int(0.3 * EMU_PER_IN)),
                                          Emu(sw - EMU_PER_IN),
                                          Emu(int(0.8 * EMU_PER_IN)))
            tb.text_frame.text = 'Reference'
        # body
        body = helpers.find_body_placeholder(slide)
        if body is None:
            from pptx.util import Emu
            body = slide.shapes.add_textbox(
                Emu(int(0.5 * EMU_PER_IN)), Emu(int(1.3 * EMU_PER_IN)),
                Emu(sw - EMU_PER_IN), Emu(sh - int(1.8 * EMU_PER_IN)))
        tf = body.text_frame
        tf.clear()
        if not unique:
            tf.paragraphs[0].text = ''
        for i, t in enumerate(unique):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = t
            p.level = 0
            helpers.set_auto_number(p, number_format)
        ref_added = True
    except Exception as e:
        print(json.dumps({'error': 'failed to add reference slide: %s' % e}))
        return 1

    try:
        prs.save(out)
    except Exception as e:
        print(json.dumps({'error': 'failed to save: %s' % e}))
        return 1

    validation = validate(out, width_factor, number_format,
                          font_name, font_pt, font_hex)

    summary = {
        'input_pptx': inp,
        'output_pptx': out,
        'detect_mode': detect_mode,
        'detected_titles': len(detected_texts),
        'unique_titles': len(unique),
        'formatted_shapes': formatted,
        'reference_slide_added': ref_added,
        'titles': unique,
        'validation': validation,
    }
    print(json.dumps(summary))
    return 0


def validate(path, width_factor, number_format, font_name, font_pt, font_hex):
    res = {'ok': True, 'issues': []}
    try:
        from pptx import Presentation
        prs = Presentation(path)
    except Exception as e:
        return {'ok': False, 'issues': ['cannot reopen: %s' % e]}
    sw = int(prs.slide_width)
    slides = list(prs.slides)
    if not slides:
        res['ok'] = False
        res['issues'].append('no slides')
        return res
    # last slide should be Reference
    last = slides[-1]
    title_text = ''
    try:
        if last.shapes.title is not None:
            title_text = helpers.norm_text(last.shapes.title.text)
    except Exception:
        pass
    if title_text.lower() != 'reference':
        # also scan shapes
        texts = [helpers.norm_text(s.text_frame.text)
                 for s in helpers.iter_text_shapes(last)]
        if not any(t.lower() == 'reference' for t in texts):
            res['ok'] = False
            res['issues'].append('last slide title is not "Reference"')
    # count auto-numbered bullets across all text frames on the last slide
    from pptx.oxml.ns import qn
    numbered = 0
    bullet_texts = []
    for shape in helpers.iter_text_shapes(last):
        th = ''
        try:
            if shape is last.shapes.title:
                continue
        except Exception:
            pass
        for par in shape.text_frame.paragraphs:
            pPr = par._p.find(qn('a:pPr'))
            if pPr is not None and pPr.find(qn('a:buAutoNum')) is not None:
                numbered += 1
                bullet_texts.append(helpers.norm_text(par.text))
    res['reference_numbered_bullets'] = numbered
    # duplicate check on the reference list
    low = [t.lower() for t in bullet_texts if t]
    res['reference_has_duplicates'] = len(low) != len(set(low))
    if res['reference_has_duplicates']:
        res['ok'] = False
        res['issues'].append('reference list contains duplicates')
    # remaining single-line check: only loose (non-placeholder) title boxes
    remaining_overflow = 0
    for s in list(prs.slides)[:-1]:
        for shape in helpers.iter_text_shapes(s):
            try:
                if shape.is_placeholder:
                    continue
            except Exception:
                pass
            info = helpers.shape_info(shape, 0, width_factor)
            if info['overflow']:
                remaining_overflow += 1
    res['remaining_overflow_shapes'] = remaining_overflow
    return res


if __name__ == '__main__':
    sys.exit(main())
