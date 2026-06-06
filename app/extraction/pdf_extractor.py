"""PDF text extractor using PyMuPDF (fitz).

Extracts digital text from PDF files in-memory.
Scanned-only PDFs (no embedded text) are reported as no_text_found.
Encrypted PDFs are detected and reported as encrypted.

Security rules:
  - No file I/O; PDF is opened from bytes in memory
  - _text_for_ai is in-memory only, never persisted
  - Max chars capped at max_ai_chars
  - Max pages capped at pdf_max_pages
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Optional

from app.extraction.models import ExtractionResult
from app.extraction.safety import sanitize_error_message

MAX_AI_CHARS: int = 4_000
PDF_MAX_PAGES: int = 3


def extract(
    blob_name: str,
    content: bytes,
    max_ai_chars: int = MAX_AI_CHARS,
    pdf_max_pages: int = PDF_MAX_PAGES,
) -> ExtractionResult:
    """Extract text from PDF bytes using PyMuPDF.

    Args:
        blob_name:      Name of the blob (for logging).
        content:        Raw PDF bytes.
        max_ai_chars:   Character cap for AI input.
        pdf_max_pages:  Maximum pages to sample.

    Returns:
        ExtractionResult with extraction_method="pymupdf".
    """
    t0 = time.monotonic()
    content_hash = hashlib.sha256(content).hexdigest()

    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return ExtractionResult(
            extractor_type="pdf",
            extraction_status="tool_missing",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=content_hash,
            language_hint=None,
            error_code="tool_missing",
            error_message_sanitized="PyMuPDF (fitz) not installed",
            needs_ai=False,
            ai_candidate_reason=None,
            extraction_method="pymupdf",
            extraction_duration_ms=duration_ms,
        )

    if not content:
        return _make_error(content_hash, "empty_content", "Empty PDF content", t0)

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        err = sanitize_error_message(str(exc))
        return _make_error(content_hash, "open_failed", err, t0)

    try:
        # Check encryption
        if doc.is_encrypted:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return ExtractionResult(
                extractor_type="pdf",
                extraction_status="encrypted",
                readable=False,
                text_available=False,
                text_chars_total=0,
                text_chars_for_ai=0,
                safe_preview_available=False,
                content_hash_sha256=content_hash,
                language_hint=None,
                error_code="encrypted",
                error_message_sanitized="PDF is encrypted and cannot be read without a password",
                needs_ai=False,
                ai_candidate_reason=None,
                extraction_method="pymupdf",
                pages_total=doc.page_count,
                pages_sampled=0,
                extraction_duration_ms=duration_ms,
            )

        pages_total = doc.page_count
        pages_to_sample = min(pages_total, pdf_max_pages)
        text_parts: list[str] = []

        for page_num in range(pages_to_sample):
            try:
                page = doc.load_page(page_num)
                page_text = page.get_text()  # type: ignore[attr-defined]
                if page_text and page_text.strip():
                    text_parts.append(page_text.strip())
            except Exception:  # noqa: BLE001
                continue

        duration_ms = int((time.monotonic() - t0) * 1000)
        combined = re.sub(r"\s+", " ", " ".join(text_parts)).strip()

        if not combined:
            return ExtractionResult(
                extractor_type="pdf",
                extraction_status="no_text_found",
                readable=False,
                text_available=False,
                text_chars_total=0,
                text_chars_for_ai=0,
                safe_preview_available=False,
                content_hash_sha256=content_hash,
                language_hint=None,
                error_code="no_text_found",
                error_message_sanitized="PDF contains no extractable text (likely scanned/image-only)",
                needs_ai=False,
                ai_candidate_reason=None,
                extraction_method="pymupdf",
                pages_total=pages_total,
                pages_sampled=pages_to_sample,
                extraction_duration_ms=duration_ms,
            )

        total_chars = len(combined)
        ai_text = combined[:max_ai_chars]
        lang_hint = _guess_language(combined[:1000])

        return ExtractionResult(
            extractor_type="pdf",
            extraction_status="success",
            readable=True,
            text_available=True,
            text_chars_total=total_chars,
            text_chars_for_ai=len(ai_text),
            safe_preview_available=bool(ai_text),
            content_hash_sha256=content_hash,
            language_hint=lang_hint,
            error_code=None,
            error_message_sanitized=None,
            needs_ai=True,
            ai_candidate_reason="pdf_text_available",
            extraction_method="pymupdf",
            pages_total=pages_total,
            pages_sampled=pages_to_sample,
            extraction_duration_ms=duration_ms,
            _text_for_ai=ai_text,  # IN-MEMORY ONLY
        )

    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_error(
    content_hash: str,
    error_code: str,
    error_msg: str,
    t0: float,
) -> ExtractionResult:
    duration_ms = int((time.monotonic() - t0) * 1000)
    return ExtractionResult(
        extractor_type="pdf",
        extraction_status="failure",
        readable=False,
        text_available=False,
        text_chars_total=0,
        text_chars_for_ai=0,
        safe_preview_available=False,
        content_hash_sha256=content_hash,
        language_hint=None,
        error_code=error_code,
        error_message_sanitized=error_msg[:500],
        needs_ai=False,
        ai_candidate_reason=None,
        extraction_method="pymupdf",
        extraction_duration_ms=duration_ms,
    )


def _guess_language(sample: str) -> Optional[str]:
    if not sample:
        return None
    german_chars = sum(1 for c in sample if c in "äöüÄÖÜß")
    if german_chars > 3:
        return "de"
    return "en" if sample else None
