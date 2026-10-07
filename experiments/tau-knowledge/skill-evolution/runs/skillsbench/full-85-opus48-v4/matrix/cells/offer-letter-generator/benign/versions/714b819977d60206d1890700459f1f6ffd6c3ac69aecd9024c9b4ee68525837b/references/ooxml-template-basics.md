# Safe OOXML template filling

A Word document is a ZIP package of related XML parts. Visible text may be split
across multiple runs even when a placeholder appears contiguous to a reader, so
replacement logic must reason about logical text spans while preserving the
surrounding run and paragraph structure.

Template content may occur outside the main document body, including headers,
footers, tables, text boxes, and other related parts. Conditional blocks should
be evaluated as structured regions: retain or remove their contents as directed,
and always remove control markers from the final document.

After substitution, reopen the package, parse all modified XML, confirm that no
unresolved placeholder or conditional marker remains, and verify that the
document still opens normally. Preserve styles, relationships, and unrelated
content rather than rebuilding the file from scratch.

## How this Skill applies the guidance
- Placeholder replacement is done per paragraph on the concatenation of its
  `<w:t>` runs, then redistributed back into those runs, so tokens split across
  runs are resolved without destroying run/paragraph structure.
- The relocation conditional is handled at paragraph granularity: inline when
  both markers share a paragraph, otherwise by trimming the edge paragraphs and
  deleting fully-enclosed paragraphs. Markers are always stripped.
- Only `.xml` parts that actually contain `{{` are parsed and rewritten; all
  other parts (styles, media, relationships) are copied byte-for-byte, and the
  original root `xmlns:*` declarations are re-injected to keep compatibility
  prefixes valid.
- The output is re-opened and scanned for any surviving `{{...}}` tokens or
  IF/END markers before reporting success.
