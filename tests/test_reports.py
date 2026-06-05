"""Tests for report aggregation, untagged detection, and dry-run/force behaviour."""

from __future__ import annotations

import json

import pytest

from app.models import ClassificationResult, RunSummary
from app.reports import (
    ReportWriter,
    _build_samples,
    _build_summary_metrics,
    _to_csv_bytes,
)


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------

_RUN_ID = "20240101T120000Z"


def _make_result(
    blob_name: str = "test/file.pdf",
    class_label: str = "finance",
    action: str = "classified",
    status: str = "classified",
    confidence: str = "80",
    reason_code: str = "path_rule_finance",
    llm_used: str = "false",
    error_reason: str = "",
    size_bytes: int = 1024,
    dsgvo: str = "false",
    archive_candidate: str = "true",
    ai_candidate: bool = False,
    ai_reason: str = "",
    ai_skipped_reason: str = "",
) -> ClassificationResult:
    return ClassificationResult(
        run_id=_RUN_ID,
        processed_at="2024-01-01T12:00:00+00:00",
        blob_name=blob_name,
        container="cool-stage-test",
        size_bytes=size_bytes,
        extension=".pdf",
        last_modified="2024-01-01T00:00:00+00:00",
        etag='"abc123"',
        existing_status_before="",
        action=action,
        status=status,
        class_label=class_label,
        dsgvo=dsgvo,
        archive_candidate=archive_candidate,
        confidence=confidence,
        readable="true",
        llm_used=llm_used,
        reason_code=reason_code,
        error_reason=error_reason,
        metadata_written="true",
        tags_written="true",
        duration_ms=5,
        ai_candidate=ai_candidate,
        ai_reason=ai_reason,
        ai_skipped_reason=ai_skipped_reason,
    )


def _make_summary(
    files_seen: int = 10,
    files_processed: int = 5,
    duration_seconds: float = 60.0,
    files_classified: int = 4,
    files_unknown: int = 1,
    files_error: int = 0,
    bytes_processed: int = 5120,
    ai_candidates: int = 0,
    ai_calls_used: int = 0,
) -> RunSummary:
    return RunSummary(
        run_id=_RUN_ID,
        mode="classify",
        status="ok",
        files_seen=files_seen,
        files_untagged=5,
        files_skipped=files_seen - 5,
        files_processed=files_processed,
        files_classified=files_classified,
        files_unknown=files_unknown,
        files_error=files_error,
        bytes_seen=10240,
        bytes_processed=bytes_processed,
        duration_seconds=duration_seconds,
        ai_candidates=ai_candidates,
        ai_calls_used=ai_calls_used,
    )


# ---------------------------------------------------------------------------
# _build_summary_metrics
# ---------------------------------------------------------------------------

class TestSummaryMetrics:
    def test_basic_counters(self):
        summary = _make_summary(files_seen=10, files_processed=5)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["files_seen"] == 10
        assert metrics["files_processed"] == 5

    def test_class_counting(self):
        summary = _make_summary(files_processed=3)
        results = [
            _make_result(class_label="br"),
            _make_result(class_label="hr"),
            _make_result(class_label="finance"),
        ]
        metrics = _build_summary_metrics(summary, results)
        assert metrics["class_br"] == 1
        assert metrics["class_hr"] == 1
        assert metrics["class_finance"] == 1
        assert metrics["class_unknown"] == 0

    def test_error_action_not_counted_in_classes(self):
        summary = _make_summary(files_processed=1)
        results = [_make_result(action="error", class_label="finance")]
        metrics = _build_summary_metrics(summary, results)
        assert metrics["class_finance"] == 0

    def test_throughput_one_hour(self):
        summary = _make_summary(files_processed=100, duration_seconds=3600.0)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["throughput_files_per_hour"] == 100.0

    def test_throughput_zero_duration(self):
        summary = _make_summary(files_processed=10, duration_seconds=0.0)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["throughput_files_per_hour"] == 0

    def test_gb_processed_one_gb(self):
        summary = _make_summary(bytes_processed=1073741824)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["gb_processed"] == pytest.approx(1.0, abs=1e-4)

    def test_llm_used_false_count(self):
        summary = _make_summary(files_processed=2)
        results = [_make_result(llm_used="false"), _make_result(llm_used="false")]
        metrics = _build_summary_metrics(summary, results)
        assert metrics["llm_used_false"] == 2
        assert metrics["llm_used_true"] == 0

    def test_llm_used_true_count(self):
        summary = _make_summary(files_processed=1)
        results = [_make_result(llm_used="true")]
        metrics = _build_summary_metrics(summary, results)
        assert metrics["llm_used_true"] == 1

    def test_ai_candidates_metric(self):
        summary = _make_summary(ai_candidates=3, ai_calls_used=2)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["ai_candidates"] == 3
        assert metrics["ai_calls_used"] == 2

    def test_ai_candidates_metric(self):
        summary = _make_summary(ai_candidates=3, ai_calls_used=2)
        metrics = _build_summary_metrics(summary, [])
        assert metrics["ai_candidates"] == 3
        assert metrics["ai_calls_used"] == 2
