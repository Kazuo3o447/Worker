"""Tests for rule-based classifier."""

from __future__ import annotations

import pytest

from app.classifier_rules import (
    _get_extension,
    classify_blob,
    should_process_blob,
)


# ---------------------------------------------------------------------------
# classify_blob – path/keyword rules
# ---------------------------------------------------------------------------

class TestClassifyBlobPathRules:
    def test_betriebsrat_keyword(self):
        r = classify_blob("Dokumente/betriebsrat/protokoll_2023.docx")
        assert r.class_label == "br"
        assert r.dsgvo == "true"
        assert r.archive_candidate == "true"
        assert r.confidence == "90"
        assert r.reason_code == "path_rule_betriebsrat"

    def test_br_underscore_prefix(self):
        r = classify_blob("br_vereinbarung_2022.pdf")
        assert r.class_label == "br"

    def test_br_path_segment(self):
        r = classify_blob("archive/br/notes.txt")
        assert r.class_label == "br"

    def test_personal_keyword(self):
        r = classify_blob("personal/mitarbeiter.xlsx")
        assert r.class_label == "hr"
        assert r.dsgvo == "true"
        assert r.confidence == "80"

    def test_hr_path_segment(self):
        r = classify_blob("docs/hr/contract.pdf")
        assert r.class_label == "hr"

    def test_human_resources_keyword(self):
        r = classify_blob("human resources/overview.pptx")
        assert r.class_label == "hr"

    def test_rechnung_keyword(self):
        r = classify_blob("buchhaltung/rechnung_2024.pdf")
        assert r.class_label == "finance"
        assert r.dsgvo == "false"

    def test_invoice_keyword(self):
        r = classify_blob("invoices/invoice_001.pdf")
        assert r.class_label == "finance"

    def test_finanz_keyword(self):
        r = classify_blob("finanzberichte/Q1_2024.xlsx")
        assert r.class_label == "finance"

    def test_vertrag_keyword(self):
        r = classify_blob("vertraege/vertrag_muster.docx")
        assert r.class_label == "contract"
        assert r.confidence == "75"

    def test_vereinbarung_keyword(self):
        r = classify_blob("vereinbarung_2023.docx")
        assert r.class_label == "contract"

    def test_contract_keyword(self):
        r = classify_blob("contracts/vendor_contract.pdf")
        assert r.class_label == "contract"


# ---------------------------------------------------------------------------
# classify_blob – extension rules
# ---------------------------------------------------------------------------

class TestClassifyBlobExtensionRules:
    def test_ps1_extension(self):
        r = classify_blob("scripts/deploy.ps1")
        assert r.class_label == "technical"
        assert r.dsgvo == "false"
        assert r.archive_candidate == "true"
        assert r.reason_code == "extension_rule_technical"

    def test_json_extension(self):
        r = classify_blob("config/settings.json")
        assert r.class_label == "technical"

    def test_xml_extension(self):
        r = classify_blob("data/config.xml")
        assert r.class_label == "technical"

    def test_config_extension(self):
        r = classify_blob("app/app.config")
        assert r.class_label == "technical"

    def test_sql_extension(self):
        r = classify_blob("db/migration.sql")
        assert r.class_label == "technical"

    def test_log_extension(self):
        r = classify_blob("logs/app.log")
        assert r.class_label == "technical"


# ---------------------------------------------------------------------------
# classify_blob – default/unknown
# ---------------------------------------------------------------------------

class TestClassifyBlobDefault:
    def test_unknown_class(self):
        r = classify_blob("random/unrelated_file.txt")
        assert r.class_label == "unknown"
        assert r.confidence == "30"
        assert r.reason_code == "no_rule_match"
        assert r.archive_candidate == "false"
        assert r.dsgvo == "false"

    def test_no_extension_unknown(self):
        r = classify_blob("folder/some_document_without_extension")
        assert r.class_label == "unknown"


# ---------------------------------------------------------------------------
# classify_blob – case-insensitivity and rule priority
# ---------------------------------------------------------------------------

