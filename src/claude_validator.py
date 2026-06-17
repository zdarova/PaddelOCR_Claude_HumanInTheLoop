"""Claude Opus validation — checks numeric consistency (row sums, totals)."""

import json
import os
from pathlib import Path

import boto3
from anthropic import Anthropic
from src.config import CONFIG, QUEUE_DIR

_client = None
_SECRET_NAME = "devops-agent/anthropic-api-key"
_REGION = "eu-west-1"


def _load_env_config():
    """Load .env_config file into os.environ if it exists."""
    env_file = Path(__file__).parent.parent / ".env_config"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _get_anthropic_credentials() -> dict:
    """
    Get Anthropic credentials. Priority:
    1. Environment variable ANTHROPIC_API_KEY (or from .env_config)
    2. AWS Secrets Manager (devops-agent/anthropic-api-key)
    """
    _load_env_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return {
            "api_key": api_key,
            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
        }

    # Fallback: AWS Secrets Manager
    session = boto3.session.Session()
    sm = session.client("secretsmanager", region_name=_REGION)
    resp = sm.get_secret_value(SecretId=_SECRET_NAME)
    return json.loads(resp["SecretString"])


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        creds = _get_anthropic_credentials()
        _client = Anthropic(
            api_key=creds["api_key"],
            base_url=creds.get("base_url"),
        )
    return _client


def validate_page(page_result: dict) -> dict:
    """
    Send table data to Claude for validation.
    Returns page_result updated with 'accuracy_score' and 'validation_notes'.
    If accuracy < threshold, adds to queue.
    """
    cfg = CONFIG["validation"]
    csv_path = Path(page_result["csv_path"])
    csv_content = csv_path.read_text() if csv_path.exists() else ""

    if not csv_content.strip():
        page_result["accuracy_score"] = 0.0
        page_result["validation_notes"] = "Empty table — no data extracted"
        _queue_page(page_result)
        return page_result

    prompt = f"""Analyze this CSV table extracted via OCR from an Italian accounting form.

IMPORTANT — Italian number format:
- Dot (.) is the THOUSANDS separator: 610.923 = six hundred ten thousand nine hundred twenty-three
- Comma (,) is the DECIMAL separator: 610.923,82 = 610923.82
- Example: 4.152,96 = 4152.96 | 752.087,28 = 752087.28

Template structure:
- Header: year, JV code, contract type, activity, phase, subphase, commessa
- Table columns: CODICE | NATURA | DESCRIZIONE NATURA | TOTALE PERIODO | TOTALE PROGRESSIVO
- Variable number of rows with CODICE NATURA line items
- Footer: TOTALE COMMESSA (sum of all line items)

Check:
1. Do the TOTALE PERIODO values of individual rows sum to the TOTALE COMMESSA row (using Italian number format)?
2. Do the TOTALE PROGRESSIVO values of individual rows sum to the TOTALE COMMESSA progressivo?
3. Are there obvious OCR errors in numbers (e.g. 'O' instead of '0', 'l' instead of '1', 'S' instead of '5')?
4. Are all numbers in consistent Italian format (dot=thousands, comma=decimal)?

Return JSON only:
{{
  "accuracy_score": <float 0-1>,
  "errors": [
    {{"row": <int>, "col": <int>, "current": "<val>", "expected": "<val>", "reason": "<why>"}}
  ],
  "notes": "<summary>"
}}

CSV content:
```
{csv_content}
```"""

    client = _get_client()
    response = client.messages.create(
        model=cfg["claude_model"],
        max_tokens=cfg["max_tokens"],
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse response
    text = response.content[0].text
    try:
        json_start = text.index("{")
        json_end = text.rindex("}") + 1
        validation = json.loads(text[json_start:json_end])
    except (ValueError, json.JSONDecodeError):
        validation = {"accuracy_score": 0.5, "errors": [], "notes": "Could not parse validation response"}

    page_result["accuracy_score"] = validation.get("accuracy_score", 0.5)
    page_result["validation_notes"] = validation.get("notes", "")
    page_result["validation_errors"] = validation.get("errors", [])

    # Queue for human review if low accuracy
    if page_result["accuracy_score"] < cfg["accuracy_threshold"]:
        _queue_page(page_result)

    return page_result


def _queue_page(page_result: dict):
    """Add page to human review queue."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    queue_file = QUEUE_DIR / f"{page_result['pdf_stem']}_page_{page_result['page_num']:04d}.json"
    with open(queue_file, "w") as f:
        json.dump(page_result, f, indent=2)
