"""Launch the human-in-the-loop correction UI."""

from src.ui_server import run_ui

if __name__ == "__main__":
    print("🌐 Starting OCR Review UI at http://127.0.0.1:5000")
    run_ui()
