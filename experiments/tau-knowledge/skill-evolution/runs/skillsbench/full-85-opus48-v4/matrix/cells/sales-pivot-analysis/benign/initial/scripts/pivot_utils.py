"""Helpers to build NATIVE Excel pivot tables with openpyxl.

The cache field list and the per-column pivot-field list must each have exactly
one entry per source column, in column order. The row/column/data reference
lists index into those columns positionally. A single cache object is shared by
all pivots so the writer deduplicates it to cache index 0.
"""
from openpyxl.utils import get_column_letter
from openpyxl.pivot.cache import (
    CacheDefinition, CacheSource, WorksheetSource, CacheField, SharedItems,
)
from openpyxl.pivot.table import (
    TableDefinition, Location, PivotField, RowColField, RowColItem, DataField,
)


def data_ref(ncols, nrows):
    """A1-style range for header row + nrows data rows across ncols columns."""
    return "A1:%s%d" % (get_column_letter(ncols), nrows + 1)


def build_shared_cache(columns, source_sheet_title, ref):
    """One CacheDefinition with one CacheField per source column (in order)."""
    fields = [CacheField(name=str(c), sharedItems=SharedItems()) for c in columns]
    wss = WorksheetSource(ref=ref, sheet=source_sheet_title)
    src = CacheSource(type="worksheet", worksheetSource=wss)
    cache = CacheDefinition(cacheSource=src, cacheFields=fields, recordCount=0)
    try:
        cache.refreshOnLoad = True
    except Exception:
        pass
    return cache


def add_pivot(ws_pivot, cache, columns, row_col, data_col, agg,
              display_name, col_col=None, name="PivotTable"):
    """Attach a pivot table object to ws_pivot.

    columns   : list of source column names (same order as the cache fields)
    row_col   : name of the row-axis column (STATE)
    data_col  : name of the aggregated column
    agg       : 'sum' | 'count' | 'average' | 'min' | 'max' ...
    col_col   : name of the column-axis column, or None for a simple pivot
    """
    n = len(columns)
    r = columns.index(row_col)
    d = columns.index(data_col)
    c = columns.index(col_col) if col_col is not None else None

    pivot_fields = []
    for i in range(n):
        if i == r:
            pf = PivotField(axis="axisRow", showAll=False)
        elif c is not None and i == c:
            pf = PivotField(axis="axisCol", showAll=False)
        elif i == d:
            pf = PivotField(dataField=True, showAll=False)
        else:
            pf = PivotField(showAll=False)
        pivot_fields.append(pf)

    row_fields = [RowColField(x=r)]
    row_items = [RowColItem()]
    if c is not None:
        col_fields = [RowColField(x=c)]
        col_items = [RowColItem()]
    else:
        col_fields = []
        col_items = []

    data_fields = [DataField(name=display_name, fld=d, subtotal=agg,
                             baseField=0, baseItem=0)]

    loc = Location(ref="A3:C20", firstHeaderRow=1, firstDataRow=2, firstDataCol=1)

    table = TableDefinition(
        name=name, cacheId=0, dataCaption="Values", location=loc,
        pivotFields=pivot_fields, rowFields=row_fields, rowItems=row_items,
        colFields=col_fields, colItems=col_items, dataFields=data_fields,
    )
    table.cache = cache
    ws_pivot._pivots.append(table)
    return table
