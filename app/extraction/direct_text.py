"""Direct-text extractor for simple text-based formats.

Supported: .txt  .csv  .log  .md  .json  .xml  .yaml  .yml  .ini  .config
           and any other file routed as direct_text.

Security rules:
  - Only reads up to MAX_DOWNLOAD_BYTES
  - Stores ONLY metrics (char count, hash, encoding hint)
  - The _text_for_ai buffer in ExtractionResult is populated but never persisted
"""

from __future__ import annotations

import hashlib
from typing import Optional

from app.extraction.models import ExtractionResult
from app.extraction.safety import sanitize_error_message

# Maximum bytes to download for text extraction
MAX_DOWNLOAD_BYTES: int = 256 * 1024   # 256 KB

# Maximum characters to keep in the in-memory AI buffer
MAX_AI_CHARS: int = 4_000

# Supported encodings to try, in order
_ENCODINGS: list[str] = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

# Threshold: if more than this fraction of bytes are non-printable, treat as binary
_BINARY_THRESHOLD: float = 0.30


def extract(
    blob_name: str,
    content: bytes,
    max_ai_chars: int = MAX_AI_CHARS,
) -> ExtractionResult:
    """Extract metrics from raw text-file bytes.

    Args:
        blob_name:    Blob name (used for logging only, never stored in output).
        content:      Raw file bytes (already limited to MAX_DOWNLOAD_BYTES).
        max_ai_chars: Maximum chars to keep in the AI buffer.

    Returns:
        ExtractionResult – safe to store (to_safe_dict()).
        The _text_for_ai field is in-memory only.
    """
    if not content:
        return ExtractionResult(
            extractor_type="direct_text",
            extraction_status="not_readable",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code="empty_content",
            error_message_sanitized="No content received",
            needs_ai=False,
            ai_candidate_reason=None,
        )

    # Binary detection: check ratio of non-printable bytes
    null_bytes = content.count(b"\x00")
    non_print = sum(1 for b in content[:2048] if b < 9 or (13 < b < 32))
    sample_len = min(len(content), 2048)
    binary_ratio = (null_bytes + non_print) / max(sample_len, 1)

    if binary_ratio > _BINARY_THRESHOLD:
        return ExtractionResult(
            extractor_type="direct_text",
            extraction_status="binary_detected",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=hashlib.sha256(content).hexdigest(),
            language_hint=None,
            error_code="binary_detected",
            error_message_sanitized="File appears to be binary, not plain text",
            needs_ai=False,
            ai_candidate_reason=None,
        )

    # Try to decode
    decoded: Optional[str] = None
    used_encoding: str = "unknown"
    decode_error: str = ""

    for enc in _ENCODINGS:
        try:
            decoded = content.decode(enc)
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError) as exc:
            decode_error = str(exc)[:200]

    if decoded is None:
        return ExtractionResult(
            extractor_type="direct_text",
            extraction_status="encoding_error",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=hashlib.sha256(content).hexdigest(),
            language_hint=None,
            error_code="encoding_error",
            error_message_sanitized=sanitize_error_message(decode_error),
            needs_ai=True,
            ai_candidate_reason="text_not_decodable",
        )

    total_chars = len(decoded)
    ai_text = decoded[:max_ai_chars]

    # Language hint: detect simple patterns (German / English)
    lang_hint = _guess_language(decoded[:1000])

    return ExtractionResult(
        extractor_type="direct_text",
        extraction_status="ok",
        readable=True,
        text_available=True,
        text_chars_total=total_chars,
        text_chars_for_ai=len(ai_text),
        safe_preview_available=bool(ai_text),
        content_hash_sha256=hashlib.sha256(content).hexdigest(),
        language_hint=lang_hint,
        error_code=None,
        error_message_sanitized=None,
        needs_ai=True,   # always true for text files (content-based classification needed)
        ai_candidate_reason="text_content_available",
        _text_for_ai=ai_text,  # IN-MEMORY ONLY
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guess_language(sample: str) -> Optional[str]:
    """Very rough language hint based on character frequencies."""
    if not sample:
        return None
    german_chars = sum(1 for c in sample if c in "äöüÄÖÜß")
    if german_chars > 3:
        return "de"
    ascii_count = sum(1 for c in sample if ord(c) < 128)
    if ascii_count / max(len(sample), 1) > 0.95:
        return "en"
    return None
