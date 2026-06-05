"""Report generation: build CSV/JSON payloads for Azure upload.

Primary path: build_all_reports() → dict[filename, bytes] → uploaded to Azure.
Local writing via write_local_reports() is available for debugging only.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from app.models import ClassificationResult, RunSummary

# ---------------------------------------------------------------------------
# Column schemas
# ---------------------------------------------------------------------------

_DETAIL_COLS = [
    "run_id", "processed_at", "blob_name", "container", "size_bytes", "extension",
    "last_modified", "etag", "existing_status_before", "action", "status", "class",
    "dsgvo", "archive_candidate", "confidence", "readable", "llm_used",
    "ai_provider", "ai_candidate", "ai_reason", "ai_input_chars", "ai_skipped_reason",
    "reason_code", "error_reason", "metadata_written", "tags_written", "duration_ms",
]

_ERROR_COLS = [
    "run_id", "processed_at", "blob_name", "extension", "size_bytes",
    "error_stage", "error_reason", "error_message", "retry_recommended",
]

_UNTAGGED_COLS = [
    "run_id", "detected_at", "blob_name", "size_bytes", "extension",
    "last_modified", "reason",
]

_SAMPLE_COLS = [
    "run_id", "sample_group", "blob_name", "class", "confidence",
    "reason_code", "suggested_review",
]

_AI_CANDIDATE_COLS = [
    "run_id", "detected_at", "blob_name", "extension", "size_bytes",
    "rule_class", "rule_confidence", "reason_code",
    "ai_candidate_reason", "ai_would_call", "ai_skipped_reason",
]

_SUMMARY_KV_COLS = ["key", "value"]

_SAMPLE_GROUPS = [
    "br", "dsgvo", "hr", "finance", "contract", "technical",
    "unknown", "error", "ai_candidate", "low_confidence",
]
_MAX_SAMPLES_PER_GROUP = 20


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _to_csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _result_to_row(r: ClassificationResult) -> dict[str, Any]:
    return {
        "run_id": r.run_id,
        "processed_at": r.processed_at,
        "blob_name": r.blob_name,
        "container": r.container,
        "size_bytes": r.size_bytes,
        "extension": r.extension,
        "last_modified": r.last_modified,
        "etag": r.etag,
        "existing_status_before": r.existing_status_before,
        "action": r.action,
        "status": r.status,
        "class": r.class_label,
        "dsgvo": r.dsgvo,
        "archive_candidate": r.archive_candidate,
        "confidence": r.confidence,
        "readable": r.readable,
        "llm_used": r.llm_used,
        "ai_provider": r.ai_provider,
        "ai_candidate": r.ai_candidate,
        "ai_reason": r.ai_reason,
        "ai_input_chars": r.ai_input_chars,
        "ai_skipped_reason": r.ai_skipped_reason,
        "reason_code": r.reason_code,
        "error_reason": r.error_reason,
        "metadata_written": r.metadata_written,
        "tags_written": r.tags_written,
        "duration_ms": r.duration_ms,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _build_summary_metrics(
    summary: RunSummary,
    results: list[ClassificationResult],
) -> dict[str, Any]:
    duration_hours = summary.duration_seconds / 3600 if summary.duration_seconds > 0 else 0
    gb_processed = summary.bytes_processed / (1024 ** 3)

    class_counts: dict[str, int] = {}
    llm_true = 0
    llm_false = 0
    for r in results:
        if r.action not in ("error", "skipped"):
            class_counts[r.class_label] = class_counts.get(r.class_label, 0) + 1
        if r.llm_used == "true":
            llm_true += 1
        else:
            llm_false += 1

    throughput_files = round(summary.files_processed / duration_hours, 2) if duration_hours > 0 else 0
    throughput_gb = round(gb_processed / duration_hours, 4) if duration_hours > 0 else 0

    return {
        "files_seen": summary.files_seen,
        "files_untagged": summary.files_untagged,
        "files_skipped": summary.files_skipped,
        "files_processed": summary.files_processed,
        "files_classified": summary.files_classified,
        "files_unknown": summary.files_unknown,
        "files_error": summary.files_error,
        "bytes_seen": summary.bytes_seen,
        "bytes_processed": summary.bytes_processed,
        "gb_processed": round(gb_processed, 6),
        "throughput_files_per_hour": throughput_files,
        "throughput_gb_per_hour": throughput_gb,
        "class_br": class_counts.get("br", 0),
        "class_dsgvo": class_counts.get("dsgvo", 0),
        "class_hr": class_counts.get("hr", 0),
        "class_finance": class_counts.get("finance", 0),
        "class_contract": class_counts.get("contract", 0),
        "class_technical": class_counts.get("technical", 0),
        "class_unknown": class_counts.get("unknown", 0),
        "class_unreadable": class_counts.get("unreadable", 0),
        "llm_used_true": llm_true,
        "llm_used_false": llm_false,
        "ai_candidates": summary.ai_candidates,
        "ai_calls_used": summary.ai_calls_used,
        "ai_calls_skipped": summary.ai_calls_skipped,
        "ai_errors": summary.ai_errors,
    }


def _build_samples(
    run_id: str,
    results: list[ClassificationResult],
) -> list[dict[str, Any]]:
    by_group: dict[str, list[ClassificationResult]] = {g: [] for g in _SAMPLE_GROUPS}
    for r in results:
        conf_val = int(r.confidence) if r.confidence and r.confidence.isdigit() else 0
        if r.action == "error":
            by_group["error"].append(r)
        elif r.class_label in by_group:
            by_group[r.class_label].append(r)
        if r.ai_candidate:
            by_group["ai_candidate"].append(r)
        if conf_val < 60 and r.action not in ("error", "skipped"):
            by_group["low_confidence"].append(r)

    rows: list[dict[str, Any]] = []
    for group, items in by_group.items():
        for r in items[:_MAX_SAMPLES_PER_GROUP]:
            conf_val = int(r.confidence) if r.confidence and r.confidence.isdigit() else 0
            rows.append({
                "run_id": run_id,
                "sample_group": group,
                "blob_name": r.blob_name,
                "class": r.class_label,
                "confidence": r.confidence,
                "reason_code": r.reason_code,
                "suggested_review": "yes" if conf_val < 70 else "no",
            })
    return rows


def _build_ai_candidates(
    run_id: str,
    ai_candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ai-candidates.csv rows. Generated even when AI is disabled."""
    return ai_candidate_rows


