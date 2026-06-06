"""Extraction Router – dispatches blobs to the correct extractor.

Uses ``FileTypeRoute.strategy`` (from app/file_type_router.py) to decide
which extractor handles each blob.

No Azure I/O here – the caller must supply raw content bytes.
"""

from __future__ import annotations

from typing import Optional

from app.extraction.models import ExtractionResult

# Strategy constants (must match app/file_type_router.py)
_STRATEGY_DIRECT_TEXT = "direct_text"
_STRATEGY_OFFICE_TEXT = "office_text"
_STRATEGY_LEGACY_OFFICE = "legacy_office"
_STRATEGY_PDF_TEXT = "pdf_text"
_STRATEGY_OCR_REQUIRED = "ocr_required"
_STRATEGY_VISION_REQUIRED = "vision_required"
_STRATEGY_ARCHIVE_CONTAINER = "archive_container"
_STRATEGY_BINARY_TECHNICAL = "binary_technical"
_STRATEGY_MEDIA_LATER = "media_later"
_STRATEGY_UNSUPPORTED = "unsupported"
_STRATEGY_UNREADABLE = "unreadable"


def route_and_extract(
    blob_name: str,
    strategy: str,
    content: Optional[bytes],
    ai_min_confidence: int = 60,
) -> ExtractionResult:
    """Dispatch *content* to the appropriate extractor based on *strategy*.

    Args:
        blob_name:          Name of the blob (for logging / ext detection).
        strategy:           FileTypeRoute.strategy value.
        content:            Raw blob bytes (None if download failed / not attempted).
        ai_min_confidence:  Confidence threshold from Config (unused in extraction phase,
                            reserved for future AI budget logic).

    Returns:
        ExtractionResult (safe to serialise via to_safe_dict()).
        The _text_for_ai field is populated in-memory for eligible files.
    """
    if content is None:
        return _download_failed_result(strategy)

    if strategy == _STRATEGY_DIRECT_TEXT:
        from app.extraction import direct_text as _dt  # noqa: PLC0415
        return _dt.extract(blob_name, content)

    if strategy in (_STRATEGY_LEGACY_OFFICE, _STRATEGY_OFFICE_TEXT):
        from app.extraction import legacy_office as _lo  # noqa: PLC0415
        return _lo.extract(blob_name, content)

    if strategy == _STRATEGY_PDF_TEXT:
        from app.extraction import pdf_extractor as _pdf  # noqa: PLC0415
        return _pdf.extract(blob_name, content)

    if strategy == _STRATEGY_OCR_REQUIRED:
        return ExtractionResult.unsupported("ocr")

    if strategy == _STRATEGY_VISION_REQUIRED:
        return ExtractionResult.unsupported("vision")

    if strategy == _STRATEGY_ARCHIVE_CONTAINER:
        return ExtractionResult(
            extractor_type="archive",
            extraction_status="skipped",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code="archive_not_extracted",
            error_message_sanitized="Archive files are not extracted in this phase",
            needs_ai=False,
            ai_candidate_reason=None,
        )

    if strategy == _STRATEGY_BINARY_TECHNICAL:
        return ExtractionResult(
            extractor_type="binary",
            extraction_status="skipped",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code="binary_technical_no_ai",
            error_message_sanitized="Binary/technical files are not passed to AI",
            needs_ai=False,
            ai_candidate_reason=None,
        )

    if strategy == _STRATEGY_MEDIA_LATER:
        return ExtractionResult.unsupported("media")

    if strategy in (_STRATEGY_UNSUPPORTED, _STRATEGY_UNREADABLE):
        return ExtractionResult.unsupported(strategy)

    # Unknown strategy
    return ExtractionResult.unsupported(f"unknown_strategy:{strategy}")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _download_failed_result(strategy: str) -> ExtractionResult:
    return ExtractionResult(
        extractor_type=strategy or "unknown",
        extraction_status="download_failed",
        readable=False,
        text_available=False,
        text_chars_total=0,
        text_chars_for_ai=0,
        safe_preview_available=False,
        content_hash_sha256=None,
        language_hint=None,
        error_code="download_failed",
        error_message_sanitized="Blob content could not be downloaded",
        needs_ai=True,
        ai_candidate_reason="download_failed_retry_needed",
    )
