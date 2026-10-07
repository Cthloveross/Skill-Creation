#!/usr/bin/env python3
"""Clean, deduplicate, and write a display-formula Markdown artifact.
Reads one JSON object from stdin and emits one JSON object on stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from formula_tools import clean_formula, inspect_left_right


def _clean_list(values: object, section: str, warnings: list[dict]) -> list[str]:
    if not isinstance(values, list):
        raise TypeError(f"{section} must be a JSON array")
    retained: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        formula, changes = clean_formula(value)
        if changes:
            warnings.append({"section": section, "index": index, "cleanup": changes})
        if formula in seen:
            warnings.append({"section": section, "index": index, "warning": "duplicate within section omitted"})
            continue
        seen.add(formula)
        retained.append(formula)
    return retained


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TypeError("input must be a JSON object")
        warnings: list[dict] = []
        originals = _clean_list(request.get("originals", []), "originals", warnings)
        corrections = _clean_list(request.get("corrections", []), "corrections", warnings)
        # Output contract prohibits duplicate lines across both logical sections.
        original_set = set(originals)
        retained_corrections: list[str] = []
        for formula in corrections:
            if formula in original_set or formula in retained_corrections:
                warnings.append({"section": "corrections", "formula": formula,
                                 "warning": "duplicate output line omitted"})
            else:
                retained_corrections.append(formula)
        all_formulas = originals + retained_corrections
        path_value = request.get("output_path", "/root/latex_formula_extraction.md")
        if not isinstance(path_value, str) or not path_value:
            raise TypeError("output_path must be a nonempty string")
        output_path = Path(path_value)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(f"$${f}$$\n" for f in all_formulas), encoding="utf-8")
        checks = [{"formula": f, **inspect_left_right(f)} for f in all_formulas]
        print(json.dumps({"output_path": str(output_path), "originals": originals,
                          "corrections": retained_corrections, "count": len(all_formulas),
                          "warnings": warnings, "delimiter_checks": checks}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stdout)
        sys.exit(2)


if __name__ == "__main__":
    main()