# ---------------------------------------------------------------------------

class TestBuildSamples:
    def test_max_20_per_group(self):
        results = [_make_result(class_label="finance") for _ in range(25)]
        samples = _build_samples(_RUN_ID, results)
        finance_samples = [s for s in samples if s["sample_group"] == "finance"]
        assert len(finance_samples) == 20

    def test_fewer_than_max(self):
        results = [_make_result(class_label="br") for _ in range(5)]
        samples = _build_samples(_RUN_ID, results)
        br_samples = [s for s in samples if s["sample_group"] == "br"]
        assert len(br_samples) == 5

    def test_error_samples_grouped_separately(self):
        results = [_make_result(action="error", error_reason="test error")]
        samples = _build_samples(_RUN_ID, results)
        error_samples = [s for s in samples if s["sample_group"] == "error"]
        assert len(error_samples) == 1

    def test_suggested_review_high_confidence(self):
        results = [_make_result(confidence="90")]
        samples = _build_samples(_RUN_ID, results)
        finance_samples = [s for s in samples if s["sample_group"] == "finance"]
        assert finance_samples[0]["suggested_review"] == "no"

    def test_suggested_review_low_confidence(self):
        results = [_make_result(confidence="30", class_label="unknown", reason_code="no_rule_match")]
        samples = _build_samples(_RUN_ID, results)
        unknown_samples = [s for s in samples if s["sample_group"] == "unknown"]
        assert unknown_samples[0]["suggested_review"] == "yes"

    def test_boundary_confidence_69(self):
        results = [_make_result(confidence="69")]
        samples = _build_samples(_RUN_ID, results)
        finance_samples = [s for s in samples if s["sample_group"] == "finance"]
        assert finance_samples[0]["suggested_review"] == "yes"

    def test_boundary_confidence_70(self):
        results = [_make_result(confidence="70")]
        samples = _build_samples(_RUN_ID, results)
        finance_samples = [s for s in samples if s["sample_group"] == "finance"]
        assert finance_samples[0]["suggested_review"] == "no"

    def test_empty_results(self):
        samples = _build_samples(_RUN_ID, [])
        assert samples == []

    def test_empty_confidence_handled(self):
        r = _make_result(confidence="")
        samples = _build_samples(_RUN_ID, [r])
        # blob appears in its class group + low_confidence group (conf=0 < 70)
        finance_samples = [s for s in samples if s["sample_group"] == "finance"]
        assert len(finance_samples) == 1
        assert finance_samples[0]["suggested_review"] == "yes"  # 0 < 70


# ---------------------------------------------------------------------------
# ReportWriter – build_all_reports returns bytes dict
# ---------------------------------------------------------------------------

