# table_reconstructor.py

Template-aware table grid reconstruction from raw OCR cells using spatial analysis.

## Main Functions

### `reconstruct_table(cells: list[dict]) -> dict`

Returns:
```python
{
    "header": {"allegato": "...", "commessa": "...", ...},  # form metadata
    "columns": ["CODICE NATURA", "DESCRIZIONE NATURA", "TOTALE PERIODO", "TOTALE PROGRESSIVO"],
    "rows": [["7110034", "Description", "0,00", "45,50"], ...]
}
```

### `validate_italian_numbers(result: dict) -> dict`

Validates all financial cells and column sums:
```python
{
    "valid": True/False,
    "accuracy_score": 0.0-1.0,
    "invalid_cells": [{"row": 3, "col": "TOTALE PERIODO", "value": "bad", "reason": "..."}],
    "sum_check": {
        "periodo": {"computed": "610.923,82", "expected": "610.923,82", "match": True},
        "progressivo": {"computed": "752.087,28", "expected": "752.087,28", "match": True}
    }
}
```

### `write_table_csv(grid, csv_path)`

Writes row list to CSV file.

## Algorithm

### Column Detection (`_find_column_anchors`)
1. Scan all cells for known header text patterns (case-insensitive)
2. Use header cell X-positions as column anchor points
3. Column boundaries = midpoints between adjacent anchors
4. Handles split headers (e.g., "TOTALE" + "PROGRESSIVO" as separate OCR cells)

### Row Detection (`_build_rows`)
1. Assign each cell to nearest column based on X-position
2. Find first-column cells — these have clean Y-spacing (34+ px between rows)
3. Compute row tolerance = 45% of minimum first-column spacing
4. Cluster all Y-tops using computed tolerance
5. Assign each cell to nearest row anchor (within 25px)

### Metadata Extraction (`_extract_metadata`)
Extracts form header fields from cells above the table header row:
- ALLEGATO, JOINT VENTURE, TIPO CONTRATTO, ATTIVITA', FASE, SUBFASE, COMMESSA

### Number Validation (`validate_italian_numbers`)
- Regex: `^\d{1,3}(\.\d{3})*,\d{2}$`
- Checks every cell in TOTALE PERIODO and TOTALE PROGRESSIVO columns
- Computes column sums and compares to TOTALE row
- Accuracy score = 70% format compliance + 30% sum match
- Any failure → page flagged for human review

## Italian Number Format

| Valid | Invalid | Reason |
|-------|---------|--------|
| `0,00` | `0.00` | Wrong decimal separator |
| `45,50` | `45,5` | Must have 2 decimal places |
| `4.152,96` | `4152,96` | Missing thousands dot |
| `610.923,82` | `610923,82` | Missing thousands dots |
| `7.296.050,00` | `7.296.05,00` | Wrong grouping |

## Extending for New Templates

To support a different form layout:
1. Add new header patterns in `_find_column_anchors()`
2. Adjust column count expectations
3. Update `validate_italian_numbers()` to match the new totals row pattern
4. The row detection algorithm is template-agnostic (adapts to any column count)
