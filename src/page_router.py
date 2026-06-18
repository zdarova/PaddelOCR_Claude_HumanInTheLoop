"""Page type router — classifies pages to drive extraction strategy.

Page types in this document family:
- COVER: sparse, title page (page 1)
- INVOICE: contains IVA, fattura amounts (page 2)
- SUMMARY: TOTALE RENDICONTO, STORNO, DIFFERENZA DA FATTURARE (page 3)
- DETAIL_TABLE: CODICE NATURA columns, line items, TOTALE COMMESSA (pages 4-15, 18-20)
- PARTNER_SPLIT: ALEANNA/equity partner allocation tables (pages 16-17, 21-22)
"""

from typing import Literal

PageType = Literal["COVER", "INVOICE", "SUMMARY", "DETAIL_TABLE", "PARTNER_SPLIT", "UNKNOWN"]


def classify_page_type(cells: list[dict]) -> tuple[PageType, float]:
    """
    Classify a page based on OCR cell content.
    Returns (page_type, confidence 0-1).
    """
    if not cells or len(cells) < 5:
        return "COVER", 0.9

    texts = [c["text"].upper().strip() for c in cells]
    all_text = " ".join(texts)

    # Score each type
    scores: dict[PageType, float] = {
        "COVER": 0.0,
        "INVOICE": 0.0,
        "SUMMARY": 0.0,
        "DETAIL_TABLE": 0.0,
        "PARTNER_SPLIT": 0.0,
    }

    # INVOICE signals
    if "IVA" in all_text and ("FATTUR" in all_text or "IMPORTO" in all_text):
        scores["INVOICE"] += 0.8
    if "BOLLO" in all_text or "PAGAMENTO" in all_text:
        scores["INVOICE"] += 0.2

    # SUMMARY signals
    if "TOTALE RENDICONTO" in all_text or "TOTALERENDICONTO" in all_text:
        scores["SUMMARY"] += 0.6
    if "DIFFERENZA DA FATTURARE" in all_text:
        scores["SUMMARY"] += 0.3
    if "STORNO" in all_text:
        scores["SUMMARY"] += 0.2

    # DETAIL_TABLE signals
    has_codice = any("CODICE" in t for t in texts)
    has_descrizione = any("DESCRIZIONE" in t for t in texts)
    has_totale_periodo = any("TOTALE PERIODO" in t for t in texts)
    has_totale_commessa = any("TOTALE COMMESSA" in t for t in texts)
    if has_codice and has_descrizione:
        scores["DETAIL_TABLE"] += 0.5
    if has_totale_periodo:
        scores["DETAIL_TABLE"] += 0.3
    if has_totale_commessa:
        scores["DETAIL_TABLE"] += 0.3
    # Line item codes (7-digit numeric or P-prefix)
    code_count = sum(1 for t in texts if _is_line_item_code(t))
    if code_count >= 2:
        scores["DETAIL_TABLE"] += 0.2

    # PARTNER_SPLIT signals
    if "ALEANNA" in all_text:
        scores["PARTNER_SPLIT"] += 0.6
    if "EQUITY" in all_text or "TOTALE EQUITY" in all_text:
        scores["PARTNER_SPLIT"] += 0.3
    if "TITOLO MINERARIO" in all_text and not has_codice:
        scores["PARTNER_SPLIT"] += 0.2

    # COVER: very few cells, no strong signals
    if len(cells) < 10 and max(scores.values()) < 0.3:
        scores["COVER"] = 0.7

    # Pick highest
    best_type = max(scores, key=scores.get)
    confidence = scores[best_type]

    # Normalize confidence to 0-1
    confidence = min(1.0, confidence)

    return best_type, confidence


def _is_line_item_code(text: str) -> bool:
    """Check if text looks like an accounting line item code."""
    text = text.strip()
    if not text:
        return False
    # 7-digit numeric codes (7110034, 7215006, etc.)
    if text.isdigit() and 5 <= len(text) <= 8:
        return True
    # P-prefix codes (P0099997, P0000902)
    if text.startswith("P") and len(text) >= 5 and text[1:].isdigit():
        return True
    # E/I/M prefix codes
    if text[0] in "EIM" and len(text) >= 5 and "." in text:
        return True
    return False
