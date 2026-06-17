# text_extractor.py

Extracts tables from text-selectable (non-scanned) PDF pages using pdfplumber.

## Function

### `extract_text_table(pdf_path: Path, page_num: int) -> dict`

Uses pdfplumber's `page.extract_tables()` to get table data directly from the PDF text layer.

Returns same schema as `table_ocr.extract_table()` for consistency.

## When Used
- Only for pages classified as `"text"` by `pdf_classifier.py`
- These pages have embedded text (not scanned images)
- No OCR needed — confidence is always 1.0

## Output
- Bounding boxes are synthetic (computed from row/col indices, not pixel positions)
- `extraction_mode: "text_selectable"`
- `row_idx` and `col_idx` always populated (from pdfplumber table structure)

## Dependencies
- `pdfplumber`