class TestReportWriterBuildAll:
    def test_returns_7_files(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        reports = writer.build_all_reports(summary, [], [])
        assert len(reports) == 7
        assert "run-summary.json" in reports
        assert "classification-details.csv" in reports
        assert "classification-errors.csv" in reports
        assert "untagged-files.csv" in reports
        assert "classification-summary.csv" in reports
        assert "classification-samples.csv" in reports
        assert "ai-candidates.csv" in reports

    def test_all_values_are_bytes(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        reports = writer.build_all_reports(summary, [], [])
        for filename, data in reports.items():
            assert isinstance(data, bytes), f"{filename} is not bytes"

    def test_run_summary_json_is_valid(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        reports = writer.build_all_reports(summary, [], [])
        data = json.loads(reports["run-summary.json"].decode("utf-8"))
        assert data["run_id"] == _RUN_ID
        assert data["mode"] == "classify"

    def test_details_csv_has_ai_columns(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        reports = writer.build_all_reports(summary, [_make_result()], [])
        header = reports["classification-details.csv"].decode("utf-8").split("\n")[0]
        assert "ai_candidate" in header
        assert "ai_provider" in header
        assert "ai_reason" in header
        assert "ai_input_chars" in header

    def test_errors_csv_contains_error_rows_only(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        results = [
            _make_result(action="classified"),
            _make_result(action="error", error_reason="write failed"),
        ]
        reports = writer.build_all_reports(summary, results, [])
        lines = [l for l in reports["classification-errors.csv"].decode("utf-8").strip().split("\n") if l]
        assert len(lines) == 2  # header + 1 error row

    def test_untagged_csv_has_correct_rows(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        untagged_rows = [{
            "run_id": _RUN_ID, "detected_at": "2024-01-01T12:00:00+00:00",
            "blob_name": "folder/untagged_file.docx", "size_bytes": 2048,
            "extension": ".docx", "last_modified": "2023-12-01", "reason": "status=none",
        }]
        reports = writer.build_all_reports(summary, [], untagged_rows)
        lines = [l for l in reports["untagged-files.csv"].decode("utf-8").strip().split("\n") if l]
        assert len(lines) == 2
        assert "untagged_file.docx" in lines[1]

    def test_ai_candidates_csv_is_generated(self):
        writer = ReportWriter(_RUN_ID)
        summary = _make_summary()
        ai_cand_rows = [{
            "run_id": _RUN_ID, "detected_at": "2024-01-01T12:00:00+00:00",
            "blob_name": "x.docx", "extension": ".docx", "size_bytes": 512,
            "rule_class": "unknown", "rule_confidence": 30, "reason_code": "no_rule_match",
            "ai_candidate_reason": "class_unknown", "ai_would_call": False,
            "ai_skipped_reason": "ai_disabled",
        }]
        reports = writer.build_all_reports(summary, [], [], ai_cand_rows)
        lines = [l for l in reports["ai-candidates.csv"].decode("utf-8").strip().split("\n") if l]
        assert len(lines) == 2  # header + 1 row
        assert "x.docx" in lines[1]

    def test_write_local_reports_creates_files(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ReportWriter(_RUN_ID)
            summary = _make_summary()
            reports = writer.build_all_reports(summary, [], [])
            written = writer.write_local_reports(reports, tmpdir)
            assert len(written) == 7
            for path in written:
                assert os.path.isfile(path)


# ---------------------------------------------------------------------------
# _to_csv_bytes
# ---------------------------------------------------------------------------

class TestToCsvBytes:
    def test_empty_rows_has_only_header(self):
        data = _to_csv_bytes([], ["col1", "col2"])
        lines = [l for l in data.decode("utf-8").strip().split("\n") if l]
        assert lines == ["col1,col2"]

    def test_with_rows(self):
        rows = [{"col1": "val1", "col2": "val2"}]
        data = _to_csv_bytes(rows, ["col1", "col2"])
        lines = [l for l in data.decode("utf-8").strip().split("\n") if l]
        assert len(lines) == 2
        assert "val1" in lines[1]
        assert "val2" in lines[1]

    def test_extra_fields_ignored(self):
        rows = [{"col1": "val1", "col2": "val2", "extra": "ignored"}]
        data = _to_csv_bytes(rows, ["col1", "col2"])
        output = data.decode("utf-8")
        assert "extra" not in output
        assert "ignored" not in output

    def test_returns_bytes(self):
        data = _to_csv_bytes([], ["col1"])
        assert isinstance(data, bytes)


# ---------------------------------------------------------------------------
# RunSummary.to_dict
# ---------------------------------------------------------------------------

class TestRunSummaryToDict:
    def test_all_expected_keys_present(self):
        summary = _make_summary()
        d = summary.to_dict()
        required_keys = [
            "run_id", "mode", "status",
            "files_seen", "files_untagged", "files_skipped",
            "files_processed", "files_classified", "files_unknown", "files_error",
            "bytes_seen", "bytes_processed",
            "enable_ai", "ai_provider", "ai_candidates", "ai_calls_used",
            "ai_calls_skipped", "ai_errors",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_ai_defaults(self):
        summary = _make_summary()
        d = summary.to_dict()
        assert d["enable_ai"] is False
        assert d["ai_provider"] == "none"
        assert d["ai_candidates"] == 0
