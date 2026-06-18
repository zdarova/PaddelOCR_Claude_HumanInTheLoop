"""Build final Excel with one tab per page, respecting 'modified' flag."""

import json
import csv
from pathlib import Path
import pandas as pd
from src.config import OCR_DIR, OUTPUT_DIR


def build_excel(pdf_stem: str) -> Path:
    """
    Assemble Excel from all page CSVs in ocr_results/.
    Modified pages (corrected via UI) are picked up automatically.
    Returns path to output Excel.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    excel_path = OUTPUT_DIR / f"{pdf_stem}.xlsx"

    # Find all page JSONs for this PDF
    json_files = sorted(OCR_DIR.glob(f"{pdf_stem}_page_*.json"))
    if not json_files:
        raise FileNotFoundError(f"No OCR results found for {pdf_stem}")

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for json_file in json_files:
            with open(json_file) as f:
                page_data = json.load(f)

            page_num = page_data["page_num"]
            csv_path_str = page_data.get("csv_path", "")
            csv_path = Path(csv_path_str) if csv_path_str else None

            if not csv_path or not csv_path.exists():
                csv_path = OCR_DIR / f"{pdf_stem}_page_{page_num:04d}.csv"

            if csv_path.exists() and csv_path.stat().st_size > 0:
                # Build sheet: metadata header + column headers + table data
                sheet_rows = []

                # Add form metadata as structured rows (label | value | value2 | value3)
                table_header = page_data.get("table_header", {})
                if table_header:
                    meta_rows = [
                        ["Pagina", table_header.get("pagina", ""), "", ""],
                        ["Joint Venture", table_header.get("joint_venture_code", ""), table_header.get("joint_venture_name", ""), ""],
                        ["Tipo Contratto", table_header.get("tipo_contratto", ""), "", ""],
                        ["Attività", table_header.get("attivita_num", ""), table_header.get("attivita_desc", ""), ""],
                        ["Fase", table_header.get("fase_num", ""), table_header.get("fase_desc", ""), ""],
                        ["Subfase", table_header.get("subfase", ""), "", ""],
                        ["Commessa", table_header.get("commessa_code", ""), table_header.get("commessa_desc", ""), ""],
                    ]
                    # Add optional fields if present
                    if table_header.get("titolo_minerario"):
                        meta_rows.insert(3, ["Titolo Minerario", table_header["titolo_minerario"], "", ""])
                    if table_header.get("equity_group"):
                        meta_rows.insert(4, ["Equity Group", table_header["equity_group"], table_header.get("equity_pct", ""), ""])

                    for row in meta_rows:
                        sheet_rows.append(row)
                    sheet_rows.append(["", "", "", ""])  # blank separator

                # Add table data from CSV (includes column headers + data + totals)
                with open(csv_path, newline="") as cf:
                    import csv as csv_mod
                    reader = csv_mod.reader(cf)
                    for row in reader:
                        sheet_rows.append(row)

                # Normalize column count to 4
                for r in sheet_rows:
                    while len(r) < 4:
                        r.append("")
                    if len(r) > 4:
                        r[:] = r[:4]

                df = pd.DataFrame(sheet_rows)
            else:
                df = pd.DataFrame({"note": ["No table data extracted"]})

            sheet_name = f"Page_{page_num}"
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

    return excel_path


def rebuild_page_csv(pdf_stem: str, page_num: int, cells: list[dict]):
    """Rebuild CSV for a specific page after human correction."""
    csv_path = OCR_DIR / f"{pdf_stem}_page_{page_num:04d}.csv"
    json_path = OCR_DIR / f"{pdf_stem}_page_{page_num:04d}.json"

    # Update JSON with modified flag
    if json_path.exists():
        with open(json_path) as f:
            page_data = json.load(f)
        page_data["cells"] = cells
        page_data["modified"] = True
        with open(json_path, "w") as f:
            json.dump(page_data, f, indent=2)

    # Rebuild CSV from cells using row/col indices or adaptive Y-grouping
    if not cells:
        csv_path.write_text("")
        return

    # Prefer structural row/col if available
    if any(c.get("row_idx") is not None for c in cells):
        max_row = max((c["row_idx"] for c in cells if c.get("row_idx") is not None), default=0)
        max_col = max((c["col_idx"] for c in cells if c.get("col_idx") is not None), default=0)
        grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
        for c in cells:
            r, col = c.get("row_idx"), c.get("col_idx")
            if r is not None and col is not None:
                grid[r][col] = c["text"]
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            for row in grid:
                writer.writerow(row)
    else:
        # Polygon bbox: top-left Y = bbox[0][1], top-left X = bbox[0][0]
        def tl_y(c): return c["bbox"][0][1] if isinstance(c["bbox"][0], list) else c["bbox"][1]
        def tl_x(c): return c["bbox"][0][0] if isinstance(c["bbox"][0], list) else c["bbox"][0]
        def height(c):
            if isinstance(c["bbox"][0], list):
                return abs(c["bbox"][3][1] - c["bbox"][0][1])
            return abs(c["bbox"][3] - c["bbox"][1])

        sorted_cells = sorted(cells, key=lambda c: (tl_y(c), tl_x(c)))
        heights = [height(c) for c in sorted_cells]
        heights = [h for h in heights if h > 0]
        median_h = sorted(heights)[len(heights) // 2] if heights else 30
        y_tolerance = max(10, median_h * 0.4)

        rows = []
        current_row = [sorted_cells[0]]
        for cell in sorted_cells[1:]:
            if abs(tl_y(cell) - tl_y(current_row[0])) < y_tolerance:
                current_row.append(cell)
            else:
                rows.append(sorted(current_row, key=lambda c: tl_x(c)))
                current_row = [cell]
        rows.append(sorted(current_row, key=lambda c: tl_x(c)))

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow([c["text"] for c in row])
