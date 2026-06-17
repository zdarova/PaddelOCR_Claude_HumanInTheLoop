# claude_validator.py

LLM-based semantic validation using Claude Opus 4.8. Checks numeric consistency beyond regex.

## Functions

### `validate_page(page_result: dict) -> dict`

Sends CSV table content to Claude for semantic analysis. Updates `page_result` with:
- `accuracy_score` (0-1)
- `validation_notes` (string summary)
- `validation_errors` (list of specific issues)

If score < threshold → page queued for human review.

### `_queue_page(page_result: dict)`

Saves page data to `working/queue/{stem}_page_{NNNN}.json` for human review.

## Credential Resolution

Priority order:
1. `.env_config` file in project root
2. `ANTHROPIC_API_KEY` environment variable
3. AWS Secrets Manager: `devops-agent/anthropic-api-key` (eu-west-1)

## Claude Prompt Design

The prompt instructs Claude to:
1. Understand Italian number format (dot=thousands, comma=decimal)
2. Verify row sums match totals row
3. Detect common OCR errors (0↔O, 1↔l, 5↔S)
4. Check format consistency across all cells
5. Return structured JSON with accuracy score and specific errors

## Configuration
- `config.yaml` → `validation.claude_model` (default: `claude-opus-4-8`)
- `config.yaml` → `validation.max_tokens` (default: 4096)
- `config.yaml` → `validation.accuracy_threshold` (default: 0.85)

## When Claude Is Called

Claude validation is **separate from** Italian number format validation:
1. Number format check runs ALWAYS (fast, local, regex-based)
2. Claude runs only when `--skip-validation` is NOT set
3. Claude is skipped for pages that already failed number format check (they go straight to queue)

## Cost Considerations
- Claude Opus 4.8: ~$15/M input tokens, ~$75/M output tokens
- Each page validation uses ~500-2000 input tokens + ~200-500 output tokens
- A 22-page PDF costs approximately $0.03-0.10 for full validation
- Use `--skip-validation` during development to avoid API costs
