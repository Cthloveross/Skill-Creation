# Anonymization quick reference

## Redact (identity-revealing)
- Author full names: byline, running headers/footers, acknowledgements, contribution notes.
- Affiliations incl. abbreviated variants (full name AND short form).
- Email addresses (institutional/personal), esp. in first-page footnotes.
- Correspondence / contribution footnotes (use exact wording from the PDF).
- The paper's OWN arXiv ID (`arXiv:YYMM.NNNNN`), DOI, and venue/acceptance statement.
- Person names in acknowledgements (read the prose: "We thank X and Y ...").
- PDF metadata Author/Creator fields.

## Preserve (do NOT touch)
- Title, abstract, body, methods, results, figures, tables, equations, captions.
- The entire References/Bibliography section, including self-citations.
- arXiv IDs / DOIs that appear INSIDE references (they belong to cited works).
- Page count and overall content length.

## Method rules
- String-level redaction only: `page.search_for(s)` -> `page.add_redact_annot(rect)` ->
  `page.apply_redactions()`. Modify the PDF in place; never rebuild from scratch.
- NEVER redact rectangular regions / page fractions. That destroys content.
- Redact the FULL discovered name, never a bare surname (common words / citations).
- Scope: names/affiliations/emails/ack-names = before references; exact own identifiers
  (arXiv/DOI/venue) = all pages.

## Pass criteria (per PDF)
- remaining_targets empty (recall).
- page_count_ok true.
- extra_words_removed small (background threshold ~<=50) (precision).

## Common failures
- Under-redaction: searched only page 1; missed acknowledgement names; variant spellings;
  text stored with ligatures/hyphenation so search_for missed it (try sub-spans/variants).
- Over-redaction: region blanking; redacting surnames; redacting self-citations; deleting
  whole sections; stripping/altering structure or page count.
