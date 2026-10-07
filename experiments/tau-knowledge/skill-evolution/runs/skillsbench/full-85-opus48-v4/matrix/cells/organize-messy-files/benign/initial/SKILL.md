---
name: organize-messy-files-by-subject
description: >-
  Classify a heterogeneous collection of documents (PDF, DOCX, PPTX, and others)
  into a fixed set of subject folders based on their textual content, then move
  each file into exactly one folder without renaming or altering it. Use this
  Skill when a task supplies a directory of mixed research files and a fixed list
  of subject categories (with one designated fallback category) and asks to sort
  every file into those categories so that no file is left out or duplicated.
---

# Organize messy files into subject folders

## When to use

The public task gives a directory of 100+ mixed files (PDF, DOCX, PPTX, maybe
more) under a source folder and a fixed list of subject categories, each mapped
to a destination folder name. Every file must be moved into exactly one folder,
chosen from the file's own content. One category is the designated *fallback*:
a file that does not clearly fit any other category goes there. Filenames and
bytes must be preserved (move, never rewrite). No file may be left in the source
or duplicated.

The category list, folder names, source directory, and fallback are **read from
the current task at runtime**, not hardcoded. Read the task opening to confirm
the mapping. For this task family the mapping is:

| subject | folder name |
|---|---|
| LLM | `LLM` |
| Trapped ion & quantum computing | `trapped_ion_and_qc` |
| Black hole | `black_hole` |
| DNA | `DNA` |
| Music history (fallback) | `music_history` |

## Important prerequisite: populate the source first

The seeded source folder usually contains only a few files. The full corpus is
fetched by a provided download script (e.g. `/tmp/download_papers.sh`). **Run the
download script before classifying** so all files exist. Internet is allowed.

```bash
bash /tmp/download_papers.sh    # if present; populates the paper folder
ls /root/papers/all | wc -l     # confirm 100+ files are present
```

Inspect where it placed files (`ls -R /root/papers`). The default source
directory is `/root/papers/all`; adjust the `source_dir` argument if the script
writes elsewhere.

## Method

1. **Discover files** recursively under the source directory. Skip the 5
   destination folders themselves and any temporary extraction artifacts.
2. **Extract text** per file with format-appropriate readers and fallbacks
   (`scripts/extract_text.py`): PDF via pdfplumber/pypdf and OCR last resort;
   DOCX/PPTX via python-docx / python-pptx with a raw-ZIP XML fallback (these
   are OOXML ZIP packages whose visible text lives in `<w:t>` / `<a:t>` runs and
   possibly headers/footers/notes). If one reader returns empty text, try the
   next representation before declaring the file unreadable.
3. **Classify** the extracted text with weighted keyword scoring over the fixed
   subjects (`scripts/subjects.py`, `scripts/classify.py`). The subject with the
   highest score wins; if the top score is zero (no evidence), assign the
   fallback subject. The fallback never wins a non-zero tie — a real subject with
   equal evidence is preferred, so the fallback truly means "fits nothing else".
4. **Move** each file into its destination folder, preserving the original name
   and bytes (`shutil.move`). Create destination folders if missing.
5. **Reconcile inventories**: every source file must land in exactly one folder;
   report leftovers, name collisions, and unreadable files.

## End-to-end entrypoint

`scripts/organize.py` does discovery → extraction → classification → move →
reconciliation in one run. It reads JSON on stdin and writes a JSON summary on
stdout.

Input schema (all optional; sensible defaults shown):
```json
{
  "source_dir": "/root/papers/all",
  "dest_root": "/root/papers",
  "subjects": null,          // null => use scripts/subjects.py defaults
  "fallback": "music_history",
  "run_download": false,     // true => run download_script first if source sparse
  "download_script": "/tmp/download_papers.sh",
  "dry_run": false           // true => classify but do not move
}
```
Output schema:
```json
{
  "source_dir": "...", "dest_root": "...",
  "total_source": 123,
  "counts": {"LLM": 30, "trapped_ion_and_qc": 25, ...},
  "moved": [{"name": "x.pdf", "label": "LLM", "method": "pdfplumber"}, ...],
  "unreadable": ["..."],
  "collisions": ["..."],
  "leftover": ["..."],
  "ok": true
}
```

### Run it

```bash
# 1. populate corpus
bash /tmp/download_papers.sh

# 2. (optional) preview classification without moving
echo '{"source_dir":"/root/papers/all","dest_root":"/root/papers","dry_run":true}' \
  | python3 /app/environment/skills/current/scripts/organize.py

# 3. perform the move
echo '{"source_dir":"/root/papers/all","dest_root":"/root/papers"}' \
  | python3 /app/environment/skills/current/scripts/organize.py
```

(Use whatever absolute path the Skill is installed at; `skill_directory` in the
environment points to the current install, typically
`/app/environment/skills/current`.)

## Interpreting results and finishing the task

- Confirm `ok` is `true` and `leftover` is empty: every source file was placed.
- `total_source` should equal the sum of `counts` plus `unreadable` handled.
  Any file in `unreadable` was still assigned (fallback if no text) and moved,
  so it is not left out — but double-check such files manually if few, since a
  bad extraction could misroute them.
- Verify on disk: each of the five folders exists under `dest_root`, the source
  folder is now empty of regular files, and no filename appears twice.
  ```bash
  for d in LLM trapped_ion_and_qc black_hole DNA music_history; do
    echo "$d: $(ls /root/papers/$d 2>/dev/null | wc -l)"; done
  ls /root/papers/all | wc -l   # expect 0 remaining regular files
  ```
- `collisions` lists names that already existed in a destination; resolve by
  inspection (the task forbids renaming, so a genuine collision indicates a
  duplicate corpus file). The script does not overwrite; it reports instead.

## Tuning classification

Keyword lists and weights live in `scripts/subjects.py` and
`references/subject_keywords.md`. If a spot check shows systematic misrouting
(e.g. quantum-computing papers landing in the fallback), add discriminative
phrases/weights there and re-run `dry_run` to re-check — this is a reusable fix,
not a per-file override. Never hardcode a specific filename-to-folder mapping;
always decide from extracted content at runtime.

## Failure modes handled

- Empty/garbled extraction → multi-reader fallback, then OCR, then fallback
  subject so the file is never lost.
- Missing optional libraries (pdfplumber, python-docx, python-pptx, OCR) →
  raw-ZIP XML parsing for OOXML and graceful degradation for PDF; the file is
  still moved (fallback subject if no text could be recovered).
- Sparse source folder → `run_download` can invoke the provided script, or run
  it manually first.
- Unsupported extensions still get moved to the fallback subject so nothing is
  left behind.
