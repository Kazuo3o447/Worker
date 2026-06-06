"""Legacy Office extractor for .docx and .doc files.

.docx: Uses Python's built-in zipfile to parse the Open XML format.
       (No python-docx dependency required; falls back gracefully.)
.doc:  Binary Word 97-2003 format – extracted via antiword subprocess.
       Falls back gracefully if antiword is not installed (tool_missing).

Security rules:
  - Only reads up to MAX_DOWNLOAD_BYTES
  - Stores ONLY metrics (char count, hash)
  - _text_for_ai is in-memory only, never persisted
  - No shell=True; subprocess called with argument list
  - Tempfile deleted after use
  - No file execution
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tempfile
import time
import zipfile
from typing import Optional

from app.extraction.models import ExtractionResult
from app.extraction.safety import sanitize_error_message

MAX_DOWNLOAD_BYTES: int = 512 * 1024   # 512 KB for office files
MAX_AI_CHARS: int = 4_000
ANTIWORD_TIMEOUT: int = 10  # seconds

# Simple XML tag stripper
_XML_TAG_RE = re.compile(r"<[^>]+>")


def extract(
    blob_name: str,
    content: bytes,
    max_ai_chars: int = MAX_AI_CHARS,
) -> ExtractionResult:
    """Extract text metrics from Office file bytes.

    .docx  – parses the embedded XML via zipfile
    .doc   – returns legacy_doc_not_supported
    """
    ext = _get_ext(blob_name)

    if ext == ".doc":
        return _extract_doc_antiword(blob_name, content, max_ai_chars)

    if ext == ".docx":
        return _extract_docx(blob_name, content, max_ai_chars)

    # Fallback for other office formats (e.g. .pptx, .xlsx via legacy_office route)
    if ext in (".pptx", ".xlsx", ".odp", ".ods", ".odt"):
        return _extract_docx(blob_name, content, max_ai_chars)  # XML-based, same approach

    return ExtractionResult.unsupported("legacy_office")


# ---------------------------------------------------------------------------
# .docx / Open XML extraction
# ---------------------------------------------------------------------------

def _extract_docx(
    blob_name: str,
    content: bytes,
    max_ai_chars: int,
) -> ExtractionResult:
    """Extract plain text from an Open XML (ZIP-based) Office file."""
    if not content:
        return _error_result("empty_content", "No content received")

    content_hash = hashlib.sha256(content).hexdigest()

    # Verify it is a valid ZIP
    if not content[:4] == b"PK\x03\x04":
        return _error_result(
            "not_a_zip",
            "File does not start with ZIP magic bytes (PK) – may be corrupted or password-protected",
            content_hash=content_hash,
        )

    text_parts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            names = zf.namelist()
            # Find XML entry points for different Office formats
            candidates = _find_xml_candidates(names)
            for name in candidates[:10]:   # cap to avoid zip bombs
                try:
                    raw_xml = zf.read(name).decode("utf-8", errors="replace")
                    text = _strip_xml_tags(raw_xml)
                    if text.strip():
                        text_parts.append(text.strip())
                except Exception:  # noqa: BLE001
                    continue
    except zipfile.BadZipFile as exc:
        err = sanitize_error_message(str(exc))
        return _error_result("bad_zip", err, content_hash=content_hash)
    except Exception as exc:  # noqa: BLE001
        err = sanitize_error_message(str(exc))
        return _error_result("extraction_error", err, content_hash=content_hash)

    combined = " ".join(text_parts)
    combined = re.sub(r"\s+", " ", combined).strip()

    if not combined:
        return ExtractionResult(
            extractor_type="legacy_office",
            extraction_status="not_readable",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=content_hash,
            language_hint=None,
            error_code="no_text_extracted",
            error_message_sanitized="No readable text found in document",
            needs_ai=True,
            ai_candidate_reason="no_text_in_document",
        )

    total_chars = len(combined)
    ai_text = combined[:max_ai_chars]
    lang_hint = _guess_language(combined[:1000])

    return ExtractionResult(
        extractor_type="legacy_office",
        extraction_status="ok",
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
        ai_candidate_reason="office_text_available",
        _text_for_ai=ai_text,  # IN-MEMORY ONLY
    )


# ---------------------------------------------------------------------------
# .doc / antiword extraction
# ---------------------------------------------------------------------------

def _extract_doc_antiword(
    blob_name: str,
    content: bytes,
    max_ai_chars: int,
) -> ExtractionResult:
    """Extract plain text from binary Word 97-2003 (.doc) via antiword.

    Security:
      - No shell=True
      - Tempfile deleted in finally-block
      - Only stdout used as text
      - Subprocess timeout enforced
    """
    t0 = time.monotonic()
    content_hash = hashlib.sha256(content).hexdigest()

    # Check antiword availability before writing tempfile
    import shutil
    if not shutil.which("antiword"):
        return ExtractionResult(
            extractor_type="legacy_office",
            extraction_status="tool_missing",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=content_hash,
            language_hint=None,
            error_code="tool_missing",
            error_message_sanitized="antiword not found in PATH",
            needs_ai=False,
            ai_candidate_reason=None,
            extraction_method="antiword",
            extraction_duration_ms=int((time.monotonic() - t0) * 1000),
        )

    tmp_path: Optional[str] = None
    try:
        # Write blob bytes to a named tempfile (antiword needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = subprocess.run(
            ["antiword", tmp_path],  # no shell=True
            capture_output=True,
            timeout=ANTIWORD_TIMEOUT,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        text = result.stdout.decode("utf-8", errors="replace").strip()

        if not text:
            return ExtractionResult(
                extractor_type="legacy_office",
                extraction_status="no_text_found",
                readable=False,
                text_available=False,
                text_chars_total=0,
                text_chars_for_ai=0,
                safe_preview_available=False,
                content_hash_sha256=content_hash,
                language_hint=None,
                error_code="no_text_found",
                error_message_sanitized="antiword returned no text",
                needs_ai=False,
                ai_candidate_reason=None,
                extraction_method="antiword",
                extraction_duration_ms=duration_ms,
            )

        total_chars = len(text)
        ai_text = text[:max_ai_chars]
        lang_hint = _guess_language(text[:1000])

        return ExtractionResult(
            extractor_type="legacy_office",
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
            ai_candidate_reason="doc_text_available",
            extraction_method="antiword",
            extraction_duration_ms=duration_ms,
            _text_for_ai=ai_text,  # IN-MEMORY ONLY
        )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return ExtractionResult(
            extractor_type="legacy_office",
            extraction_status="timeout",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=content_hash,
            language_hint=None,
            error_code="timeout",
            error_message_sanitized=f"antiword timed out after {ANTIWORD_TIMEOUT}s",
            needs_ai=False,
            ai_candidate_reason=None,
            extraction_method="antiword",
            extraction_duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - t0) * 1000)
        err = sanitize_error_message(str(exc))
        return ExtractionResult(
            extractor_type="legacy_office",
            extraction_status="failure",
            readable=False,
            text_available=False,
            text_chars_total=0,
            text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256=content_hash,
            language_hint=None,
            error_code="antiword_error",
            error_message_sanitized=err[:500],
            needs_ai=False,
            ai_candidate_reason=None,
            extraction_method="antiword",
            extraction_duration_ms=duration_ms,
        )
    finally:
        if tmp_path:
            import os as _os
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_xml_candidates(names: list[str]) -> list[str]:
    """Return XML entry names that likely contain document text."""
    priority: list[str] = []
    rest: list[str] = []
    for n in names:
        nl = n.lower()
        if nl.endswith(".xml"):
            if "word/document" in nl or "word/document.xml" == nl:
                priority.insert(0, n)
            elif any(k in nl for k in ("content", "document", "slide", "sheet", "body")):
                priority.append(n)
            else:
                rest.append(n)
    return priority + rest


def _strip_xml_tags(xml_text: str) -> str:
    """Remove all XML tags, leaving only text content."""
    return _XML_TAG_RE.sub(" ", xml_text)


def _error_result(
    error_code: str,
    error_msg: str,
    content_hash: Optional[str] = None,
) -> ExtractionResult:
    return ExtractionResult(
        extractor_type="legacy_office",
        extraction_status="error",
        readable=False,
        text_available=False,
        text_chars_total=0,
        text_chars_for_ai=0,
        safe_preview_available=False,
        content_hash_sha256=content_hash,
        language_hint=None,
        error_code=error_code,
        error_message_sanitized=error_msg[:500],
        needs_ai=True,
        ai_candidate_reason="extraction_failed",
    )


def _get_ext(blob_name: str) -> str:
    parts = blob_name.rsplit(".", 1)
    if len(parts) == 2 and parts[1]:
        return "." + parts[1].lower()
    return ""


def _guess_language(sample: str) -> Optional[str]:
    if not sample:
        return None
    german_chars = sum(1 for c in sample if c in "äöüÄÖÜß")
    if german_chars > 3:
        return "de"
    return "en" if sample else None
