# excel_builder.py

Assembles final Excel output with one tab per page, including form metadata header.

## Functions

### `build_excel(pdf_stem: str) -> Path`

Reads all `working/ocr_results/{stem}_page_*.json` files and builds Excel at `output/{stem}.xlsx`.

Each sheet contains:
1. **Metadata header** (if available): ALLEGATO, JOINT VENTURE, CONTRATTO, ATTIVITA', FASE, SUBFASE, COMMESSA
2. **Blank separator row**
3. **Table data** from the page CSV

Respects the `modified` flag — pages corrected via UI are automatically picked up.

### `rebuild_page_csv(pdf_stem: str, page_num: int, cells: list[dict])`

Rebuilds a single page CSV after human correction. Sets `modified: true` in the JSON.

## Sheet Naming
- `Page_1`, `Page_2`, ..., `Page_22`

## Dependencies
- `pandas`, `openpyxl`

## Notes
- Uses `on_bad_lines="warn"` for CSV parsing (Italian numbers with commas can confuse pandas)
- Empty pages get a placeholder "No table data extracted" cell
- The `--rebuild` flag in main.py calls `build_excel()` without re-running OCR
