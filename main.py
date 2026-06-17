"""Main pipeline: PDF → classify → render → rotate → OCR → validate → Excel."""

import sys
import argparse
from pathlib import Path
from src.config import INPUT_DIR
from src.pdf_classifier import classify_pages
from src.page_renderer import render_pages
from src.rotation_corrector import correct_rotation
from src.table_ocr import extract_table
from src.text_extractor import extract_text_table
from src.claude_validator import validate_page
from src.excel_builder import build_excel


def process_pdf(pdf_path: Path, pages: list[int] | None = None, skip_validation: bool = False) -> Path:
    """
    Run full pipeline on a PDF.
    If pages is None, processes ALL pages. Otherwise only the specified page numbers.
    Returns path to output Excel.
    """
    print(f"📄 Processing: {pdf_path.name}")

    # 1. Classify pages
    print("  🔍 Classifying pages...")
    page_types = classify_pages(pdf_path)

    # Filter to requested pages (or all)
    if pages:
        page_types = {p: t for p, t in page_types.items() if p in pages}
        missing = set(pages) - set(page_types.keys())
        if missing:
            print(f"  ⚠️  Pages not found in PDF: {sorted(missing)}")

    scanned = [p for p, t in page_types.items() if t == "scanned"]
    text_pages = [p for p, t in page_types.items() if t == "text"]
    print(f"     Total: {len(page_types)} pages | Text-selectable: {len(text_pages)}, Scanned: {len(scanned)}")

    all_results = []

    # 2. Process text-selectable pages
    for page_num in text_pages:
        print(f"  📝 Extracting text table from page {page_num}...")
        result = extract_text_table(pdf_path, page_num)
        all_results.append(result)

    # 3. Render scanned pages to images
    if scanned:
        print(f"  🖼️  Rendering {len(scanned)} scanned pages...")
        images = render_pages(pdf_path, scanned)

        for page_num, image_path in images.items():
            # 4. Rotate/deskew
            print(f"  🔄 Correcting rotation for page {page_num}...")
            rotated_path = correct_rotation(image_path)

            # 5. OCR
            print(f"  🔬 Running OCR on page {page_num}...")
            result = extract_table(rotated_path, page_num, pdf_path.stem)
            all_results.append(result)

    # 6. Validate with Claude (raw_ocr pages auto-flagged for review)
    if not skip_validation:
        print("  🤖 Validating with Claude...")
        for result in all_results:
            if result.get("extraction_mode") == "raw_ocr":
                print(f"     Page {result['page_num']}: ⚠️ raw_ocr fallback — auto-queued for review")
                result["accuracy_score"] = 0.0
                result["validation_notes"] = "Raw OCR fallback (no table structure detected) — needs manual review"
                from src.claude_validator import _queue_page
                _queue_page(result)
            else:
                result = validate_page(result)
                score = result.get("accuracy_score", 0)
                status = "✅" if score >= 0.85 else "⚠️"
                print(f"     Page {result['page_num']}: {status} {score:.0%}")

    # 7. Build Excel
    print("  📊 Building Excel output...")
    excel_path = build_excel(pdf_path.stem)
    print(f"  ✅ Done: {excel_path}")
    return excel_path


def rebuild(pdf_path: Path) -> Path:
    """Rebuild Excel from existing OCR results (after human corrections)."""
    print(f"🔄 Rebuilding Excel for: {pdf_path.stem}")
    excel_path = build_excel(pdf_path.stem)
    print(f"  ✅ Done: {excel_path}")
    return excel_path


def main():
    parser = argparse.ArgumentParser(description="PDF Table OCR Pipeline")
    parser.add_argument("pdf", help="Path to PDF file (absolute or relative to input/)")
    parser.add_argument("--pages", type=int, nargs="+", help="Specific page numbers to process (default: all)")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild Excel from existing OCR results")
    parser.add_argument("--skip-validation", action="store_true", help="Skip Claude validation step")
    args = parser.parse_args()

    pdf_file = Path(args.pdf)
    if not pdf_file.exists():
        pdf_file = INPUT_DIR / args.pdf
    if not pdf_file.exists():
        print(f"❌ File not found: {args.pdf}")
        sys.exit(1)

    if args.rebuild:
        rebuild(pdf_file)
    else:
        process_pdf(pdf_file, pages=args.pages, skip_validation=args.skip_validation)


if __name__ == "__main__":
    main()
