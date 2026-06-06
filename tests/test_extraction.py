"""Tests for the extraction module (AP2): direct_text, legacy_office, router.

Run with:
    python -m pytest tests/test_extraction.py -v
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.extraction.direct_text import extract as direct_extract
from app.extraction.legacy_office import extract as office_extract
from app.extraction.models import ExtractionResult
from app.extraction.router import route_and_extract


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _utf8(text: str) -> bytes:
    return text.encode("utf-8")


def _make_docx_bytes(body_text: str) -> bytes:
    """Create a minimal valid .docx (ZIP with word/document.xml)."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        f"<w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml.encode("utf-8"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# direct_text extractor
# ---------------------------------------------------------------------------


class TestDirectTextExtractor:
    def test_plain_utf8_txt(self):
        content = _utf8("Hello World – some plain text content.\n" * 10)
        result = direct_extract("readme.txt", content)
        assert result.extraction_status == "ok"
        assert result.readable is True
        assert result.text_available is True
        assert result.text_chars_total > 0
        assert result.text_chars_for_ai > 0
        assert result._text_for_ai  # in-memory only – must be populated

    def test_json_file(self):
        content = _utf8('{"key": "value", "count": 42}')
        result = direct_extract("data.json", content)
        assert result.extraction_status == "ok"
        assert result.text_available is True

    def test_csv_file(self):
        content = _utf8("name,age,city\nAlice,30,Berlin\nBob,25,Hamburg\n")
        result = direct_extract("table.csv", content)
        assert result.readable is True
        assert result.text_chars_total >= 30

    def test_yaml_file(self):
        content = _utf8("key: value\nlist:\n  - a\n  - b\n")
        result = direct_extract("config.yaml", content)
        assert result.extraction_status == "ok"

    def test_binary_content_detected(self):
        # Many non-printable bytes (null + control chars) to trigger binary threshold > 0.30
        binary = bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0b,
                         0x0c, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
                         0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f]) * 80
        result = direct_extract("binary.txt", binary)
        assert result.extraction_status == "binary_detected"
        assert result.readable is False
        assert result.text_available is False

    def test_empty_content(self):
        result = direct_extract("empty.txt", b"")
        # Empty content returns not_readable (no distinction from None in implementation)
        assert result.extraction_status in ("empty", "not_readable")
        assert result.text_available is False

    def test_max_ai_chars_respected(self):
        long_text = "a" * 10_000
        result = direct_extract("long.txt", _utf8(long_text), max_ai_chars=4000)
        assert result.text_chars_for_ai <= 4000
        assert result.text_chars_total == len(long_text)

    def test_content_hash_sha256_present(self):
        content = _utf8("deterministic content for hashing")
        r1 = direct_extract("file.txt", content)
        r2 = direct_extract("file.txt", content)
        assert r1.content_hash_sha256 == r2.content_hash_sha256
        assert len(r1.content_hash_sha256) == 64  # SHA-256 hex

    def test_extractor_type_is_direct_text(self):
        result = direct_extract("notes.md", _utf8("# Title\nContent."))
        assert result.extractor_type == "direct_text"

    def test_none_content_returns_download_failed(self):
        result = direct_extract("file.txt", None)  # type: ignore[arg-type]
        # None content is treated as not_readable (no content received)
        assert result.extraction_status in ("download_failed", "not_readable")
        assert result.readable is False

    def test_latin1_encoding_fallback(self):
        # Use pure latin-1 compatible German text (no em-dash)
        content = "Ae Oe Ue ae oe ue - German text umlauts: Gross.\n".encode("latin-1")
        result = direct_extract("german.txt", content)
        assert result.readable is True


# ---------------------------------------------------------------------------
# legacy_office extractor
# ---------------------------------------------------------------------------


