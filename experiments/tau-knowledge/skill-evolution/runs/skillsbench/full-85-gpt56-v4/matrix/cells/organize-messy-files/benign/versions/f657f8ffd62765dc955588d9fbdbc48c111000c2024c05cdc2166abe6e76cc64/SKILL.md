---
name: organize-research-documents-by-subject
description: Classify a mixed collection of research papers and Office documents by their extracted content and move every source document, unchanged, into five required topical folders: LLM, trapped_ion_and_qc, black_hole, DNA, and music_history. Use when a document collection must be exhaustively organized without renaming or altering files.
---

# Organize research documents by subject

This Skill exhaustively moves supported document files into the five requested subject directories while preserving their original filenames and bytes. Classification is based on text extracted from the supplied files, not fixed filenames, slide IDs, or a precomputed mapping.

## Required runtime inputs

The organizer script receives one JSON object on stdin:

```json
{
  "source_dir": "/absolute/path/to/unorganized/files",
  "destination_dir": "/absolute/path/to/parent/of-subject-folders"
}
```

It writes a JSON report to stdout. `source_dir` may contain PDFs, DOCX, PPTX, and other files. The destination parent will contain exactly these folders created as needed:

- `LLM`
- `trapped_ion_and_qc`
- `black_hole`
- `DNA`
- `music_history`

The script uses atomic filesystem moves (`os.replace`) within a filesystem and never edits document bytes or filenames. It refuses a filename collision rather than overwriting a document.

## Execution procedure

1. Identify the actual source collection. Do not include helper scripts, extraction text, or other temporary artifacts as source documents.
2. If the task supplies a download/preparation script that is necessary to populate the collection, inspect its target paths and run it before organizing. Confirm downloaded files are present in the source directory. Do not move the preparation script unless it is explicitly part of the requested collection.
3. Run the organizer, for example:

   ```sh
   python3 /app/environment/skills/current/scripts/organize.py <<'JSON'
   {"source_dir":"/root/papers/all","destination_dir":"/root/papers"}
   JSON
   ```

4. Read its JSON report. A successful report has `ok: true`, `source_after: []`, no `collisions`, and `destination_inventory_count` equal to `source_before_count`. The `moved` list records the content-derived destination for every file.
5. If the script reports an extraction issue, inspect that document using a format-appropriate representation before deciding it is unusable: PDF text extraction may fail on scanned material; DOCX/PPTX are OOXML ZIP packages whose XML text can still be read. The organizer already uses these representations and records extraction method/quality in the report. Rerun only after resolving collisions or input-path errors.
6. Verify independently that every original filename occurs once under the five folders, no original remains in the source directory, and no files other than the five folder directories were created under the destination parent. Do not add reports or temporary files to the destination collection.

## Classification method and assumptions

The script extracts PDF text with `pdftotext` when available and falls back to printable strings. For DOCX and PPTX it reads textual XML from the OOXML package (including all Word document parts or PowerPoint slides and notes). It normalizes text and assigns weighted evidence to all five topics. It gives the leading title region additional weight, because a long paper can mention an unrelated method in its background or references. Strong multiword subject terms outweigh generic words. `music_history` is selected both for explicit music evidence and as the required exhaustive remainder when no subject evidence is found.

For low-confidence or unreadable files, the script still assigns the required remainder category and marks the record `needs_review` in stdout; it does not leave a document unfiled. Review these records from the original moved document if the task permits human judgment, but do not change the file during review.

The script treats every regular file in the source tree as a collection member, including an unsupported extension. It flattens nested source paths by basename because requested output folders contain files directly; collisions are a deliberate failure to avoid silent renaming. Use a source directory containing only the collection.

## Validation guarantees

Before moving anything, the script inventories all regular source files and builds a complete plan. It validates that every planned destination is one of the five folders, that each source appears once, and that no target already exists. After moves it compares source and destination inventories and reports omissions, duplicates, renamed files, and leftovers. A nonzero exit means the collection was not fully organized and should be corrected before claiming completion.
