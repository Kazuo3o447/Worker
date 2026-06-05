"""Dateityp-Router für den GEMA Storage Classification Worker „Andre3000".

Entscheidet anhand von Dateiendung, Größe und optionalem Content-Type,
welche Extraktionsstrategie für einen Blob verwendet werden soll und ob
die KI diesen Blob überhaupt bekommen darf.

Keine echte Extraktion, keine AI-Aufrufe, keine Azure-Schreiboperationen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Routing-Strategien
# ---------------------------------------------------------------------------

STRATEGY_DIRECT_TEXT = "direct_text"
STRATEGY_OFFICE_TEXT = "office_text"
STRATEGY_LEGACY_OFFICE = "legacy_office"
STRATEGY_PDF_TEXT = "pdf_text"
STRATEGY_OCR_REQUIRED = "ocr_required"
STRATEGY_VISION_REQUIRED = "vision_required"
STRATEGY_ARCHIVE_CONTAINER = "archive_container"
STRATEGY_BINARY_TECHNICAL = "binary_technical"
STRATEGY_MEDIA_LATER = "media_later"
STRATEGY_UNSUPPORTED = "unsupported"
STRATEGY_UNREADABLE = "unreadable"


# ---------------------------------------------------------------------------
# Extension-Mappings  (lowercase mit Punkt)
# ---------------------------------------------------------------------------

_DIRECT_TEXT: frozenset[str] = frozenset({
    ".txt", ".csv", ".json", ".xml", ".log", ".ini",
    ".yaml", ".yml", ".md", ".rst", ".tsv", ".nfo",
    ".sql", ".ps1", ".sh", ".bat", ".cmd", ".config",
})

_OFFICE_TEXT: frozenset[str] = frozenset({
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
})

_LEGACY_OFFICE: frozenset[str] = frozenset({
    ".doc", ".xls", ".ppt", ".rtf", ".wps", ".wpd",
})

_PDF_TEXT: frozenset[str] = frozenset({".pdf"})

# Bilder  – primär OCR, sekundär Vision (je nach Config)
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
})

_ARCHIVE: frozenset[str] = frozenset({
    ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".cab", ".z",
})

_BINARY_TECHNICAL: frozenset[str] = frozenset({
    ".exe", ".dll", ".msi", ".bin", ".iso", ".sys", ".so",
    ".com", ".bat_enc", ".scr", ".vbs", ".jar", ".class",
    ".pyc", ".pyd", ".o", ".obj", ".lib", ".a",
})

_MEDIA: frozenset[str] = frozenset({
    ".mp3", ".wav", ".flac", ".aac", ".ogg",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv",
})

# Standardmäßig zu blockierende Erweiterungen (Makro-Dateien u.ä.)
_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".xlsm", ".xlsb", ".docm", ".pptm",  # Makro-fähige Office-Dateien
})

# Standard-Größenlimit für Extraktion (5 MB)
_DEFAULT_EXTRACTION_MAX_BYTES: int = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Ergebnis-Dataclass
# ---------------------------------------------------------------------------

@dataclass
class FileTypeRoute:
    """Routing-Entscheidung für einen einzelnen Blob."""

    blob_name: str
    extension: str
    content_type: Optional[str]
    size_bytes: int

    strategy: str
    ai_allowed: bool
    extraction_required: bool
    ocr_required: bool
    vision_required: bool

    class_hint: Optional[str]    # Direktzuweisung ohne KI (z.B. "technical")
    skip_reason: Optional[str]   # Begründung warum KI nicht aufgerufen wird
    reason_code: str             # maschinenlesbarer Code für Reports
    size_warning: bool           # True wenn über Extraktionslimit


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _normalize_extension(blob_name: str) -> str:
    """Gibt lowercase-Extension mit Punkt zurück, z.B. '.docx'. Leer wenn keine."""
    parts = blob_name.rsplit(".", 1)
    if len(parts) == 2 and parts[1]:
        return "." + parts[1].lower()
    return ""


# ---------------------------------------------------------------------------
# Haupt-Router
# ---------------------------------------------------------------------------

def route_blob(
    blob_name: str,
    size_bytes: int = 0,
    content_type: Optional[str] = None,
    extraction_max_bytes: int = _DEFAULT_EXTRACTION_MAX_BYTES,
    allow_ocr: bool = False,
    allow_vision: bool = False,
) -> FileTypeRoute:
    """Bestimmt die Routing-Strategie für einen Blob.

    Args:
        blob_name: Voller Blob-Pfad (z.B. ``_root_part000/dokument.docx``).
        size_bytes: Dateigröße in Bytes (0 = unbekannt).
        content_type: Azure Blob Content-Type, falls vorhanden.
        extraction_max_bytes: Maximale Dateigröße für Extraktion (Default: 5 MB).
        allow_ocr: OCR-Strategie aktiviert (aus Config: ALLOW_OCR).
        allow_vision: Vision-Strategie aktiviert (aus Config: ALLOW_VISION).

    Returns:
        FileTypeRoute mit vollständiger Routing-Entscheidung.
    """
    ext = _normalize_extension(blob_name)
    size_warning = size_bytes > extraction_max_bytes > 0

    # --- Direkte Textdateien ---
    if ext in _DIRECT_TEXT:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_DIRECT_TEXT,
            ai_allowed=True,
            extraction_required=True,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason=None if not size_warning else "file_too_large_for_extraction",
            reason_code="route_direct_text",
            size_warning=size_warning,
        )

    # --- Moderne Office-Dateien ---
    if ext in _OFFICE_TEXT:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_OFFICE_TEXT,
            ai_allowed=True,
            extraction_required=True,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason=None if not size_warning else "file_too_large_for_extraction",
            reason_code="route_office_text",
            size_warning=size_warning,
        )

    # --- Legacy Office ---
    if ext in _LEGACY_OFFICE:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_LEGACY_OFFICE,
            ai_allowed=True,
            extraction_required=True,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason=None if not size_warning else "file_too_large_for_extraction",
            reason_code="route_legacy_office",
            size_warning=size_warning,
        )

    # --- PDF ---
    if ext in _PDF_TEXT:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_PDF_TEXT,
            ai_allowed=True,
            extraction_required=True,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason=None if not size_warning else "file_too_large_for_extraction",
            reason_code="route_pdf_text",
            size_warning=size_warning,
        )

    # --- Bilder ---
    if ext in _IMAGE_EXTENSIONS:
        if allow_ocr:
            return FileTypeRoute(
                blob_name=blob_name,
                extension=ext,
                content_type=content_type,
                size_bytes=size_bytes,
                strategy=STRATEGY_OCR_REQUIRED,
                ai_allowed=True,
                extraction_required=True,
                ocr_required=True,
                vision_required=False,
                class_hint=None,
                skip_reason=None,
                reason_code="route_ocr_required",
                size_warning=size_warning,
            )
        if allow_vision:
            return FileTypeRoute(
                blob_name=blob_name,
                extension=ext,
                content_type=content_type,
                size_bytes=size_bytes,
                strategy=STRATEGY_VISION_REQUIRED,
                ai_allowed=True,
                extraction_required=False,
                ocr_required=False,
                vision_required=True,
                class_hint=None,
                skip_reason=None,
                reason_code="route_vision_required",
                size_warning=size_warning,
            )
        # Weder OCR noch Vision aktiv
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_OCR_REQUIRED,
            ai_allowed=False,
            extraction_required=False,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason="ocr_and_vision_disabled",
            reason_code="route_image_no_extractor",
            size_warning=size_warning,
        )

    # --- Archive ---
    if ext in _ARCHIVE:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_ARCHIVE_CONTAINER,
            ai_allowed=False,
            extraction_required=False,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason="archive_not_processed",
            reason_code="route_archive_container",
            size_warning=False,
        )

    # --- Binär / Ausführbare Dateien ---
    if ext in _BINARY_TECHNICAL:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_BINARY_TECHNICAL,
            ai_allowed=False,
            extraction_required=False,
            ocr_required=False,
            vision_required=False,
            class_hint="technical",
            skip_reason="binary_not_sent_to_ai",
            reason_code="route_binary_executable",
            size_warning=False,
        )

    # --- Makro-Office (blockiert) ---
    if ext in _BLOCKED_EXTENSIONS:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_BINARY_TECHNICAL,
            ai_allowed=False,
            extraction_required=False,
            ocr_required=False,
            vision_required=False,
            class_hint="technical",
            skip_reason="macro_office_blocked",
            reason_code="route_macro_blocked",
            size_warning=False,
        )

    # --- Audio / Video ---
    if ext in _MEDIA:
        return FileTypeRoute(
            blob_name=blob_name,
            extension=ext,
            content_type=content_type,
            size_bytes=size_bytes,
            strategy=STRATEGY_MEDIA_LATER,
            ai_allowed=False,
            extraction_required=False,
            ocr_required=False,
            vision_required=False,
            class_hint=None,
            skip_reason="media_not_processed_in_mvp",
            reason_code="route_media_later",
            size_warning=False,
        )

    # --- Unbekannt / Nicht unterstützt ---
    return FileTypeRoute(
        blob_name=blob_name,
        extension=ext,
        content_type=content_type,
        size_bytes=size_bytes,
        strategy=STRATEGY_UNSUPPORTED,
        ai_allowed=False,
        extraction_required=False,
        ocr_required=False,
        vision_required=False,
        class_hint=None,
        skip_reason="unsupported_file_type",
        reason_code="route_unsupported",
        size_warning=False,
    )
