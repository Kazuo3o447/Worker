"""Tests for AI dry-run worker integration and report token fields.

Tests cover:
- Worker classify + dry_run: AI called but no tags/metadata written
- AI result appears in ClassificationResult with token fields
- RunSummary contains model and token totals
- classification-details.csv contains per-file AI token fields
- admin-report.json contains AI summary

No real Azure calls. No real Groq calls. All mocked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.ai.providers.base import AiClassificationRequest, AiClassificationResponse
from app.models import BlobRecord, ClassificationResult, RunSummary
from app.reports import ReportWriter


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class _Config:
    enable_ai: bool = True
    ai_provider: str = "groq"
    ai_model: str = "llama-3.3-70b-versatile"
    ai_prompt_version: str = "v1"
    ai_policy_mode: str = "conservative"
    ai_max_calls_per_run: int = 3
    ai_max_chars_per_file: int = 2000
    ai_max_total_chars_per_run: int = 10000
    ai_temperature: float = 0.0
    ai_max_output_tokens: int = 300
    ai_write_tags: bool = False
    ai_min_confidence_threshold: int = 60
    worker_version: str = "test-v0.1"
    worker_name: str = "Andre3000"


def _make_blob(name="test/unknown_file.txt", ext=".txt", size=500):
    return BlobRecord(
        blob_name=name,
        container="cool-stage-test",
        size_bytes=size,
        extension=ext,
        last_modified=None,
        etag='"abc123"',
        existing_tags={},
        existing_status_before="",
    )


def _make_ai_response(success=True, with_usage=True):
    """Build a mock AiClassificationResponse."""
    if success:
        return AiClassificationResponse(
            status="classified",
            class_label="contract",
            dsgvo="false",
            archive_candidate="true",
            confidence="78",
            readable="true",
            reason_code="ai_contract_match",
            explanation_short="Contract structure detected in text.",
            input_chars=450,
            provider="groq",
            ai_model="llama-3.3-70b-versatile",
            ai_prompt_version="v1",
            ai_prompt_chars=650,
            ai_text_extract_chars=450,
            ai_estimated_prompt_tokens=163,
            ai_estimated_total_input_tokens=163,
            ai_prompt_tokens=155 if with_usage else None,
            ai_completion_tokens=38 if with_usage else None,
            ai_total_tokens=193 if with_usage else None,
            ai_token_source="provider_usage" if with_usage else "estimated",
            ai_latency_ms=820,
            ai_request_id="req-xyz789",
        )
    else:
        return AiClassificationResponse(
            status="error",
            class_label="unknown",
            dsgvo="false",
            archive_candidate="false",
            confidence="0",
            readable="true",
            reason_code="ai_error",
            explanation_short="Rate limited",
            input_chars=0,
            provider="groq",
            ai_error="rate_limited",
            ai_model="llama-3.3-70b-versatile",
            ai_prompt_version="v1",
        )


# ---------------------------------------------------------------------------
# Worker dry-run: AI called but no tags/metadata written
# ---------------------------------------------------------------------------

class TestWorkerDryRunAI:
    """Verify classify + dry_run: AI fires but nothing is written to Azure."""

    def _run_classify_blob(self, dry_run=True, ai_text="Some contract text about agreement."):
        """Run _classify_blob with mocked AI provider and mocked repo."""
        from app.worker import _classify_blob

        config = _Config()
        blob = _make_blob()

        # Mock AI provider
        mock_provider = MagicMock()
        mock_provider.available = True
        mock_provider.name = "groq"
        mock_provider.classify.return_value = _make_ai_response(success=True)

        # Mock repo for text extraction
        mock_repo = MagicMock()

        # Mock the extraction pipeline to return known text
        with patch("app.worker.classify_blob") as mock_rule:
            from app.models import RuleResult
            mock_rule.return_value = RuleResult(
                class_label="unknown",
                dsgvo="false",
                archive_candidate="false",
                confidence="30",
                reason_code="no_rule_match",
            )
            with patch("app.file_type_router.route_blob") as mock_route:
                mock_file_route = MagicMock()
                mock_file_route.strategy = "plain_text"
                mock_file_route.extraction_required = True
                mock_route.return_value = mock_file_route

                with patch("app.extraction.router.route_and_extract") as mock_extract:
                    mock_ext = MagicMock()
                    mock_ext.text_available = True
                    mock_ext.text_for_ai = ai_text
                    mock_ext.extraction_status = "ok"
                    mock_ext.readable = True
                    mock_extract.return_value = mock_ext

                    mock_repo.download_blob_content.return_value = (ai_text.encode(), "")

                    result = _classify_blob(
                        run_id="test-run-001",
                        config=config,
                        blob=blob,
                        dry_run=dry_run,
                        ai_provider=mock_provider,
                        ai_calls_used=0,
                        repo=mock_repo,
                    )
        return result

    def test_dry_run_ai_called_no_tags_written(self):
        result = self._run_classify_blob(dry_run=True)
        # AI was called
        assert result.ai_called is True
        assert result.ai_success is True
        # Tags/metadata NOT written (worker doesn't write, only _write_to_azure does)
        assert result.tags_written == "false"
        assert result.metadata_written == "false"

    def test_dry_run_ai_result_in_classification(self):
        result = self._run_classify_blob(dry_run=True)
        # AI classification applied
        assert result.class_label == "contract"
        assert result.llm_used == "true"
        assert result.ai_class == "contract"

    def test_dry_run_token_fields_populated(self):
        result = self._run_classify_blob(dry_run=True)
        # Token fields from provider
        assert result.ai_prompt_tokens == 155
        assert result.ai_completion_tokens == 38
        assert result.ai_total_tokens == 193
        assert result.ai_token_source == "provider_usage"
        assert result.ai_latency_ms == 820
        assert result.ai_model == "llama-3.3-70b-versatile"
        assert result.ai_prompt_version == "v1"

    def test_no_text_extract_skips_ai(self):
        """When text_extract is empty, AI is skipped with no_text_extract reason."""
        from app.worker import _classify_blob
        config = _Config()
        blob = _make_blob()

        mock_provider = MagicMock()
        mock_provider.available = True

        mock_repo = MagicMock()

        with patch("app.worker.classify_blob") as mock_rule:
            from app.models import RuleResult
            mock_rule.return_value = RuleResult(
                class_label="unknown", dsgvo="false",
                archive_candidate="false", confidence="30", reason_code="no_rule_match",
            )
            with patch("app.file_type_router.route_blob") as mock_route:
                mock_file_route = MagicMock()
                mock_file_route.strategy = "plain_text"
                mock_file_route.extraction_required = True
                mock_route.return_value = mock_file_route

                with patch("app.extraction.router.route_and_extract") as mock_extract:
                    mock_ext = MagicMock()
                    mock_ext.text_available = False
                    mock_ext.text_for_ai = ""
                    mock_ext.extraction_status = "empty"
                    mock_extract.return_value = mock_ext

                    mock_repo.download_blob_content.return_value = (b"", "")

                    result = _classify_blob(
                        run_id="test-run-002",
                        config=config,
                        blob=blob,
                        dry_run=True,
                        ai_provider=mock_provider,
                        ai_calls_used=0,
                        repo=mock_repo,
                    )

        assert result.ai_called is False
        assert result.ai_skipped_reason == "no_text_extract"
        mock_provider.classify.assert_not_called()


# ---------------------------------------------------------------------------
# Reports: run-summary contains AI model and token totals
# ---------------------------------------------------------------------------

class TestReportsAIFields:
    def _make_summary(self, **kwargs):
        defaults = dict(
            run_id="run-20260606T120000Z",
            mode="classify",
            status="ok",
            worker_name="Andre3000",
            worker_version="test-v0.1",
            storage_account="sttest",
            source_container="cool-stage",
            report_container="reports",
            dry_run=True,
            enable_ai=True,
            ai_provider="groq",
            ai_model="llama-3.3-70b-versatile",
            ai_prompt_version="v1",
            ai_calls_used=2,
            ai_calls_skipped=1,
            ai_errors=0,
            ai_candidates=3,
            ai_max_calls_per_run=3,
            ai_prompt_tokens_total=300,
            ai_completion_tokens_total=76,
            ai_total_tokens_sum=376,
            ai_estimated_tokens_total=320,
            ai_latency_ms_avg=810.0,
            ai_latency_ms_max=900,
            ai_token_source_breakdown="provider_usage:2",
        )
        defaults.update(kwargs)
        return RunSummary(**defaults)

    def _make_result(self, blob_name="file.txt", ai_called=True):
        r = ClassificationResult(
            run_id="run-test",
            processed_at="2026-06-06T12:00:00",
            blob_name=blob_name,
            container="cool-stage",
            size_bytes=500,
            extension=".txt",
            last_modified="2026-01-01T00:00:00",
            etag='"abc"',
            existing_status_before="",
            action="classified",
            status="classified",
            class_label="contract",
            dsgvo="false",
            archive_candidate="true",
            confidence="78",
            readable="true",
            llm_used="true" if ai_called else "false",
            reason_code="ai_contract_match",
            error_reason="",
            metadata_written="false",
            tags_written="false",
            duration_ms=150,
            ai_called=ai_called,
            ai_success=ai_called,
            ai_model="llama-3.3-70b-versatile",
            ai_prompt_version="v1",
            ai_prompt_tokens=155,
            ai_completion_tokens=38,
            ai_total_tokens=193,
            ai_token_source="provider_usage",
            ai_latency_ms=820,
        )
        return r

    def test_run_summary_to_dict_contains_ai_model(self):
        summary = self._make_summary()
        d = summary.to_dict()
        assert d["ai_model"] == "llama-3.3-70b-versatile"
        assert d["ai_prompt_version"] == "v1"

    def test_run_summary_to_dict_contains_token_totals(self):
        summary = self._make_summary()
        d = summary.to_dict()
        assert d["ai_prompt_tokens_total"] == 300
        assert d["ai_completion_tokens_total"] == 76
        assert d["ai_total_tokens"] == 376
        assert d["ai_latency_ms_avg"] == 810.0

    def test_classification_details_csv_contains_ai_fields(self):
        summary = self._make_summary()
        results = [self._make_result()]
        writer = ReportWriter("run-test")
        reports = writer.build_all_reports(summary, results, [], [])
        csv_text = reports["classification-details.csv"].decode("utf-8")
        # Headers should contain AI token columns
        assert "ai_called" in csv_text
        assert "ai_prompt_tokens" in csv_text
        assert "ai_completion_tokens" in csv_text
        assert "ai_total_tokens" in csv_text
        assert "ai_token_source" in csv_text
        assert "ai_model" in csv_text
        assert "ai_prompt_version" in csv_text

    def test_admin_report_json_contains_ai_summary(self):
        summary = self._make_summary()
        results = [self._make_result()]
        writer = ReportWriter("run-test")
        reports = writer.build_all_reports(summary, results, [], [])
        admin = json.loads(reports["admin-report.json"].decode("utf-8"))
        # AI section should exist with model info
        ai = admin.get("ai", {})
        assert ai.get("model") == "llama-3.3-70b-versatile"
        assert ai.get("prompt_version") == "v1"
        assert ai.get("calls_used") == 2
        assert ai.get("prompt_tokens_total") == 300
        assert ai.get("total_tokens") == 376

    def test_run_summary_json_contains_ai_fields(self):
        summary = self._make_summary()
        writer = ReportWriter("run-test")
        reports = writer.build_all_reports(summary, [], [], [])
        run_summary = json.loads(reports["run-summary.json"].decode("utf-8"))
        assert run_summary["ai_model"] == "llama-3.3-70b-versatile"
        assert run_summary["ai_prompt_tokens_total"] == 300
        assert run_summary["ai_total_tokens"] == 376
