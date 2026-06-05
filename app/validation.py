"""Input validation for Blob Index Tags and Metadata.

Ensures all values written to Azure are within allowed ranges and comply
with Azure Blob Storage naming restrictions before any API calls are made.
"""

from __future__ import annotations

from typing import Callable

# ---------------------------------------------------------------------------
# Allowed value sets
# ---------------------------------------------------------------------------

ALLOWED_STATUS: frozenset[str] = frozenset({"new", "classified", "error", "unreadable", "skipped"})
ALLOWED_CLASS: frozenset[str] = frozenset(
    {"br", "dsgvo", "hr", "finance", "contract", "technical", "unknown", "unreadable"}
)
ALLOWED_BOOL: frozenset[str] = frozenset({"true", "false"})

# Azure limits
_TAG_MAX_KEY_LEN = 128
_TAG_MAX_VALUE_LEN = 256
_TAG_MAX_COUNT = 10
_METADATA_MAX_KEY_LEN = 256
_METADATA_MAX_VALUE_LEN = 8192


# ---------------------------------------------------------------------------
# Per-tag value validators
# ---------------------------------------------------------------------------

def validate_confidence(value: str) -> bool:
    """Return True if *value* is an integer string in range 0–100."""
    try:
        return 0 <= int(value) <= 100
    except (ValueError, TypeError):
        return False


_TAG_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "status": lambda v: v in ALLOWED_STATUS,
    "class": lambda v: v in ALLOWED_CLASS,
    "dsgvo": lambda v: v in ALLOWED_BOOL,
    "archive_candidate": lambda v: v in ALLOWED_BOOL,
    "readable": lambda v: v in ALLOWED_BOOL,
    "llm_used": lambda v: v in ALLOWED_BOOL,
    "confidence": validate_confidence,
    "needs_ai": lambda v: v in ALLOWED_BOOL,
}


# ---------------------------------------------------------------------------
# Tag validation
# ---------------------------------------------------------------------------

def validate_tags(tags: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Validate blob index tags.

    Returns ``(valid_tags, error_messages)``.
    Only valid tags are included in the returned dict.
    """
    errors: list[str] = []
    valid: dict[str, str] = {}

    if len(tags) > _TAG_MAX_COUNT:
        errors.append(f"Too many tags: {len(tags)} > {_TAG_MAX_COUNT}. Excess tags will be dropped.")

    for key, value in list(tags.items())[:_TAG_MAX_COUNT]:
        str_value = str(value)

        # Key rules
        if not key.isascii() or " " in key or not key:
            errors.append(f"Invalid tag key '{key}': must be non-empty ASCII without spaces")
            continue
        if len(key) > _TAG_MAX_KEY_LEN:
            errors.append(f"Tag key too long ('{key[:30]}...'): {len(key)} chars > {_TAG_MAX_KEY_LEN}")
            continue

        # Value length
        if len(str_value) > _TAG_MAX_VALUE_LEN:
            errors.append(
                f"Tag value too long for key '{key}': {len(str_value)} chars > {_TAG_MAX_VALUE_LEN}"
            )
            continue

        # Allowed values for known tags
        validator = _TAG_VALIDATORS.get(key)
        if validator is not None and not validator(str_value):
            errors.append(f"Invalid value for tag '{key}': '{str_value}'")
            continue

        valid[key] = str_value

    return valid, errors


# ---------------------------------------------------------------------------
# Metadata validation
# ---------------------------------------------------------------------------

def validate_metadata(metadata: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Validate blob metadata key/value pairs.

    Returns ``(valid_metadata, error_messages)``.
    Values are sanitised (non-printable chars stripped, truncated if needed).
    """
    errors: list[str] = []
    valid: dict[str, str] = {}

    for key, value in metadata.items():
        # Key: lowercase ASCII, no spaces
        if not key:
            errors.append("Empty metadata key skipped")
            continue
        if not key.isascii() or " " in key:
            errors.append(f"Invalid metadata key '{key}': must be ASCII without spaces")
            continue
        if key != key.lower():
            errors.append(f"Metadata key '{key}' must be lowercase – auto-correcting")
            key = key.lower()
        if len(key) > _METADATA_MAX_KEY_LEN:
            errors.append(f"Metadata key too long: '{key[:30]}...' ({len(key)} chars)")
            continue

        # Sanitise value
        str_value = str(value)
        sanitised = "".join(ch for ch in str_value if ch.isprintable())
        if len(sanitised) > _METADATA_MAX_VALUE_LEN:
            errors.append(f"Metadata value truncated for key '{key}'")
            sanitised = sanitised[:_METADATA_MAX_VALUE_LEN]

        valid[key] = sanitised

    return valid, errors