# ---------------------------------------------------------------------------
# ReportWriter
# ---------------------------------------------------------------------------

class ReportWriter:
    """Builds all report payloads as bytes.

    Primary workflow:
      reports = writer.build_all_reports(...)
      count   = repo.upload_run_reports(run_id, reports)

    write_local_reports() is available for debugging only.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    # ------------------------------------------------------------------
    # Build payloads
    # ------------------------------------------------------------------

    def build_all_reports(
        self,
        summary: RunSummary,
        results: list[ClassificationResult],
        untagged_rows: list[dict[str, Any]],
        ai_candidate_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, bytes]:
        """Return filename → bytes dict for all report files."""
        reports: dict[str, bytes] = {}

        # 1. run-summary.json
        reports["run-summary.json"] = json.dumps(
            summary.to_dict(), indent=2, default=str
        ).encode("utf-8")

        # 2. classification-details.csv
        reports["classification-details.csv"] = _to_csv_bytes(
            [_result_to_row(r) for r in results], _DETAIL_COLS
        )

        # 3. classification-errors.csv
        error_rows = [
            {
                "run_id": r.run_id, "processed_at": r.processed_at,
                "blob_name": r.blob_name, "extension": r.extension,
                "size_bytes": r.size_bytes,
                "error_stage": r.reason_code, "error_reason": r.error_reason,
                "error_message": r.error_reason, "retry_recommended": "true",
            }
            for r in results if r.action == "error"
        ]
        reports["classification-errors.csv"] = _to_csv_bytes(error_rows, _ERROR_COLS)

        # 4. untagged-files.csv
        reports["untagged-files.csv"] = _to_csv_bytes(untagged_rows, _UNTAGGED_COLS)

        # 5. classification-summary.csv
        metrics = _build_summary_metrics(summary, results)
        reports["classification-summary.csv"] = _to_csv_bytes(
            [{"key": k, "value": v} for k, v in metrics.items()], _SUMMARY_KV_COLS
        )

        # 6. classification-samples.csv
        reports["classification-samples.csv"] = _to_csv_bytes(
            _build_samples(self.run_id, results), _SAMPLE_COLS
        )

        # 7. ai-candidates.csv (generated even when AI is disabled)
        cand_rows = _build_ai_candidates(self.run_id, ai_candidate_rows or [])
        reports["ai-candidates.csv"] = _to_csv_bytes(cand_rows, _AI_CANDIDATE_COLS)

        return reports

    # ------------------------------------------------------------------
    # Debug: write locally
    # ------------------------------------------------------------------

    def write_local_reports(
        self,
        reports: dict[str, bytes],
        local_dir: str,
    ) -> list[str]:
        """Write report files to *local_dir/<run_id>/*. For debugging only."""
        run_dir = os.path.join(local_dir, self.run_id)
        os.makedirs(run_dir, exist_ok=True)
        written: list[str] = []
        for filename, data in reports.items():
            path = os.path.join(run_dir, filename)
            with open(path, "wb") as fh:
                fh.write(data)
            written.append(path)
        return written

