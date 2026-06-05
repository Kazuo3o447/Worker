"""Tests für den Dateityp-Router (app/file_type_router.py)."""

from __future__ import annotations

import pytest

from app.file_type_router import (
    FileTypeRoute,
    STRATEGY_ARCHIVE_CONTAINER,
    STRATEGY_BINARY_TECHNICAL,
    STRATEGY_DIRECT_TEXT,
    STRATEGY_LEGACY_OFFICE,
    STRATEGY_MEDIA_LATER,
    STRATEGY_OCR_REQUIRED,
    STRATEGY_OFFICE_TEXT,
    STRATEGY_PDF_TEXT,
    STRATEGY_UNSUPPORTED,
    STRATEGY_VISION_REQUIRED,
    route_blob,
    _normalize_extension,
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: _normalize_extension
# ---------------------------------------------------------------------------

class TestNormalizeExtension:
    def test_lowercase(self):
        assert _normalize_extension("Dokument.DOCX") == ".docx"

    def test_no_extension(self):
        assert _normalize_extension("kein_suffix") == ""

    def test_with_path(self):
        assert _normalize_extension("ordner/datei.PDF") == ".pdf"

    def test_dot_in_folder(self):
        assert _normalize_extension("v1.2/release.zip") == ".zip"

    def test_empty_string(self):
        assert _normalize_extension("") == ""


# ---------------------------------------------------------------------------
# Direkte Textdateien
# ---------------------------------------------------------------------------

class TestDirectText:
    def test_txt(self):
        r = route_blob("readme.txt")
        assert r.strategy == STRATEGY_DIRECT_TEXT
        assert r.ai_allowed is True
        assert r.extraction_required is True
        assert r.ocr_required is False
        assert r.vision_required is False
        assert r.reason_code == "route_direct_text"

    def test_csv(self):
        r = route_blob("export.csv")
        assert r.strategy == STRATEGY_DIRECT_TEXT
        assert r.ai_allowed is True

    def test_json(self):
        r = route_blob("config.json")
        assert r.strategy == STRATEGY_DIRECT_TEXT

    def test_xml(self):
        r = route_blob("manifest.xml")
        assert r.strategy == STRATEGY_DIRECT_TEXT

    def test_yaml(self):
        r = route_blob("pipeline.yaml")
        assert r.strategy == STRATEGY_DIRECT_TEXT

    def test_log(self):
        r = route_blob("app.log")
        assert r.strategy == STRATEGY_DIRECT_TEXT

    def test_ps1(self):
        r = route_blob("deploy.ps1")
        assert r.strategy == STRATEGY_DIRECT_TEXT

    def test_sql(self):
        r = route_blob("migration.sql")
        assert r.strategy == STRATEGY_DIRECT_TEXT


# ---------------------------------------------------------------------------
# Office Text (moderne Formate)
# ---------------------------------------------------------------------------

class TestOfficeText:
    def test_docx(self):
        r = route_blob("bericht.docx")
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.ai_allowed is True
        assert r.extraction_required is True
        assert r.ocr_required is False
        assert r.vision_required is False
        assert r.reason_code == "route_office_text"

    def test_xlsx(self):
        r = route_blob("tabelle.xlsx")
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.ai_allowed is True

    def test_pptx(self):
        r = route_blob("praesentation.pptx")
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.ai_allowed is True
        # Hinweis: Bilder in PPTX brauchen später Vision/OCR
        # Der Router markiert die Strategie korrekt als office_text

    def test_odt(self):
        r = route_blob("dokument.odt")
        assert r.strategy == STRATEGY_OFFICE_TEXT

    def test_path_prefix(self):
        r = route_blob("_root_part000/vertrag.docx")
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.extension == ".docx"


# ---------------------------------------------------------------------------
# Legacy Office
# ---------------------------------------------------------------------------

class TestLegacyOffice:
    def test_doc(self):
        r = route_blob("altdokument.doc")
        assert r.strategy == STRATEGY_LEGACY_OFFICE
        assert r.ai_allowed is True
        assert r.extraction_required is True
        assert r.reason_code == "route_legacy_office"

    def test_xls(self):
        r = route_blob("tabelle_alt.xls")
        assert r.strategy == STRATEGY_LEGACY_OFFICE

    def test_ppt(self):
        r = route_blob("folien_alt.ppt")
        assert r.strategy == STRATEGY_LEGACY_OFFICE

    def test_rtf(self):
        r = route_blob("schreiben.rtf")
        assert r.strategy == STRATEGY_LEGACY_OFFICE


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class TestPdfText:
    def test_pdf(self):
        r = route_blob("vertrag.pdf")
        assert r.strategy == STRATEGY_PDF_TEXT
        assert r.ai_allowed is True
        assert r.extraction_required is True
        assert r.reason_code == "route_pdf_text"

    def test_pdf_uppercase(self):
        r = route_blob("FORMULAR.PDF")
        assert r.strategy == STRATEGY_PDF_TEXT

    def test_pdf_with_path(self):
        r = route_blob("archiv/2024/rechnung.pdf")
        assert r.strategy == STRATEGY_PDF_TEXT


# ---------------------------------------------------------------------------
# Bilder – OCR / Vision / kein Extraktor
# ---------------------------------------------------------------------------

class TestImages:
    def test_jpg_no_ocr_no_vision(self):
        """Ohne OCR und Vision: ai_allowed=False, strategy=ocr_required."""
        r = route_blob("scan.jpg")
        assert r.strategy == STRATEGY_OCR_REQUIRED
        assert r.ai_allowed is False
        assert r.ocr_required is False
        assert r.skip_reason == "ocr_and_vision_disabled"
        assert r.reason_code == "route_image_no_extractor"

    def test_jpg_with_ocr(self):
        r = route_blob("scan.jpg", allow_ocr=True)
        assert r.strategy == STRATEGY_OCR_REQUIRED
        assert r.ai_allowed is True
        assert r.ocr_required is True
        assert r.vision_required is False
        assert r.reason_code == "route_ocr_required"

    def test_jpg_with_vision(self):
        r = route_blob("screenshot.jpg", allow_vision=True)
        assert r.strategy == STRATEGY_VISION_REQUIRED
        assert r.ai_allowed is True
        assert r.vision_required is True
        assert r.ocr_required is False
        assert r.reason_code == "route_vision_required"

    def test_png_with_ocr(self):
        r = route_blob("scan.png", allow_ocr=True)
        assert r.strategy == STRATEGY_OCR_REQUIRED
        assert r.ai_allowed is True

    def test_tif_with_ocr(self):
        r = route_blob("scan.tif", allow_ocr=True)
        assert r.strategy == STRATEGY_OCR_REQUIRED

    def test_tiff(self):
        r = route_blob("fax.tiff")
        assert r.strategy == STRATEGY_OCR_REQUIRED
        assert r.ai_allowed is False

    def test_ocr_takes_priority_over_vision(self):
        """Wenn beide aktiviert: OCR hat Vorrang (evaluate Reihenfolge)."""
        r = route_blob("scan.jpg", allow_ocr=True, allow_vision=True)
        assert r.strategy == STRATEGY_OCR_REQUIRED


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

class TestArchive:
    def test_zip(self):
        r = route_blob("backup.zip")
        assert r.strategy == STRATEGY_ARCHIVE_CONTAINER
        assert r.ai_allowed is False
        assert r.extraction_required is False
        assert r.skip_reason == "archive_not_processed"
        assert r.reason_code == "route_archive_container"

    def test_7z(self):
        r = route_blob("archiv.7z")
        assert r.strategy == STRATEGY_ARCHIVE_CONTAINER
        assert r.ai_allowed is False

    def test_rar(self):
        r = route_blob("dokumente.rar")
        assert r.strategy == STRATEGY_ARCHIVE_CONTAINER

    def test_tar_gz(self):
        r = route_blob("backup.tar")
        assert r.strategy == STRATEGY_ARCHIVE_CONTAINER

    def test_gz(self):
        r = route_blob("log.gz")
        assert r.strategy == STRATEGY_ARCHIVE_CONTAINER


# ---------------------------------------------------------------------------
# Binär / Ausführbare Dateien
# ---------------------------------------------------------------------------

class TestBinaryTechnical:
    def test_exe(self):
        r = route_blob("setup.exe")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL
        assert r.ai_allowed is False
        assert r.extraction_required is False
        assert r.class_hint == "technical"
        assert r.skip_reason == "binary_not_sent_to_ai"
        assert r.reason_code == "route_binary_executable"

    def test_dll(self):
        r = route_blob("library.dll")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL
        assert r.ai_allowed is False
        assert r.class_hint == "technical"

    def test_msi(self):
        r = route_blob("installer.msi")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL

    def test_iso(self):
        r = route_blob("image.iso")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL

    def test_sys(self):
        r = route_blob("driver.sys")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL


# ---------------------------------------------------------------------------
# Makro-Office (blockiert)
# ---------------------------------------------------------------------------

class TestMacroOfficeBlocked:
    def test_xlsm(self):
        r = route_blob("makros.xlsm")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL
        assert r.ai_allowed is False
        assert r.skip_reason == "macro_office_blocked"
        assert r.reason_code == "route_macro_blocked"

    def test_docm(self):
        r = route_blob("makrodok.docm")
        assert r.strategy == STRATEGY_BINARY_TECHNICAL
        assert r.ai_allowed is False


# ---------------------------------------------------------------------------
# Audio / Video
# ---------------------------------------------------------------------------

class TestMedia:
    def test_mp3(self):
        r = route_blob("aufnahme.mp3")
        assert r.strategy == STRATEGY_MEDIA_LATER
        assert r.ai_allowed is False
        assert r.skip_reason == "media_not_processed_in_mvp"
        assert r.reason_code == "route_media_later"

    def test_mp4(self):
        r = route_blob("video.mp4")
        assert r.strategy == STRATEGY_MEDIA_LATER

    def test_wav(self):
        r = route_blob("ton.wav")
        assert r.strategy == STRATEGY_MEDIA_LATER


# ---------------------------------------------------------------------------
# Unbekannte / nicht unterstützte Erweiterungen
# ---------------------------------------------------------------------------

class TestUnsupported:
    def test_unknown_extension(self):
        r = route_blob("datei.xyz")
        assert r.strategy == STRATEGY_UNSUPPORTED
        assert r.ai_allowed is False
        assert r.skip_reason == "unsupported_file_type"
        assert r.reason_code == "route_unsupported"

    def test_no_extension(self):
        r = route_blob("datei_ohne_endung")
        assert r.strategy == STRATEGY_UNSUPPORTED
        assert r.ai_allowed is False
        assert r.extension == ""

    def test_dat_file(self):
        r = route_blob("daten.dat")
        assert r.strategy == STRATEGY_UNSUPPORTED

    def test_psd_file(self):
        r = route_blob("design.psd")
        assert r.strategy == STRATEGY_UNSUPPORTED


# ---------------------------------------------------------------------------
# Größenlimit / size_warning
# ---------------------------------------------------------------------------

class TestSizeWarning:
    def test_large_docx_gets_size_warning(self):
        """Datei über Extraktionslimit bekommt size_warning=True."""
        large = 10 * 1024 * 1024  # 10 MB
        r = route_blob("gross.docx", size_bytes=large, extraction_max_bytes=5 * 1024 * 1024)
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.size_warning is True
        assert r.skip_reason == "file_too_large_for_extraction"

    def test_small_docx_no_warning(self):
        r = route_blob("klein.docx", size_bytes=100_000)
        assert r.strategy == STRATEGY_OFFICE_TEXT
        assert r.size_warning is False
        assert r.skip_reason is None

    def test_large_pdf_gets_size_warning(self):
        large = 20 * 1024 * 1024
        r = route_blob("gross.pdf", size_bytes=large)
        assert r.strategy == STRATEGY_PDF_TEXT
        assert r.size_warning is True

    def test_binary_no_size_warning(self):
        """Binärdateien ignorieren das Größenlimit (werden nie extrahiert)."""
        large = 100 * 1024 * 1024
        r = route_blob("big.exe", size_bytes=large)
        assert r.strategy == STRATEGY_BINARY_TECHNICAL
        assert r.size_warning is False

    def test_zero_size_bytes_no_warning(self):
        """size_bytes=0 (unbekannt) soll kein Warning auslösen."""
        r = route_blob("dok.docx", size_bytes=0)
        assert r.size_warning is False

    def test_txt_large_with_custom_limit(self):
        r = route_blob("log.txt", size_bytes=2000, extraction_max_bytes=1000)
        assert r.strategy == STRATEGY_DIRECT_TEXT
        assert r.size_warning is True


# ---------------------------------------------------------------------------
# Rückgabeobjekt – Vollständigkeit
# ---------------------------------------------------------------------------

class TestReturnObjectCompleteness:
    def test_all_fields_present(self):
        r = route_blob("test.docx", size_bytes=1024, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert r.blob_name == "test.docx"
        assert r.extension == ".docx"
        assert r.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert r.size_bytes == 1024
        assert isinstance(r.strategy, str)
        assert isinstance(r.ai_allowed, bool)
        assert isinstance(r.extraction_required, bool)
        assert isinstance(r.ocr_required, bool)
        assert isinstance(r.vision_required, bool)
        assert isinstance(r.reason_code, str)
        assert isinstance(r.size_warning, bool)

    def test_binary_class_hint(self):
        r = route_blob("app.exe")
        assert r.class_hint == "technical"

    def test_docx_no_class_hint(self):
        r = route_blob("bericht.docx")
        assert r.class_hint is None
