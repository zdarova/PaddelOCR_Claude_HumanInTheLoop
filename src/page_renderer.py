"""Render PDF pages to images for OCR processing."""

from pathlib import Path
from pdf2image import convert_from_path
from src.config import IMAGES_DIR, CONFIG


def render_pages(pdf_path: Path, page_numbers: list[int]) -> dict[int, Path]:
    """Render specified pages to PNG images. Returns {page_num: image_path}."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem
    dpi = CONFIG["rendering"]["dpi"]
    results = {}

    for page_num in page_numbers:
        images = convert_from_path(
            pdf_path, dpi=dpi, first_page=page_num, last_page=page_num
        )
        if images:
            out_path = IMAGES_DIR / f"{stem}_page_{page_num:04d}.png"
            images[0].save(out_path, "PNG")
            results[page_num] = out_path

    return results
