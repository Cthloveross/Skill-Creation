#!/usr/bin/env python3
"""Inspect interactive form fields in a PDF.

stdin:  {"pdf_path": "..."}
stdout: {"count": N, "fields": [{name,type,value,states,tooltip}, ...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pdf_common import read_fields  # noqa: E402


def main():
    data = json.load(sys.stdin)
    pdf_path = data['pdf_path']
    fields = read_fields(pdf_path)
    json.dump({'count': len(fields), 'fields': fields}, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
