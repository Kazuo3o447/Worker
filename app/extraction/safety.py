"""Safety layer – protects against accidental raw text persistence.

Rules enforced:
  1. No forbidden field names (raw_text, full_text, extracted_text, etc.)
     may appear in any dict that is about to be serialised.
  2. No string value longer than MAX_SAFE_FIELD_LEN characters is allowed
     in a serialised report field.
  3. Error messages are sanitised to remove file-path information and
     potential credential fragments.

Usage:
    from app.extraction.safety import assert_no_raw_text, sanitize_error_message

    safe_dict = result.to_safe_dict()
    assert_no_raw_text(safe_dict)            # raises if forbidden content found
    err = sanitize_error_message(raw_error)  # always call before persisting
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Field names that must NEVER appear in any serialised output
FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset({
    "raw_text",
    "full_text",
    "extracted_text",
    "content_text",
    "preview_text",
    "text",          # standalone "text" key is dangerous
    "page_text",
    "body_text",
    "document_text",
    "ocr_text",
    "vision_text",
    "file_content",
    "blob_content",
})

# Maximum characters allowed in a single string-valued report field
MAX_SAFE_FIELD_LEN: int = 2000

# Regex patterns for sensitive content in error messages
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),       # Base64-like (tokens, keys)
    re.compile(r"sk-[A-Za-z0-9]{20,}"),             # OpenAI-style keys
    re.compile(r"(password|secret|token|key)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"https?://[^\s]{80,}"),              # Very long URLs (may embed tokens)
]

# Path separators – strip Windows/Unix absolute paths from error messages
_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s\"']+|/(?:home|tmp|usr|var|app|data)/[^\s\"']+")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class RawTextPersistenceError(ValueError):
    """Raised when forbidden raw-text content is detected before serialisation."""


def assert_no_raw_text(data: Any, _path: str = "") -> None:
    """Recursively verify *data* contains no forbidden fields or oversized strings.

    Raises ``RawTextPersistenceError`` on the first violation found.

    Args:
        data:   The value to inspect (dict, list, str, or scalar).
        _path:  Internal path string for error messages (do not pass manually).
    """
    if isinstance(data, dict):
        for key, value in data.items():
            child_path = f"{_path}.{key}" if _path else key
            if key.lower() in FORBIDDEN_FIELD_NAMES:
                raise RawTextPersistenceError(
                    f"Forbidden field '{child_path}' detected – raw text must not be persisted."
                )
            assert_no_raw_text(value, child_path)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            assert_no_raw_text(item, f"{_path}[{i}]")

    elif isinstance(data, str):
        if len(data) > MAX_SAFE_FIELD_LEN:
            raise RawTextPersistenceError(
                f"Field '{_path}' value is too long ({len(data)} chars > {MAX_SAFE_FIELD_LEN}). "
                "Raw file content must not be persisted."
            )


def sanitize_error_message(message: str, max_len: int = 500) -> str:
    """Return a sanitised version of *message* safe to store in reports.

    Removes:
    - Absolute file-system paths
    - Base64 blobs, API keys, and tokens
    - Very long URLs that might embed credentials

    Truncates to *max_len* characters.
    """
    if not message:
        return ""

    sanitized = _PATH_PATTERN.sub("[PATH]", message)
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)

    # Truncate
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len] + "...[truncated]"

    return sanitized


def check_report_bytes(data: bytes, forbidden_markers: list[str] | None = None) -> list[str]:
    """Scan raw report bytes for forbidden markers.

    Returns a list of violations (empty list = safe).

    Use in tests to ensure no content from test files leaks into reports.
    """
    violations: list[str] = []
    text = data.decode("utf-8", errors="replace")

    # Forbidden field names
    for field in FORBIDDEN_FIELD_NAMES:
        # Look for JSON key patterns: "field":
        if f'"{field}"' in text or f"'{field}'" in text:
            violations.append(f"Forbidden field name '{field}' found in report bytes")

    # Custom markers (e.g. test sentinel strings)
    for marker in (forbidden_markers or []):
        if marker in text:
            violations.append(f"Forbidden marker '{marker[:60]}' found in report bytes")

    return violations
