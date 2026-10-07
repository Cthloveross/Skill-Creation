# Protein-expression Task output contract (public request summary)

Workbook: two sheets, `Task` (work area) and `Data` (raw log2 expression).

Required formula outputs on the `Task` sheet (default coordinates; always
confirm at runtime with inspect_workbook.py):

1. Lookup block `C11:L20`: value for each of 10 target proteins (ids in
   `A11:A20`) x 10 samples (names in row 10, `C10:L10`). Match on BOTH protein
   id and sample name (INDEX + two MATCH, or VLOOKUP/XLOOKUP equivalent).
2. Group statistics `B24:K27` (proteins across columns B-K, four statistics down
   rows 24-27): Control mean, Control stdev, Treated mean, Treated stdev. The
   group of each sample column is given in row 9 (Control vs Treated, blue
   highlight). Data is already log2-transformed -> plain AVERAGE / STDEV.
3. Fold change rows 32-41: column C = Treated mean - Control mean (log2 fold
   change); column D = 2^(log2 fold change).

Constraints:
- Use real formulas, never hard-coded numbers.
- No macros / VBA.
- Do not change file format, colours or fonts; do not add sheets.

Integrity note: openpyxl writes formula text but not cached values. Set
fullCalcOnLoad and/or recalculate with a spreadsheet engine (LibreOffice) so a
value-reading consumer sees numbers, then reopen in data_only mode and confirm
the target cells are numeric and error-free. An independent Python recomputation
from the Data sheet is used to confirm the formulas are logically correct even
when no spreadsheet engine is available.
