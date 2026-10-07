# Implementation notes

## Required output contract (from the public task)
- Output path default `/root/demographic_analysis.xlsx` (override via config).
- Exactly 5 sheets, exact names/order:
  `Population by State`, `Earners by State`, `Regions by State`,
  `State Income Quartile`, `SourceData`.
- 4 native pivot tables (sheets 1-4). Sheet 5 is a flat enriched table.
- Pivot specs:
  1 STATE / Sum POPULATION_2023
  2 STATE / Sum EARNERS
  3 STATE / Count (number of SA2 regions = row count)
  4 STATE rows x Quarter columns / Sum EARNERS
- SourceData adds `Quarter` (Q1..Q4) and `Total` (EARNERS x MEDIAN_INCOME).

## Quartile ambiguity
The wording "quartiles based on MEDIAN_INCOME ranges" is ambiguous between
equal-width range binning and percentile quartiles (see frozen background). The
builder defaults to `range` (equal-width: min..max split into four equal bands,
lower-inclusive, max in Q4). Switch `quartile_method` to `quantile` if the
`range` interpretation is rejected. Both yield labels Q1 (lowest) .. Q4 (highest).

## openpyxl pivot structure
- `openpyxl.pivot.cache`: CacheDefinition / CacheSource / WorksheetSource /
  CacheField / SharedItems. One CacheField per source column, in order.
- `openpyxl.pivot.table`: TableDefinition / Location / PivotField / RowColField /
  RowColItem / DataField. One PivotField per source column; axis='axisRow' for
  STATE, axis='axisCol' for Quarter, dataField=True for the aggregated column.
- rowFields/colFields hold RowColField(x=index); dataFields hold
  DataField(fld=index, subtotal='sum'|'count', name=display).
- A single CacheDefinition is attached to all four TableDefinition.cache so the
  writer deduplicates it to cache index 0; `refreshOnLoad=True` lets Excel
  recompute values on open.

## Known fragilities to check during evolution
- PDF/Excel header names differ from the canonical names -> inspect
  build_report output `columns` and adjust token matching in data_io.CANON.
- openpyxl version differences in pivot class constructors -> adjust
  pivot_utils.py; keep axis flags consistent with the reference-list indices.
- Inner-join row count (warnings report unmatched keys on each side).
