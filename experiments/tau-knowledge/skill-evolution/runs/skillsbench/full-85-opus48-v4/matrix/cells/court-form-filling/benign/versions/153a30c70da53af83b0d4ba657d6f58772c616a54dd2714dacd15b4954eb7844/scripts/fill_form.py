#!/usr/bin/env python3
"""Fill AcroForm fields and save a new PDF, preserving structure.

stdin:  {"input_pdf":"...","output_pdf":"...","fields":{name:value,...}}
        For checkbox/radio fields pass the exact on-state string reported by
        inspect_fields (e.g. "/Yes"). For text fields pass a plain string.
stdout: {"ok":bool,"written":[...],"missing":[...],"output_pdf":"..."}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pdf_common import (  # noqa: E402
    PdfReader, PdfWriter, NameObject, set_need_appearances, read_fields,
)


def main():
    data = json.load(sys.stdin)
    input_pdf = data['input_pdf']
    output_pdf = data['output_pdf']
    fields = data.get('fields', {}) or {}

    existing = {f['name'] for f in read_fields(input_pdf)}
    missing = [n for n in fields if n not in existing]
    present = {n: v for n, v in fields.items() if n in existing}

    reader = PdfReader(input_pdf)
    writer = PdfWriter()
    writer.append(reader)

    written = set()
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(
                page, present, auto_regenerate=False)
        except TypeError:
            # older signature without auto_regenerate
            writer.update_page_form_field_values(page, present)
        except Exception:
            # keep going; verification will catch failures
            pass
    # Record intent; actual confirmation is done by verify_fields.py.
    written = sorted(present.keys())

    set_need_appearances(writer)

    with open(output_pdf, 'wb') as fh:
        writer.write(fh)

    json.dump({
        'ok': len(missing) == 0,
        'written': written,
        'missing': missing,
        'output_pdf': output_pdf,
    }, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