class TestClassifyBlobEdgeCases:
    def test_case_insensitive_betriebsrat(self):
        r = classify_blob("BETRIEBSRAT/Protokoll.docx")
        assert r.class_label == "br"

    def test_case_insensitive_extension(self):
        r = classify_blob("script.PS1")
        assert r.class_label == "technical"

    def test_betriebsrat_beats_personal(self):
        # "betriebsrat" rule comes first → br wins over hr
        r = classify_blob("betriebsrat/personal/file.pdf")
        assert r.class_label == "br"

    def test_betriebsrat_beats_extension(self):
        r = classify_blob("betriebsrat/setup.ps1")
        assert r.class_label == "br"

    def test_llm_used_false_by_default(self):
        r = classify_blob("any/file.txt")
        assert r.llm_used == "false"

    def test_readable_true_by_default(self):
        r = classify_blob("any/file.txt")
        assert r.readable == "true"


# ---------------------------------------------------------------------------
# should_process_blob
# ---------------------------------------------------------------------------

class TestShouldProcessBlob:
    def test_no_status_should_process(self):
        ok, reason = should_process_blob({})
        assert ok is True
        assert "none" in reason

    def test_status_new_should_process(self):
        ok, _ = should_process_blob({"status": "new"})
        assert ok is True

    def test_status_error_should_process(self):
        ok, _ = should_process_blob({"status": "error"})
        assert ok is True

    def test_status_classified_skip(self):
        ok, reason = should_process_blob({"status": "classified"})
        assert ok is False
        assert "classified" in reason

    def test_status_skipped_skip(self):
        ok, _ = should_process_blob({"status": "skipped"})
        assert ok is False

    def test_status_unreadable_skip(self):
        ok, _ = should_process_blob({"status": "unreadable"})
        assert ok is False

    def test_force_overrides_classified(self):
        ok, reason = should_process_blob({"status": "classified"}, force=True)
        assert ok is True
        assert "force=true" in reason

    def test_force_overrides_skipped(self):
        ok, reason = should_process_blob({"status": "skipped"}, force=True)
        assert ok is True

    def test_force_overrides_unreadable(self):
        ok, _ = should_process_blob({"status": "unreadable"}, force=True)
        assert ok is True

    def test_force_false_still_skips_classified(self):
        ok, _ = should_process_blob({"status": "classified"}, force=False)
        assert ok is False

    def test_unknown_status_is_processed(self):
        ok, reason = should_process_blob({"status": "some_future_status"})
        assert ok is True

    # --- needs_ai retry behaviour (new) ---

    def test_classified_needs_ai_true_should_retry(self):
        """status=classified + needs_ai=true → allow re-processing for AI."""
        ok, reason = should_process_blob({"status": "classified", "needs_ai": "true"})
        assert ok is True
        assert "needs_ai=true" in reason

    def test_classified_needs_ai_false_skip(self):
        """status=classified + needs_ai=false → final, skip."""
        ok, _ = should_process_blob({"status": "classified", "needs_ai": "false"})
        assert ok is False

    def test_classified_no_needs_ai_tag_skip(self):
        """status=classified, no needs_ai tag → skip (final by default)."""
        ok, _ = should_process_blob({"status": "classified"})
        assert ok is False

    def test_pending_ai_should_process(self):
        """status=pending_ai → in retry statuses, should process."""
        ok, reason = should_process_blob({"status": "pending_ai"})
        assert ok is True

    def test_needs_ai_true_but_status_skipped_skip(self):
        """status=skipped + needs_ai=true → skipped is final regardless of needs_ai."""
        ok, _ = should_process_blob({"status": "skipped", "needs_ai": "true"})
        assert ok is False


# ---------------------------------------------------------------------------
# _get_extension helper
# ---------------------------------------------------------------------------

class TestGetExtension:
    def test_pdf(self):
        assert _get_extension("file.pdf") == ".pdf"

    def test_no_extension(self):
        assert _get_extension("filename_without_ext") == ""

    def test_uppercase_lowercased(self):
        assert _get_extension("FILE.PS1") == ".ps1"

    def test_path_with_extension(self):
        assert _get_extension("folder/subfolder/file.docx") == ".docx"

    def test_dot_only(self):
        # "file." → split gives ["file", ""] → empty ext
        assert _get_extension("file.") == ""

    def test_hidden_file_unix(self):
        # ".gitignore" → split gives [".gitignore"] or [".gitignore", ""]
        # rsplit(".", 1) on ".gitignore" → ["", "gitignore"]
        assert _get_extension(".gitignore") == ".gitignore"
