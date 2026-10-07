"""Extract text from heterogeneous document formats.

stdin JSON:  {"path": "/abs/path/to/file", "max_chars": 60000}
stdout JSON: {"path": ..., "text": ..., "method": ..., "ok": bool}

Strategies, in order, by extension:
  .pdf  : pdfplumber -> pypdf/PyPDF2 -> OCR (pdf2image + pytesseract) [last resort]
  .docx : python-docx -> raw ZIP XML (<w:t> incl. headers/footers)
  .pptx : python-pptx -> raw ZIP XML (<a:t> across slides + notes)
  .txt/.md/.csv/other text : direct read
Unknown/binary: returns empty text, ok=False (caller sends to fallback).
"""
import sys, os, json, zipfile, re


def _strip_xml_text(xml_bytes, tag_localnames):
    try:
        s = xml_bytes.decode("utf-8", "ignore")
    except Exception:
        return ""
    parts = []
    for ln in tag_localnames:
        # match <...:ln ...>text</...:ln> or <ln>text</ln>
        for m in re.finditer(r"<(?:[a-zA-Z0-9]+:)?%s\b[^>]*>(.*?)</(?:[a-zA-Z0-9]+:)?%s>" % (ln, ln), s, re.S):
            txt = re.sub(r"<[^>]+>", "", m.group(1))
            if txt.strip():
                parts.append(txt)
    return " ".join(parts)


def _zip_xml_text(path, member_prefixes, tag_localnames):
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if any(name.startswith(p) and name.endswith(".xml") for p in member_prefixes):
                    try:
                        out.append(_strip_xml_text(z.read(name), tag_localnames))
                    except Exception:
                        pass
    except Exception:
        return ""
    return " ".join(p for p in out if p)


def extract_pdf(path, max_chars):
    text = ""
    try:
        import pdfplumber
        chunks = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                chunks.append(t)
                if sum(len(c) for c in chunks) > max_chars:
                    break
        text = "\n".join(chunks)
        if text.strip():
            return text, "pdfplumber"
    except Exception:
        pass
    for modname, cls in (("pypdf", "PdfReader"), ("PyPDF2", "PdfReader")):
        try:
            mod = __import__(modname)
            reader = getattr(mod, cls)(path)
            chunks = []
            for page in reader.pages:
                try:
                    chunks.append(page.extract_text() or "")
                except Exception:
                    pass
                if sum(len(c) for c in chunks) > max_chars:
                    break
            text = "\n".join(chunks)
            if text.strip():
                return text, modname
        except Exception:
            continue
    # OCR last resort
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(path, dpi=150, first_page=1, last_page=5)
        chunks = []
        for img in images:
            chunks.append(pytesseract.image_to_string(img))
            if sum(len(c) for c in chunks) > max_chars:
                break
        text = "\n".join(chunks)
        if text.strip():
            return text, "ocr"
    except Exception:
        pass
    return text, "pdf-empty"


def extract_docx(path, max_chars):
    try:
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for tbl in d.tables:
            for row in tbl.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        for sec in d.sections:
            try:
                parts += [p.text for p in sec.header.paragraphs]
                parts += [p.text for p in sec.footer.paragraphs]
            except Exception:
                pass
        text = "\n".join(p for p in parts if p)
        if text.strip():
            return text, "python-docx"
    except Exception:
        pass
    text = _zip_xml_text(path, ("word/",), ("t",))
    return (text, "docx-zip") if text.strip() else (text, "docx-empty")


def extract_pptx(path, max_chars):
    try:
        from pptx import Presentation
        prs = Presentation(path)
        parts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    parts.append(shape.text_frame.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        for c in row.cells:
                            parts.append(c.text)
            try:
                if slide.has_notes_slide:
                    parts.append(slide.notes_slide.notes_text_frame.text)
            except Exception:
                pass
            if sum(len(p) for p in parts) > max_chars:
                break
        text = "\n".join(p for p in parts if p)
        if text.strip():
            return text, "python-pptx"
    except Exception:
        pass
    text = _zip_xml_text(path, ("ppt/slides/", "ppt/notesSlides/"), ("t",))
    return (text, "pptx-zip") if text.strip() else (text, "pptx-empty")


def extract_text_file(path, max_chars):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars), "text"
    except Exception:
        return "", "text-empty"


def extract(path, max_chars=60000):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text, method = extract_pdf(path, max_chars)
    elif ext == ".docx":
        text, method = extract_docx(path, max_chars)
    elif ext == ".pptx":
        text, method = extract_pptx(path, max_chars)
    elif ext in (".txt", ".md", ".csv", ".json", ".tex", ".rtf", ".html", ".htm"):
        text, method = extract_text_file(path, max_chars)
    else:
        # try as a zip (some OOXML variants) then as text
        text = _zip_xml_text(path, ("word/", "ppt/slides/"), ("t",))
        if text.strip():
            method = "zip-xml"
        else:
            text, method = extract_text_file(path, max_chars)
    text = (text or "")[:max_chars]
    return {"path": path, "text": text, "method": method, "ok": bool(text.strip())}


def main():
    req = json.load(sys.stdin)
    res = extract(req["path"], int(req.get("max_chars", 60000)))
    json.dump(res, sys.stdout)


if __name__ == "__main__":
    main()
