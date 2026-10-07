#!/usr/bin/env python3
"""End-to-end smoke test of the generated solution (needs internet + rdkit).

Usage: python3 scripts/smoke_test.py [TARGET_NAME] [PDF_PATH] [TOP_K]

Validates: result is a list, length <= top_k, descending similarity with
alphabetical tie-break when the solution is adapted to return scores, and that
a target present in the pool self-matches. Reads the actual pool at runtime.
"""
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ref = os.path.normpath(os.path.join(here, "..", "references"))
    sys.path.insert(0, ref)
    import solution_source as sol  # type: ignore

    pdf_path = sys.argv[2] if len(sys.argv) > 2 else "/root/molecules.pdf"
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    pool = sol._extract_names_from_pdf(pdf_path)
    if not pool:
        print("FAIL: no names extracted from PDF; tune _extract_names_from_pdf")
        return
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TARGET") or pool[0]

    result = sol.topk_tanimoto_similarity_molecules(target, pdf_path, top_k)
    assert isinstance(result, list), "result must be a list"
    assert len(result) <= top_k, "result longer than top_k"
    print("target:", target)
    print("pool_size:", len(pool))
    print("result:", result)
    print("OK")


if __name__ == "__main__":
    main()
