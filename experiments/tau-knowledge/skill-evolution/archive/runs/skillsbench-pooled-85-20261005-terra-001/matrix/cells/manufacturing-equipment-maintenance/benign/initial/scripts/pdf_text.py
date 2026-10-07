"""PDF text extraction with local-tool and installed-library fallbacks."""
from __future__ import annotations
import io
import subprocess


def extract_pdf_text(path: str) -> str:
    # pdftotext preserves many table layouts and is preferred when available.
    try:
        result = subprocess.run(["pdftotext", "-layout", path, "-"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=120, check=True)
        if result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    errors = []
    for module_name in ("pypdf", "PyPDF2", "pdfplumber"):
        try:
            if module_name == "pdfplumber":
                import pdfplumber  # type: ignore
                with pdfplumber.open(path) as pdf:
                    text = "\n\n".join((p.extract_text() or "") for p in pdf.pages)
            else:
                module = __import__(module_name)
                reader = module.PdfReader(path)
                text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
            if text.strip():
                return text
        except Exception as exc:  # continue to the next locally installed reader
            errors.append(f"{module_name}: {exc}")
    raise RuntimeError("Could not extract searchable handbook text. Install/use an approved "
                       "local PDF/OCR reader or provide a text-accessible handbook. " + "; ".join(errors))
