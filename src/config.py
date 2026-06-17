import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input"
WORKING_DIR = ROOT / "working"
IMAGES_DIR = WORKING_DIR / "images"
ROTATED_DIR = WORKING_DIR / "rotated"
OCR_DIR = WORKING_DIR / "ocr_results"
QUEUE_DIR = WORKING_DIR / "queue"
OUTPUT_DIR = ROOT / "output"


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


CONFIG = load_config()
