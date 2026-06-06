"""Rule-based blob classification for pilot v0.

No content download – classification is based purely on blob path/name.
Extend this module later to add LLM-backed classification without touching
the rest of the worker.
"""

from __future__ import annotations

from app.models import RuleResult

# ---------------------------------------------------------------------------
# Rule table – evaluated in order; first match wins.
# Each entry: (keywords, class_label, dsgvo, archive_candidate, confidence, reason_code)
# ---------------------------------------------------------------------------
_PATH_RULES: list[tuple[list[str], str, str, str, str, str]] = [
    (
        ["betriebsrat", "br_", "/br/"],
        "br", "true", "true", "90", "path_rule_betriebsrat",
    ),
    (
        ["dsgvo", "datenschutz"],
        "dsgvo", "true", "true", "85", "path_rule_dsgvo",
    ),
    (
        ["personal", "/hr/", "human resources"],
        "hr", "true", "true", "80", "path_rule_hr",
    ),
    (
        ["rechnung", "finanz", "buchhaltung", "invoice"],
        "finance", "false", "true", "80", "path_rule_finance",
    ),
    (
        ["vertrag", "vereinbarung", "contract"],
        "contract", "false", "true", "75", "path_rule_contract",
    ),
]

_TECHNICAL_EXTENSIONS: frozenset[str] = frozenset(
    {".ps1", ".json", ".xml", ".config", ".sql", ".log", ".ini", ".yaml", ".yml"}
)

# Statuses that can be re-processed without --force
_RETRY_STATUSES: frozenset[str] = frozenset({"new", "error", "", "pending_ai"})

# Statuses that are considered final (skip without --force)
_SKIP_STATUSES: frozenset[str] = frozenset({"classified", "skipped", "unreadable"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_blob(blob_name: str) -> RuleResult:
    """Return a RuleResult for *blob_name* using path/extension rules only.

    No network calls, no content access.
    """
    name_lower = blob_name.lower()

    for keywords, class_label, dsgvo, archive_candidate, confidence, reason_code in _PATH_RULES:
        for kw in keywords:
            if kw in name_lower:
                return RuleResult(
                    class_label=class_label,
                    dsgvo=dsgvo,
                    archive_candidate=archive_candidate,
                    confidence=confidence,
                    reason_code=reason_code,
                )

    ext = _get_extension(blob_name)
    if ext in _TECHNICAL_EXTENSIONS:
        return RuleResult(
            class_label="technical",
            dsgvo="false",
            archive_candidate="true",
            confidence="70",
            reason_code="extension_rule_technical",
        )

    return RuleResult(
        class_label="unknown",
        dsgvo="false",
        archive_candidate="false",
        confidence="30",
        reason_code="no_rule_match",
    )


def should_process_blob(
    existing_tags: dict[str, str],
    force: bool = False,
) -> tuple[bool, str]:
    """Decide whether a blob needs processing.

    Returns ``(should_process, reason_string)``.

    Rules:
    - No status tag  → process (reason: status=none)
    - status=new     → process
    - status=error   → process (retry)
    - status=classified / skipped / unreadable → skip, unless ``force=True``
    """
    status = existing_tags.get("status", "")

    if status in _RETRY_STATUSES:
        return True, f"status={status or 'none'}"

    if force:
        return True, f"force=true,status={status}"

    # classified + needs_ai=true → allow AI retry without --force
    if status == "classified" and existing_tags.get("needs_ai") == "true":
        return True, "status=classified,needs_ai=true"

    if status in _SKIP_STATUSES:
        return False, f"status={status}"

    # Unknown status → process to be safe
    return True, f"status_unknown={status}"


# ---------------------------------------------------------------------------
# Internal helpers (also used by azure_storage and tests)
# ---------------------------------------------------------------------------

def _get_extension(blob_name: str) -> str:
    """Return lowercase file extension with leading dot, or '' if none."""
    parts = blob_name.rsplit(".", 1)
    if len(parts) == 2 and parts[1]:
        return "." + parts[1].lower()
    return ""
