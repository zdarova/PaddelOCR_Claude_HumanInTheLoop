# pdf_classifier.py

Classifies each page of a PDF as either **text-selectable** or **scanned** (image-based).

## Function

### `classify_pages(pdf_path: Path) -> dict[int, str]`

Returns `{page_number: "text" | "scanned"}` for every page (1-indexed).

**Logic**: Uses `pdfplumber` to extract text. If a page has ≥ 50 characters of extractable text, it's `"text"`. Otherwise it's `"scanned"` and needs OCR.

## Dependencies
- `pdfplumber`

## Usage
```python
from src.pdf_classifier import classify_pages
result = classify_pages(Path("input/doc.pdf"))
# {1: "text", 2: "scanned", 3: "scanned", ...}
```

## Customization
- Adjust `TEXT_THRESHOLD` constant (default 50) to change sensitivity.