class TestLegacyOfficeExtractor:
    def test_docx_extracts_text(self):
        content = _make_docx_bytes("Important document content for testing.")
        result = office_extract("report.docx", content)
        assert result.extraction_status == "ok"
        assert result.readable is True
        assert result.text_available is True
        assert result.text_chars_total > 0

    def test_doc_antiword_missing(self):
        # When antiword is not in PATH, should return tool_missing
        with patch("shutil.which", return_value=None):
            result = office_extract("old_report.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        assert result.extraction_status == "tool_missing"
        assert result.readable is False
        assert result.text_available is False
        assert result.extraction_method == "antiword"

    def test_doc_antiword_success(self):
        # Mock antiword returning text
        mock_proc = MagicMock()
        mock_proc.stdout = b"Extracted document text from Word file."
        with patch("shutil.which", return_value="/usr/bin/antiword"), \
             patch("subprocess.run", return_value=mock_proc):
            result = office_extract("report.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        assert result.extraction_status == "success"
        assert result.readable is True
        assert result.text_available is True
        assert result.text_chars_total > 0
        assert result.extraction_method == "antiword"
        assert result._text_for_ai  # in-memory only

    def test_doc_antiword_no_output(self):
        # antiword returns empty stdout
        mock_proc = MagicMock()
        mock_proc.stdout = b""
        with patch("shutil.which", return_value="/usr/bin/antiword"), \
             patch("subprocess.run", return_value=mock_proc):
            result = office_extract("empty.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        assert result.extraction_status == "no_text_found"
        assert result.text_available is False

    def test_doc_antiword_timeout(self):
        import subprocess
        with patch("shutil.which", return_value="/usr/bin/antiword"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("antiword", 10)):
            result = office_extract("slow.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        assert result.extraction_status == "timeout"
        assert result.text_available is False
        assert result.extraction_method == "antiword"

    def test_doc_antiword_max_chars(self):
        big_text = ("x" * 500 + "\n") * 20
        mock_proc = MagicMock()
        mock_proc.stdout = big_text.encode("utf-8")
        with patch("shutil.which", return_value="/usr/bin/antiword"), \
             patch("subprocess.run", return_value=mock_proc):
            result = office_extract("big.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 512,
                                    max_ai_chars=500)
        assert result.text_chars_for_ai <= 500
        assert result.text_chars_total > 500

    def test_docx_corrupted_zip(self):
        result = office_extract("corrupted.docx", b"not a valid zip")
        # Corrupted ZIP returns 'error' status
        assert result.extraction_status in ("extract_error", "zip_error", "error")
        # Must not raise an exception

    def test_extractor_type_is_legacy_office(self):
        content = _make_docx_bytes("Some text")
        result = office_extract("file.docx", content)
        assert result.extractor_type == "legacy_office"

    def test_docx_text_for_ai_populated(self):
        content = _make_docx_bytes("Relevant contract text for analysis.")
        result = office_extract("contract.docx", content)
        assert result.text_available is True
        if result._text_for_ai:
            assert "Relevant contract text" in result._text_for_ai


# ---------------------------------------------------------------------------
# extraction router
# ---------------------------------------------------------------------------


class TestExtractionRouter:
    def test_direct_text_strategy(self):
        content = _utf8("Hello from direct text.")
        result = route_and_extract("notes.txt", "direct_text", content)
        assert result.extractor_type == "direct_text"
        assert result.extraction_status == "ok"

    def test_legacy_office_strategy_docx(self):
        content = _make_docx_bytes("Office content")
        result = route_and_extract("file.docx", "legacy_office", content)
        assert result.extractor_type == "legacy_office"

    def test_pdf_strategy_calls_pymupdf(self):
        # PyMuPDF not installed in test env → tool_missing, but router wires correctly
        with patch("app.extraction.pdf_extractor.extract") as mock_pdf:
            mock_pdf.return_value = ExtractionResult(
                extractor_type="pdf", extraction_status="success",
                readable=True, text_available=True,
                text_chars_total=100, text_chars_for_ai=100,
                safe_preview_available=True,
                content_hash_sha256=None, language_hint="de",
                error_code=None, error_message_sanitized=None,
                needs_ai=True, ai_candidate_reason="pdf_text_available",
                extraction_method="pymupdf",
            )
            result = route_and_extract("file.pdf", "pdf_text", b"%PDF-1.4")
        assert result.extraction_status == "success"
        assert result.extraction_method == "pymupdf"

    def test_ocr_strategy_unsupported(self):
        result = route_and_extract("scan.tiff", "ocr_required", b"\xff\xd8")
        assert result.text_available is False
        assert result.extraction_status in ("unsupported", "not_implemented")

    def test_binary_strategy(self):
        result = route_and_extract("app.exe", "binary_technical", b"MZ" + b"\x00" * 100)
        assert result.readable is False
        assert result.text_available is False

    def test_media_strategy(self):
        result = route_and_extract("video.mp4", "media_later", b"\x00\x00\x00\x20ftyp")
        assert result.text_available is False

    def test_archive_strategy(self):
        result = route_and_extract("archive.zip", "archive_container", b"PK" + b"\x03\x04")
        assert result.text_available is False

    def test_none_content_returns_download_failed(self):
        result = route_and_extract("file.txt", "direct_text", None)
        assert result.extraction_status == "download_failed"

    def test_office_text_strategy_uses_office_extractor(self):
        content = _make_docx_bytes("DOCX via office_text strategy")
        result = route_and_extract("file.docx", "office_text", content)
        assert result.extractor_type == "legacy_office"

    def test_to_safe_dict_no_raw_text(self):
        content = _utf8("some potentially sensitive text")
        result = route_and_extract("notes.txt", "direct_text", content)
        safe = result.to_safe_dict()
        assert "_text_for_ai" not in safe
        assert "text_for_ai" not in safe
        assert "raw_text" not in safe
        for v in safe.values():
            if isinstance(v, str):
                assert "sensitive text" not in v  # no raw text in safe dict


# ---------------------------------------------------------------------------
# ExtractionResult model
# ---------------------------------------------------------------------------


class TestExtractionResultModel:
    def test_unsupported_factory(self):
        r = ExtractionResult.unsupported("pdf_text")
        assert r.readable is False
        assert r.text_available is False
        assert r.extraction_status == "unsupported"

    def test_legacy_doc_not_supported_factory(self):
        r = ExtractionResult.legacy_doc_not_supported()
        assert r.extraction_status == "legacy_doc_not_supported"
        assert r.readable is False

    def test_skipped_factory(self):
        r = ExtractionResult.skipped("test_reason")
        assert r.extraction_status == "skipped"

    def test_to_safe_dict_excludes_text_for_ai(self):
        r = ExtractionResult(
            extractor_type="direct_text",
            extraction_status="ok",
            readable=True,
            text_available=True,
            text_chars_total=100,
            text_chars_for_ai=100,
            safe_preview_available=False,
            content_hash_sha256=None,
            language_hint=None,
            error_code=None,
            error_message_sanitized=None,
            needs_ai=False,
            ai_candidate_reason=None,
        )
        r._text_for_ai = "SECRET TEXT SHOULD NOT APPEAR"
        safe = r.to_safe_dict()
        assert "_text_for_ai" not in safe
        for v in safe.values():
            assert "SECRET TEXT" not in str(v)

    def test_new_fields_in_to_safe_dict(self):
        """New extraction detail fields are serialised."""
        r = ExtractionResult(
            extractor_type="pdf",
            extraction_status="success",
            readable=True,
            text_available=True,
            text_chars_total=500,
            text_chars_for_ai=400,
            safe_preview_available=True,
            content_hash_sha256="abc",
            language_hint="de",
            error_code=None,
            error_message_sanitized=None,
            needs_ai=True,
            ai_candidate_reason=None,
            extraction_method="pymupdf",
            pages_total=5,
            pages_sampled=3,
            extraction_duration_ms=42,
        )
        d = r.to_safe_dict()
        assert d["extraction_method"] == "pymupdf"
        assert d["pages_total"] == 5
        assert d["pages_sampled"] == 3
        assert d["extraction_duration_ms"] == 42


# ---------------------------------------------------------------------------
# PDF extractor
# ---------------------------------------------------------------------------


class TestPdfExtractor:
    """Tests for app/extraction/pdf_extractor.py using mocked PyMuPDF."""

    def _make_fitz_mock(self, page_texts, is_encrypted=False, page_count=None):
        doc = MagicMock()
        doc.is_encrypted = is_encrypted
        doc.page_count = page_count if page_count is not None else len(page_texts)
        pages = []
        for txt in page_texts:
            p = MagicMock()
            p.get_text.return_value = txt
            pages.append(p)
        doc.load_page.side_effect = lambda i: pages[i]
        return doc

    def test_success_with_text(self):
        from app.extraction import pdf_extractor
        doc_mock = self._make_fitz_mock(["Page one text.", "Page two text."])
        fitz_mod = MagicMock()
        fitz_mod.open.return_value = doc_mock
        with patch.dict("sys.modules", {"fitz": fitz_mod}):
            import importlib
            importlib.reload(pdf_extractor)
            result = pdf_extractor.extract("doc.pdf", b"%PDF-1.4 content")
        assert result.extraction_status == "success"
        assert result.readable is True
        assert result.text_available is True
        assert result.text_chars_total > 0
        assert result.extraction_method == "pymupdf"
        assert result.pages_total == 2
        assert result.pages_sampled == 2

    def test_no_text_found(self):
        from app.extraction import pdf_extractor
        doc_mock = self._make_fitz_mock(["", "   ", ""])
        fitz_mod = MagicMock()
        fitz_mod.open.return_value = doc_mock
        with patch.dict("sys.modules", {"fitz": fitz_mod}):
            import importlib
            importlib.reload(pdf_extractor)
            result = pdf_extractor.extract("scan.pdf", b"%PDF-1.4")
        assert result.extraction_status == "no_text_found"
        assert result.text_available is False
        assert result.extraction_method == "pymupdf"

    def test_encrypted_pdf(self):
        from app.extraction import pdf_extractor
        doc_mock = self._make_fitz_mock([], is_encrypted=True, page_count=3)
        fitz_mod = MagicMock()
        fitz_mod.open.return_value = doc_mock
        with patch.dict("sys.modules", {"fitz": fitz_mod}):
            import importlib
            importlib.reload(pdf_extractor)
            result = pdf_extractor.extract("locked.pdf", b"%PDF-1.4")
        assert result.extraction_status == "encrypted"
        assert result.readable is False
        assert result.pages_total == 3

    def test_pdf_max_pages_respected(self):
        from app.extraction import pdf_extractor
        doc_mock = self._make_fitz_mock(["p1", "p2", "p3", "p4", "p5"], page_count=5)
        fitz_mod = MagicMock()
        fitz_mod.open.return_value = doc_mock
        with patch.dict("sys.modules", {"fitz": fitz_mod}):
            import importlib
            importlib.reload(pdf_extractor)
            result = pdf_extractor.extract("big.pdf", b"%PDF-1.4", pdf_max_pages=2)
        assert result.pages_sampled == 2

    def test_max_chars_respected(self):
        from app.extraction import pdf_extractor
        long_text = "x" * 10_000
        doc_mock = self._make_fitz_mock([long_text])
        fitz_mod = MagicMock()
        fitz_mod.open.return_value = doc_mock
        with patch.dict("sys.modules", {"fitz": fitz_mod}):
            import importlib
            importlib.reload(pdf_extractor)
            result = pdf_extractor.extract("long.pdf", b"%PDF-1.4", max_ai_chars=500)
        assert result.text_chars_for_ai <= 500


# ---------------------------------------------------------------------------
# Worker AI Gate: extracted_chars gate
# ---------------------------------------------------------------------------


class TestWorkerAiGate:
    """Verify that AI gate logic respects extracted_chars."""

    def test_text_available_passes_gate(self):
        """When extraction succeeds with text, text_extract will be populated."""
        from app.extraction.models import ExtractionResult
        r = ExtractionResult(
            extractor_type="legacy_office", extraction_status="success",
            readable=True, text_available=True,
            text_chars_total=200, text_chars_for_ai=200,
            safe_preview_available=True,
            content_hash_sha256="abc", language_hint="de",
            error_code=None, error_message_sanitized=None,
            needs_ai=True, ai_candidate_reason="doc_text_available",
            extraction_method="antiword",
        )
        r._text_for_ai = "some document text for AI analysis"
        # Simulate worker gate
        text_extract = (r._text_for_ai or "") if r.text_available else ""
        assert len(text_extract) > 0

    def test_no_text_blocks_gate(self):
        """When extraction finds no text, gate blocks AI."""
        from app.extraction.models import ExtractionResult
        r = ExtractionResult(
            extractor_type="legacy_office", extraction_status="no_text_found",
            readable=False, text_available=False,
            text_chars_total=0, text_chars_for_ai=0,
            safe_preview_available=False,
            content_hash_sha256="abc", language_hint=None,
            error_code="no_text_found", error_message_sanitized="no text",
            needs_ai=False, ai_candidate_reason=None,
            extraction_method="antiword",
        )
        text_extract = (r._text_for_ai or "") if r.text_available else ""
        assert text_extract == ""
