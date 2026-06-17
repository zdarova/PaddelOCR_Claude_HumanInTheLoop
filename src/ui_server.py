"""Flask UI for human-in-the-loop correction of low-accuracy OCR pages."""

import json
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from src.config import QUEUE_DIR, OCR_DIR, IMAGES_DIR, ROTATED_DIR, CONFIG
from src.excel_builder import rebuild_page_csv, build_excel

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)


@app.route("/")
def index():
    """List all pages in the review queue."""
    queue_files = sorted(QUEUE_DIR.glob("*.json")) if QUEUE_DIR.exists() else []
    pages = []
    for f in queue_files:
        with open(f) as fh:
            data = json.load(fh)
        pages.append({
            "file": f.name,
            "pdf_stem": data["pdf_stem"],
            "page_num": data["page_num"],
            "accuracy_score": data.get("accuracy_score", 0),
            "notes": data.get("validation_notes", ""),
            "modified": data.get("modified", False),
        })
    return render_template("index.html", pages=pages)


@app.route("/review/<filename>")
def review_page(filename):
    """Review a specific page with bounding box overlay."""
    queue_file = QUEUE_DIR / filename
    if not queue_file.exists():
        return "Page not found", 404
    with open(queue_file) as f:
        page_data = json.load(f)
    return render_template("review.html", page_data=page_data)


@app.route("/api/page/<filename>")
def get_page_data(filename):
    """API: get page OCR data with cells and bounding boxes."""
    queue_file = QUEUE_DIR / filename
    if not queue_file.exists():
        return jsonify({"error": "not found"}), 404
    with open(queue_file) as f:
        return jsonify(json.load(f))


@app.route("/api/image/<path:image_name>")
def serve_image(image_name):
    """Serve page image for bounding box overlay."""
    for directory in [ROTATED_DIR, IMAGES_DIR]:
        img_path = directory / image_name
        if img_path.exists():
            return send_file(img_path)
    return "Image not found", 404


@app.route("/api/save", methods=["POST"])
def save_corrections():
    """Save corrected cells from the UI."""
    data = request.json
    pdf_stem = data["pdf_stem"]
    page_num = data["page_num"]
    cells = data["cells"]

    # Rebuild CSV and mark as modified
    rebuild_page_csv(pdf_stem, page_num, cells)

    # Update queue file
    queue_file = QUEUE_DIR / f"{pdf_stem}_page_{page_num:04d}.json"
    if queue_file.exists():
        with open(queue_file) as f:
            page_data = json.load(f)
        page_data["cells"] = cells
        page_data["modified"] = True
        with open(queue_file, "w") as f:
            json.dump(page_data, f, indent=2)

    return jsonify({"status": "saved", "modified": True})


@app.route("/api/rebuild/<pdf_stem>", methods=["POST"])
def rebuild_excel(pdf_stem):
    """Rebuild Excel output for a PDF after corrections."""
    try:
        path = build_excel(pdf_stem)
        return jsonify({"status": "ok", "path": str(path)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_ui():
    cfg = CONFIG["ui"]
    app.run(host=cfg["host"], port=cfg["port"], debug=False)


if __name__ == "__main__":
    run_ui()
