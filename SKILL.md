---
name: mineru-pdf-analysis
description: Analyze user-uploaded PDF files through the project's MinerU parsing flow and produce raw Markdown, cleaned Markdown, and metadata for Agent document QA. Use when a user uploads or references a PDF and wants the Agent to summarize, extract, compare, or answer questions from that PDF.
---

# MinerU PDF Analysis

## Core Rule

When the user provides a PDF, do not analyze the PDF directly from binary content. First run this skill's script to parse the PDF with MinerU, then read the generated cleaned Markdown and use it as the document context.

## Script

Use:

```bash
python skills/mineru-pdf-analysis/scripts/analyze_pdf_with_mineru.py /path/to/user-uploaded.pdf
```

The script:

1. Requests a MinerU upload URL.
2. Uploads the PDF bytes to MinerU.
3. Polls MinerU until parsing finishes.
4. Downloads the result zip.
5. Extracts `full.md`.
6. Writes raw Markdown.
7. Normalizes Markdown whitespace without deleting domain-specific content.
8. Writes `metadata.json`.
9. Prints metadata JSON to stdout.

## Token Configuration

The script includes a built-in MinerU token so platform users can run it without extra setup.

If the platform owner needs to override the built-in token, set:

```bash
export MINERU_TOKEN="your-mineru-token"
```

You may also pass `--token` for one-off testing.

## Output Contract

The script prints JSON like:

```json
{
  "pdf_path": "/absolute/path/to/file.pdf",
  "output_dir": "/absolute/path/to/mineru-output/1a2b3c4d",
  "raw_markdown_path": "/absolute/path/to/mineru-output/1a2b3c4d/<batch_id>.md",
  "cleaned_markdown_path": "/absolute/path/to/mineru-output/1a2b3c4d/<batch_id>.cleaned.md",
  "metadata_path": "/absolute/path/to/mineru-output/1a2b3c4d/metadata.json",
  "batch_id": "mineru-batch-id",
  "model_version": "vlm",
  "language": "ch",
  "enable_table": true,
  "enable_formula": true,
  "is_ocr": false,
  "pdf_size": 12345
}
```

**Note**: Output files are named with `<batch_id>` (e.g., `e995397c-2db8-4160-962e-03d68f27c15d.md`) instead of the PDF filename to avoid Windows path length limits (260 characters). The `metadata.json` records the original `pdf_path` for reference.

After the script succeeds, always read `cleaned_markdown_path` for normal document QA. Use `raw_markdown_path` only when the user asks to inspect MinerU's unmodified output.

## Default MinerU Settings

- `model_version`: `vlm`
- `language`: `ch`
- `enable_table`: `true`
- `enable_formula`: `true`
- `is_ocr`: `false`
- polling timeout: `3600` seconds
- polling interval: `5` seconds

For scanned PDFs, rerun with `--ocr`.

## Optional Arguments

```bash
python skills/mineru-pdf-analysis/scripts/analyze_pdf_with_mineru.py /path/to/file.pdf \
  --output-dir /path/to/output \
  --ocr \
  --language ch \
  --model-version vlm
```

Useful flags:

- `--output-dir`: choose where Markdown and metadata are written.
- `--ocr`: enable OCR for scanned PDFs.
- `--disable-table`: disable table extraction.
- `--disable-formula`: disable formula extraction.
- `--timeout-seconds`: change MinerU polling timeout.
- `--interval-seconds`: change MinerU polling interval.

## Markdown Normalization

The cleaned Markdown is intentionally conservative because this skill may serve different users and document types. It only:

- Removes trailing whitespace from non-empty lines.
- Collapses repeated blank lines.
- Removes leading and trailing blank lines.

Do not add user-specific deletion rules unless the deploying platform explicitly requires them.

## Agent Workflow

1. Receive or locate the user's uploaded PDF path.
2. Run the script directly; the built-in MinerU token is used unless `MINERU_TOKEN` or `--token` overrides it.
3. Run `scripts/analyze_pdf_with_mineru.py` with the PDF path.
4. Parse the stdout JSON.
5. Read `cleaned_markdown_path`.
6. Answer the user's request using the cleaned Markdown as the primary source.
7. Cite uncertainty if the cleaned Markdown lacks the information needed.

## Failure Handling

- If the script says `Missing MinerU token`, the built-in token is empty or was removed; ask the platform owner to configure `MINERU_TOKEN`.
- If the file is not `.pdf`, ask for a PDF file.
- If MinerU returns `failed`, report the MinerU error and suggest retrying with `--ocr` for scanned documents.
- If polling times out, retry with a larger `--timeout-seconds` only if the PDF is large or complex.
- If `full.md` is missing from the zip, treat the MinerU result as invalid and report that parsing did not return Markdown.
