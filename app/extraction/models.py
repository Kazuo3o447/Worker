"""Extraction result model.

SECURITY RULE:
  The in-memory text buffer (_text_for_ai) is NEVER serialized to disk,
  Azure, logs, or any report.  Use to_safe_dict() for all external output.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExtractionResult:
    """Safe, serialisable result of one extraction attempt.

    The field ``_text_for_ai`` lives in-memory only.
    It is NOT included in to_safe_dict() and must never be persisted.
    """

    extractor_type: str          # direct_text | legacy_office | antiword | pymupdf | unsupported | binary | error
    extraction_status: str       # success | ok | not_readable | binary_detected | legacy_doc_not_supported
                                 # | no_text_found | encrypted | tool_missing | timeout
                                 # | size_limit_exceeded | encoding_error | error | skipped | not_implemented
    readable: bool
    text_available: bool
    text_chars_total: int        # total chars in source (0 if unreadable)
    text_chars_for_ai: int       # how many chars prepared for AI (0 if AI not planned)
    safe_preview_available: bool # True if _text_for_ai is populated (in-memory only)
    content_hash_sha256: Optional[str]
    language_hint: Optional[str]
    error_code: Optional[str]
    error_message_sanitized: Optional[str]
    needs_ai: bool
    ai_candidate_reason: Optional[str]
    # New extraction detail fields
    extraction_method: str = ""      # antiword | pymupdf | zipfile | direct | none
    pages_total: int = 0             # PDF only: total page count
    pages_sampled: int = 0           # PDF only: pages actually sampled
    extraction_duration_ms: int = 0  # wall-clock ms for extraction

    # ------------------------------------------------------------------ #
    #  IN-MEMORY ONLY – NEVER serialized to reports/logs/metadata/tags    #
    # ------------------------------------------------------------------ #
    _text_for_ai: str = field(default="", repr=False, compare=False)

    # ------------------------------------------------------------------
    # Serialisation (safe)
    # ------------------------------------------------------------------

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a dict that is safe to persist.

        The ``_text_for_ai`` buffer is deliberately excluded.
        """
        return {
            "extractor_type": self.extractor_type,
            "extraction_status": self.extraction_status,
            "readable": self.readable,
            "text_available": self.text_available,
            "text_chars_total": self.text_chars_total,
            "text_chars_for_ai": self.text_chars_for_ai,
            "safe_preview_available": self.safe_preview_available,
            "content_hash_sha256": self.content_hash_sha256,
            "language_hint": self.language_hint,
            "error_code": self.error_code,
            "error_message_sanitized": self.error_message_sanitized,
            "needs_ai": self.needs_ai,
            "ai_candidate_reason": self.ai_candidate_reason,
            "extraction_method": self.extraction_method,
            "pages_total": self.pages_total,
            "pages_sampled": self.pages_sampled,
            "extraction_duration_ms": self.extraction_duration_ms,
        }

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def unsupported(cls, extractor_type: str = "unsupported") -> "ExtractionResult":
        return cls(
            extractor_type=extractor_type,
            extraction_status="unsupported",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code="unsupported_type",
            error_message_sanitized="File type not supported for extraction in this phase",
            needs_ai=False,
            ai_candidate_reason=None,
        )

    @classmethod
    def legacy_doc_not_supported(cls) -> "ExtractionResult":
        return cls(
            extractor_type="legacy_office",
            extraction_status="legacy_doc_not_supported",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code="legacy_doc_not_supported",
            error_message_sanitized=(
                ".doc (binary Word 97-2003) requires LibreOffice or antiword "
                "which are not available in this environment"
            ),
            needs_ai=True,
            ai_candidate_reason="legacy_doc_content_inaccessible",
        )

    @classmethod
    def skipped(cls, reason: str = "not_eligible") -> "ExtractionResult":
        return cls(
            extractor_type="skipped",
            extraction_status="skipped",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code=None,
            error_message_sanitized=None,
            needs_ai=False,
            ai_candidate_reason=reason,
        )


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
