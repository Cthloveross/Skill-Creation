---
name: organize-documents-by-subject
description: Classify a document collection into the required LLM, trapped-ion/quantum-computing, black-hole, DNA, and music-history folders using extracted document content while preserving every source file's bytes and basename. Use for heterogeneous PDF, DOCX, PPTX, text, and similar research-document collections.
---

# Organize documents by subject

Use `scripts/organize_documents.py` to make a content-based, auditable filing plan and, after reviewing it, move every regular source file into exactly one of these folders:

- `LLM`
- `trapped_ion_and_qc`
- `black_hole`
- `DNA`
- `music_history`

The script extracts text directly from DOCX and PPTX OOXML packages, uses `pdftotext` for PDFs when available, and can use `pdftoppm` plus `tesseract` as a fallback for a PDF with empty or malformed text extraction. It recognizes topic-specific terminology in document text and filenames. `music_history` is the required fallback when there is no positive evidence for one of the other subjects.

## Safety and prerequisites

1. Identify the actual source collection and a destination root. The destination root **must not be inside** the source directory. It should be a clean directory: target subject directories must be absent or empty.
2. Do not include helper scripts, downloads, extraction output, or other unrelated files merely because they are nearby. Set `source_dir` to the collection that the user asked to organize.
3. The process moves all regular files recursively from `source_dir`; therefore check the plan before setting `perform_move` to `true`. Symlinks are rejected rather than followed or altered.
4. Filenames are preserved exactly. If two source files would have the same basename in one target folder, the script stops before moving anything because preserving both names is impossible without a user decision.

## Run

First create and inspect a plan. Script input and output are JSON on standard input/output.

```json
{
  "source_dir": "/path/to/source-collection",
  "destination_root": "/path/to/destination-root",
  "perform_move": false,
  "ocr_fallback": true
}
```

The planning response contains a `manifest` entry for every source file with its inferred category, score table, extraction method, and matched evidence. Review entries with `low_confidence: true`, `extractor` errors, or unexpected fallback classifications by reading the original document with an appropriate viewer. If a document's subject is established by review, provide an exact source-relative POSIX path in `overrides`:

```json
{
  "source_dir": "/path/to/source-collection",
  "destination_root": "/path/to/destination-root",
  "perform_move": true,
  "ocr_fallback": true,
  "overrides": {
    "nested/original-paper.pdf": "black_hole"
  }
}
```

Allowed override values are exactly the five folder names above. Overrides do not rename files and are recorded in the manifest as `extractor: "override"`.

## Validation and completion

Before any move, the script validates source readability, unique target paths, and clean target folders. During execution it records SHA-256 digests before moving and compares them with the files at their destinations. It then verifies all of the following:

- every planned source file was moved;
- no regular source file remains;
- each expected destination path exists with the original filename and identical bytes;
- the union of the five destination inventories exactly equals the planned inventory; and
- no duplicate destination path was created.

A successful execution response has `ok: true`, `performed_move: true`, and `validation.ok: true`. Treat any other response as a failed organization: do not claim completion, inspect the JSON error, and resolve the stated source, naming, extraction, or destination issue. The script deliberately writes no temporary extraction artifacts or logs into either the source collection or the destination folders.

## Interface

Required JSON fields:

- `source_dir` (string): existing directory containing the files to organize.
- `destination_root` (string): directory under which the five subject folders will be created.

Optional JSON fields:

- `perform_move` (boolean, default `false`): only `true` changes the filesystem.
- `ocr_fallback` (boolean, default `true`): try available OCR programs after poor PDF text extraction.
- `ocr_pages` (integer, default `3`, range 1–20): initial PDF pages used for OCR fallback.
- `overrides` (object): mapping of source-relative POSIX paths to allowed category names.

The script emits one JSON object. In a plan it includes `manifest`, `summary`, and `performed_move: false`. In an execution it additionally includes `validation` and post-move destination records. On a validation or runtime error it emits `{ "ok": false, "error": ... }` and exits nonzero.
