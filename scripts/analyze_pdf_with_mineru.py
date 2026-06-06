#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


BASE_URL = "https://mineru.net/api/v4"
DEFAULT_MODEL_VERSION = "vlm"
DEFAULT_LANGUAGE = "ch"
DEFAULT_MINERU_TOKEN = "your token"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_headers(token: str, include_json: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
    }
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


def http_json(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = None
    headers = build_headers(token, include_json=payload is not None)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(url=url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_bytes(url: str) -> bytes:
    request = Request(url=url, method="GET")
    with urlopen(request, timeout=300) as response:
        return response.read()


def http_put_file(url: str, file_path: Path) -> int:
    parts = urlsplit(url)
    connection_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    request_path = parts.path if not parts.query else f"{parts.path}?{parts.query}"

    connection = connection_cls(parts.netloc, timeout=300)
    try:
        with file_path.open("rb") as file_obj:
            connection.putrequest("PUT", request_path)
            connection.putheader("Content-Length", str(file_path.stat().st_size))
            connection.endheaders()

            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break
                connection.send(chunk)

        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def build_data_id(file_path: Path, max_length: int = 128) -> str:
    stem = file_path.stem
    if len(stem) <= max_length:
        return stem
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()
    return digest[:max_length]


def request_upload_url(
    file_path: Path,
    token: str,
    model_version: str,
    language: str,
    enable_table: bool,
    enable_formula: bool,
    is_ocr: bool,
) -> tuple[str, str]:
    payload = {
        "files": [
            {
                "name": file_path.name,
                "data_id": build_data_id(file_path),
            }
        ],
        "model_version": model_version,
        "language": language,
        "enable_table": enable_table,
        "is_ocr": is_ocr,
        "enable_formula": enable_formula,
    }
    result = http_json("POST", f"{BASE_URL}/file-urls/batch", token=token, payload=payload)
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to request MinerU upload URL: {result}")

    data = result["data"]
    return data["batch_id"], data["file_urls"][0]


def poll_full_zip_url(batch_id: str, token: str, timeout_seconds: int, interval_seconds: int) -> str:
    started_at = time.time()

    while time.time() - started_at < timeout_seconds:
        result = http_json("GET", f"{BASE_URL}/extract-results/batch/{batch_id}", token=token)
        if result.get("code") != 0:
            raise RuntimeError(f"Failed to query MinerU result: {result}")

        extract_result = result["data"]["extract_result"][0]
        state = extract_result["state"]
        elapsed = int(time.time() - started_at)
        log(f"[{elapsed:>4}s] MinerU state={state}")

        if state == "done":
            return extract_result["full_zip_url"]
        if state == "failed":
            raise RuntimeError(f"MinerU extraction failed: {extract_result.get('err_msg', 'unknown error')}")

        time.sleep(interval_seconds)

    raise TimeoutError(f"Polling timed out for batch_id={batch_id}")


def extract_raw_markdown(zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member_name in archive.namelist():
            if member_name.endswith("/full.md") or member_name == "full.md":
                return archive.read(member_name).decode("utf-8")
    raise RuntimeError("Could not find full.md in MinerU result zip")


def clean_markdown_text(markdown_text: str) -> str:
    cleaned_lines: list[str] = []
    previous_blank = False

    for line in markdown_text.splitlines():
        if line.strip():
            cleaned_lines.append(line.rstrip())
            previous_blank = False
            continue
        if not previous_blank:
            cleaned_lines.append("")
            previous_blank = True

    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    return "\n".join(cleaned_lines) + "\n"


def default_output_dir(pdf_path: Path) -> Path:
    """
    FIX: Use short hash for directory name to avoid Windows path length limit.
    Old behavior: <cwd>/mineru-output/<pdf_stem>-<hash8>  (can exceed 260 chars)
    New behavior: <cwd>/mineru-output/<hash8>  (short and safe)
    """
    digest = hashlib.sha256(str(pdf_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return Path.cwd() / "mineru-output" / digest


def analyze_pdf(args: argparse.Namespace) -> dict[str, str | int | bool]:
    pdf_path = args.pdf_path.expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Only .pdf files are supported: {pdf_path}")

    token = args.token or os.getenv("MINERU_TOKEN") or DEFAULT_MINERU_TOKEN
    if not token:
        raise RuntimeError("Missing MinerU token. Set MINERU_TOKEN, pass --token, or set DEFAULT_MINERU_TOKEN.")

    log(f"Requesting MinerU upload URL for: {pdf_path.name}")
    batch_id, upload_url = request_upload_url(
        file_path=pdf_path,
        token=token,
        model_version=args.model_version,
        language=args.language,
        enable_table=not args.disable_table,
        enable_formula=not args.disable_formula,
        is_ocr=args.ocr,
    )
    log(f"batch_id={batch_id}")

    log("Uploading PDF to MinerU...")
    status_code = http_put_file(upload_url, pdf_path)
    if status_code not in (200, 201):
        raise RuntimeError(f"MinerU upload failed with HTTP {status_code}")

    log("Upload complete, polling MinerU...")
    full_zip_url = poll_full_zip_url(
        batch_id=batch_id,
        token=token,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )

    log("Downloading MinerU result zip...")
    zip_bytes = http_get_bytes(full_zip_url)
    raw_markdown = extract_raw_markdown(zip_bytes)
    cleaned_markdown = clean_markdown_text(raw_markdown)

    # Set up output directory (use short name to avoid Windows path length limit)
    output_dir = (args.output_dir.expanduser().resolve() if args.output_dir else default_output_dir(pdf_path))
    output_dir.mkdir(parents=True, exist_ok=True)

    # FIX: Use batch_id for filenames instead of pdf_path.stem
    # This avoids Windows path length limit (260 chars) for long PDF names
    raw_md_path = output_dir / f"{batch_id}.md"
    cleaned_md_path = output_dir / f"{batch_id}.cleaned.md"
    metadata_path = output_dir / "metadata.json"

    log(f"Writing output files to: {output_dir}")
    raw_md_path.write_text(raw_markdown, encoding="utf-8")
    cleaned_md_path.write_text(cleaned_markdown, encoding="utf-8")

    metadata: dict[str, str | int | bool] = {
        "pdf_path": str(pdf_path),
        "output_dir": str(output_dir),
        "raw_markdown_path": str(raw_md_path),
        "cleaned_markdown_path": str(cleaned_md_path),
        "metadata_path": str(metadata_path),
        "batch_id": batch_id,
        "model_version": args.model_version,
        "language": args.language,
        "enable_table": not args.disable_table,
        "enable_formula": not args.disable_formula,
        "is_ocr": args.ocr,
        "pdf_size": pdf_path.stat().st_size,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze a PDF with MinerU and produce raw/cleaned Markdown for Agent document QA."
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the user-uploaded PDF.")
    parser.add_argument("-o", "--output-dir", type=Path, help="Directory for raw Markdown, cleaned Markdown, and metadata.")
    parser.add_argument("--token", help="Override the built-in MinerU API token.")
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION, help="MinerU model version. Default: vlm.")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="MinerU document language. Default: ch.")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR mode for scanned PDFs.")
    parser.add_argument("--disable-table", action="store_true", help="Disable table extraction.")
    parser.add_argument("--disable-formula", action="store_true", help="Disable formula extraction.")
    parser.add_argument("--timeout-seconds", type=int, default=3600, help="Polling timeout. Default: 3600.")
    parser.add_argument("--interval-seconds", type=int, default=5, help="Polling interval. Default: 5.")
    return parser


def main() -> int:
    # FIX: Configure stderr/stdout encoding for Windows compatibility
    try:
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass  # Not all Python versions/platforms support this

    parser = build_parser()
    args = parser.parse_args()

    try:
        metadata = analyze_pdf(args)
    except (HTTPError, URLError) as exc:
        log(f"Network error: {exc}")
        return 1
    except Exception as exc:
        log(f"Error: {exc}")
        return 1

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
