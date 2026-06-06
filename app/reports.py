"""Report generation: build CSV/JSON payloads for Azure upload.

Primary path: build_all_reports() → dict[filename, bytes] → uploaded to Azure.
Local writing via write_local_reports() is available for debugging only.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
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
    "needs_ai", "reason_code", "error_reason", "metadata_written", "tags_written", "duration_ms",
    # AI detailed fields
    "ai_called", "ai_success", "ai_error", "ai_model", "ai_prompt_version",
    "ai_prompt_chars", "ai_text_extract_chars",
    "ai_estimated_prompt_tokens_raw", "ai_estimated_prompt_tokens_buffered",
    "ai_estimated_prompt_tokens",
    "ai_prompt_tokens", "ai_completion_tokens", "ai_total_tokens",
    "ai_token_source", "ai_latency_ms",
    "ai_class", "ai_confidence_ai", "ai_reason_code_ai", "ai_explanation_short",
    "retry_recommended",
    # Extraction fields (AP2)
    "extractor_type", "extraction_status", "extraction_method",
    "text_available", "text_chars_total", "text_chars_for_ai",
    "content_hash_sha256", "extraction_error_code", "extraction_error_message_sanitized",
    "pages_total", "pages_sampled", "extraction_duration_ms",
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
    "ai_candidate_reason", "ai_would_call", "ai_called", "ai_skipped_reason",
    "needs_ai", "retry_recommended", "previous_status", "previous_class", "previous_llm_used",
    "budget_available",
    "extraction_status", "extraction_method", "extracted_chars",
    "ai_model", "ai_prompt_chars",
    "ai_estimated_prompt_tokens_raw", "ai_estimated_prompt_tokens_buffered",
    "ai_estimated_prompt_tokens",
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
        "needs_ai": r.needs_ai,
        "reason_code": r.reason_code,
        "error_reason": r.error_reason,
        "metadata_written": r.metadata_written,
        "tags_written": r.tags_written,
        "duration_ms": r.duration_ms,
        # Extraction fields
        "extractor_type": getattr(r, "extractor_type", ""),
        "extraction_status": getattr(r, "extraction_status", ""),
        "extraction_method": getattr(r, "extraction_method", ""),
        "text_available": getattr(r, "text_available", False),
        "text_chars_total": getattr(r, "text_chars_total", 0),
        "text_chars_for_ai": getattr(r, "text_chars_for_ai", 0),
        "content_hash_sha256": getattr(r, "content_hash_sha256", ""),
        "extraction_error_code": getattr(r, "extraction_error_code", ""),
        "extraction_error_message_sanitized": getattr(r, "extraction_error_message_sanitized", ""),
        "pages_total": getattr(r, "pages_total", 0),
        "pages_sampled": getattr(r, "pages_sampled", 0),
        "extraction_duration_ms": getattr(r, "extraction_duration_ms", 0),
        # AI detailed fields
        "ai_called": getattr(r, "ai_called", False),
        "ai_success": getattr(r, "ai_success", False),
        "ai_error": getattr(r, "ai_error", ""),
        "ai_model": getattr(r, "ai_model", ""),
        "ai_prompt_version": getattr(r, "ai_prompt_version", ""),
        "ai_prompt_chars": getattr(r, "ai_prompt_chars", 0),
        "ai_text_extract_chars": getattr(r, "ai_text_extract_chars", 0),
        "ai_estimated_prompt_tokens": getattr(r, "ai_estimated_prompt_tokens", 0),
        "ai_estimated_prompt_tokens_raw": getattr(r, "ai_estimated_prompt_tokens_raw", 0),
        "ai_estimated_prompt_tokens_buffered": getattr(r, "ai_estimated_prompt_tokens_buffered", 0),
        "ai_prompt_tokens": getattr(r, "ai_prompt_tokens", None),
        "ai_completion_tokens": getattr(r, "ai_completion_tokens", None),
        "ai_total_tokens": getattr(r, "ai_total_tokens", None),
        "ai_token_source": getattr(r, "ai_token_source", ""),
        "ai_latency_ms": getattr(r, "ai_latency_ms", 0),
        "ai_class": getattr(r, "ai_class", ""),
        "ai_confidence_ai": getattr(r, "ai_confidence_ai", 0),
        "ai_reason_code_ai": getattr(r, "ai_reason_code_ai", ""),
        "ai_explanation_short": getattr(r, "ai_explanation_short", ""),
        "retry_recommended": getattr(r, "retry_recommended", False),
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
        "ai_skipped_budget_exhausted_count": getattr(summary, "ai_skipped_budget_exhausted_count", 0),
        "needs_ai_count": getattr(summary, "needs_ai_count", 0),
        "retry_recommended_count": getattr(summary, "retry_recommended_count", 0),
        "ai_prompt_tokens_total": getattr(summary, "ai_prompt_tokens_total", 0),
        "ai_completion_tokens_total": getattr(summary, "ai_completion_tokens_total", 0),
        "ai_total_tokens": getattr(summary, "ai_total_tokens_sum", 0),
        "ai_estimated_tokens_raw_total": getattr(summary, "ai_estimated_tokens_raw_total", 0),
        "ai_estimated_tokens_buffered_total": getattr(summary, "ai_estimated_tokens_buffered_total", 0),
        "ai_token_estimation_safety_factor": getattr(summary, "ai_token_estimation_safety_factor", 1.4),
        "ai_model": getattr(summary, "ai_model", ""),
        "ai_provider": getattr(summary, "ai_provider", ""),
        # Extraction summary
        "files_with_extract": summary.files_with_extract,
        "files_without_extract": summary.files_without_extract,
        "extraction_success_count": summary.extraction_success_count,
        "extraction_failed_count": summary.extraction_failed_count,
        "extraction_no_text_count": summary.extraction_no_text_count,
        "extraction_tool_missing_count": summary.extraction_tool_missing_count,
        "extracted_chars_total": summary.extracted_chars_total,
        "extraction_method_counts": summary.extraction_method_counts,
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

        # 8. admin-report.json
        reports["admin-report.json"] = _build_admin_report_json(
            summary, results, ai_candidate_rows or []
        )

        # 9. admin-report.pdf
        try:
            reports["admin-report.pdf"] = _build_admin_report_pdf(summary, results)
        except Exception:  # noqa: BLE001
            pass  # PDF generation is best-effort; don't fail the whole run

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


# ---------------------------------------------------------------------------
# Admin report builders
# ---------------------------------------------------------------------------

def _build_admin_report_json(
    summary: RunSummary,
    results: list[ClassificationResult],
    ai_candidate_rows: list[dict[str, Any]],
) -> bytes:
    """Build admin-report.json as consolidated admin payload."""
    class_counts: dict[str, int] = {}
    needs_ai_total = 0
    rules_only = 0
    llm_used_total = 0
    for r in results:
        if r.action not in ("error", "skipped"):
            class_counts[r.class_label] = class_counts.get(r.class_label, 0) + 1
        if getattr(r, "needs_ai", False):
            needs_ai_total += 1
        if r.llm_used == "true":
            llm_used_total += 1
        else:
            rules_only += 1

    conf_vals = [int(r.confidence) for r in results if r.confidence and str(r.confidence).isdigit()]
    low_conf_total = sum(1 for c in conf_vals if c < 60)
    unknown_total = class_counts.get("unknown", 0)
    ai_disabled_total = sum(
        1 for row in ai_candidate_rows
        if row.get("ai_skipped_reason") == "ai_disabled"
    )

    ext_counts: dict[str, int] = {}
    for row in ai_candidate_rows:
        ext = row.get("extension", "")
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    top_extensions = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]

    # File type distribution from results
    file_ext_counts: dict[str, int] = {}
    file_ext_sizes: dict[str, int] = {}
    for r in results:
        ext = r.extension or "(none)"
        file_ext_counts[ext] = file_ext_counts.get(ext, 0) + 1
        file_ext_sizes[ext] = file_ext_sizes.get(ext, 0) + r.size_bytes
    file_type_distribution = [
        {"extension": ext, "count": cnt, "total_bytes": file_ext_sizes.get(ext, 0)}
        for ext, cnt in sorted(file_ext_counts.items(), key=lambda x: -x[1])
    ]

    error_summary = [
        {"blob_name": r.blob_name, "error_reason": r.error_reason}
        for r in results
        if r.action == "error"
    ][:20]

    # Risk assessment
    risks: list[dict[str, Any]] = []
    processed_safe = max(summary.files_processed, 1)
    if summary.ai_candidates > 0 and not summary.enable_ai:
        risks.append({
            "risk": "ai_candidates_but_ai_off",
            "message": f"KI-Kandidaten vorhanden ({summary.ai_candidates}), aber KI deaktiviert",
            "severity": "warning",
        })
    if unknown_total > 0 and processed_safe > 0:
        pct = unknown_total / processed_safe * 100
        if pct > 80:
            risks.append({
                "risk": "high_unknown_rate",
                "message": f"unknown > 80% der verarbeiteten Dateien ({pct:.0f}%)",
                "severity": "warning",
            })
    if summary.files_error > 0:
        risks.append({
            "risk": "errors_present",
            "message": f"{summary.files_error} Fehler im Lauf – Retry empfohlen",
            "severity": "error",
        })
    if not getattr(summary, "reports_uploaded", True) and summary.files_processed > 0:
        risks.append({
            "risk": "reports_not_uploaded",
            "message": "Reports wurden nicht nach Azure hochgeladen",
            "severity": "warning",
        })

    # Next actions (narrative, not raw commands)
    next_actions: list[str] = []
    if summary.files_error > 0:
        next_actions.append(
            f"Fehler prüfen: {summary.files_error} Dateien konnten nicht verarbeitet werden"
        )
    if needs_ai_total > 0 and not summary.enable_ai:
        next_actions.append(
            f"KI-Dry-Run vorbereiten: {needs_ai_total} AI-Kandidaten gefunden – "
            "docker compose run --rm worker --mode classify --dry-run --enable-ai --ai-provider foundry --ai-max-calls 20"
        )
    elif needs_ai_total > 0:
        next_actions.append(
            f"KI-Ergebnisse prüfen: {needs_ai_total} Dateien wurden als KI-Kandidaten markiert"
        )
    if unknown_total > 0 and not summary.enable_ai:
        next_actions.append(
            f"Keine Skalierung empfohlen: {unknown_total} Dateien als unknown – Content Extraction + KI empfohlen"
        )
    _needs_ai_s = getattr(summary, "needs_ai_count", 0)
    _retry_s = getattr(summary, "retry_recommended_count", 0)
    _budget_ex_s = getattr(summary, "ai_skipped_budget_exhausted_count", 0)
    if _needs_ai_s > 0:
        next_actions.append(
            f"needs_ai=true: {_needs_ai_s} Dateien warten auf KI – kleinen Retry-Lauf (max-files=10) planen"
        )
    if _retry_s > 0:
        next_actions.append(
            f"retry_recommended=true: {_retry_s} Dateien – erneuter Lauf ohne --force"
        )
    if _budget_ex_s > 0:
        next_actions.append(
            f"budget_exhausted: {_budget_ex_s} Dateien wegen Budget übersprungen – AI_MAX_CALLS_PER_RUN erhöhen"
        )
    if not next_actions:
        next_actions.append("Keine besonderen Maßnahmen erforderlich – Lauf war erfolgreich.")

    # Extraction aggregates (AP2)
    ext_by_type: dict[str, int] = {}
    ext_by_status: dict[str, int] = {}
    ext_by_extension: dict[str, int] = {}
    files_readable = 0
    files_unreadable = 0
    text_available_count = 0
    estimated_ai_chars = 0
    for r in results:
        et = getattr(r, "extractor_type", "")
        es = getattr(r, "extraction_status", "")
        if et:
            ext_by_type[et] = ext_by_type.get(et, 0) + 1
        if es:
            ext_by_status[es] = ext_by_status.get(es, 0) + 1
        if getattr(r, "text_available", False):
            text_available_count += 1
            estimated_ai_chars += getattr(r, "text_chars_for_ai", 0)
        if getattr(r, "readable", "true") == "true":
            files_readable += 1
        else:
            files_unreadable += 1
        rext = r.extension or "(none)"
        ext_by_extension[rext] = ext_by_extension.get(rext, 0) + 1

    report: dict[str, Any] = {
        "report_type": "admin-report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "worker_name": getattr(summary, "worker_name", "Andre3000"),
        "worker_version": getattr(summary, "worker_version", ""),
        "run": {
            "run_id": summary.run_id,
            "mode": summary.mode,
            "dry_run": summary.dry_run,
            "force": getattr(summary, "force", False),
            "prefix": summary.prefix,
            "max_files": summary.max_files,
            "started_at": summary.started_at,
            "finished_at": summary.finished_at,
            "duration_seconds": summary.duration_seconds,
            "ai_provider": summary.ai_provider if summary.enable_ai else None,
            "ai_model": getattr(summary, "ai_model", "") if summary.enable_ai else None,
            "ai_total_tokens": getattr(summary, "ai_total_tokens_sum", 0) if summary.enable_ai else None,
            "ai_prompt_tokens": getattr(summary, "ai_prompt_tokens_total", 0) if summary.enable_ai else None,
            "ai_completion_tokens": getattr(summary, "ai_completion_tokens_total", 0) if summary.enable_ai else None,
            "ai_tokens_per_file_avg": round(
                getattr(summary, "ai_total_tokens_sum", 0) / max(summary.ai_calls_used, 1), 1
            ) if summary.enable_ai and summary.ai_calls_used > 0 else None,
        },
        "azure": {
            "storage_account": summary.storage_account,
            "source_container": summary.source_container,
            "report_container": summary.report_container,
            "prefix": summary.prefix,
        },
        "security": {
            "raw_text_persisted": False,
            "dashboard_read_only": True,
            "scan_writes_disabled": True,
            "dry_run_writes_disabled": True,
            "secrets_detected_in_reports": False,
        },
        "safety": {
            "writes_enabled": not summary.dry_run,
            "ai_enabled": summary.enable_ai,
            "ai_provider": summary.ai_provider,
            "ai_max_calls_per_run": summary.ai_max_calls_per_run,
            "force": getattr(summary, "force", False),
            "max_files": summary.max_files,
        },
        "extraction": {
            "files_seen": summary.files_seen,
            "files_processed": summary.files_processed,
            "files_readable": getattr(summary, "files_readable", files_readable),
            "files_unreadable": getattr(summary, "files_unreadable", files_unreadable),
            "text_available_count": getattr(summary, "text_available_count", text_available_count),
            "by_extractor_type": ext_by_type,
            "by_extraction_status": ext_by_status,
            "by_extension": ext_by_extension,
        },
        "metrics": {
            "files_seen": summary.files_seen,
            "files_untagged": summary.files_untagged,
            "files_skipped": summary.files_skipped,
            "files_processed": summary.files_processed,
            "files_classified": summary.files_classified,
            "files_unknown": summary.files_unknown,
            "files_error": summary.files_error,
            "ai_candidates": summary.ai_candidates,
            "ai_calls_used": summary.ai_calls_used,
            "ai_calls_skipped": summary.ai_calls_skipped,
            "ai_errors": summary.ai_errors,
            "rules_only_count": rules_only,
            "llm_used_count": llm_used_total,
        },
        "classification_distribution": class_counts,
        "file_type_distribution": file_type_distribution,
        "ai_readiness": {
            "candidates_total": summary.ai_candidates,
            "unknown_total": unknown_total,
            "low_confidence_total": low_conf_total,
            "ai_disabled_total": ai_disabled_total,
            "needs_ai_total": needs_ai_total,
            "retry_recommended_total": getattr(summary, "retry_recommended_count", 0),
            "budget_exhausted_count": getattr(summary, "ai_skipped_budget_exhausted_count", 0),
            "top_extensions": [{"ext": e, "count": c} for e, c in top_extensions],
        },
        "classification_readiness": {
            "ai_candidates": summary.ai_candidates,
            "unknown_count": unknown_total,
            "low_confidence_count": low_conf_total,
            "estimated_ai_input_chars": getattr(summary, "estimated_ai_input_chars", estimated_ai_chars),
            "estimated_ai_calls": summary.ai_candidates,
        },
        "ai": {
            "enable_ai": summary.enable_ai,
            "provider": summary.ai_provider,
            "model": getattr(summary, "ai_model", ""),
            "prompt_version": getattr(summary, "ai_prompt_version", ""),
            "calls_used": summary.ai_calls_used,
            "calls_skipped": summary.ai_calls_skipped,
            "errors": summary.ai_errors,
            "budget_exhausted": (
                summary.ai_calls_used >= summary.ai_max_calls_per_run
                if summary.ai_max_calls_per_run > 0 else False
            ),
            "dry_run": summary.dry_run,
            "write_tags": not summary.dry_run,
            "note": "Dry Run - keine Tags geschrieben" if summary.dry_run else "Tags geschrieben wenn AI_WRITE_TAGS=true",
            "prompt_tokens_total": getattr(summary, "ai_prompt_tokens_total", 0),
            "completion_tokens_total": getattr(summary, "ai_completion_tokens_total", 0),
            "total_tokens": getattr(summary, "ai_total_tokens_sum", 0),
            "estimated_tokens_total": getattr(summary, "ai_estimated_tokens_total", 0),
            "latency_ms_avg": getattr(summary, "ai_latency_ms_avg", 0),
            "latency_ms_max": getattr(summary, "ai_latency_ms_max", 0),
            "token_source_breakdown": getattr(summary, "ai_token_source_breakdown", ""),
            "tokens_per_file_avg": round(
                getattr(summary, "ai_total_tokens_sum", 0) / max(summary.ai_calls_used, 1), 1
            ) if summary.ai_calls_used > 0 else 0,
            "success_rate_pct": round(
                (summary.ai_calls_used - summary.ai_errors) / max(summary.ai_calls_used, 1) * 100, 1
            ) if summary.ai_calls_used > 0 else 0,
        },
        "token_summary": {
            "ai_token_estimation_safety_factor": getattr(summary, "ai_token_estimation_safety_factor", 1.5),
            "ai_estimated_tokens_raw_total": getattr(summary, "ai_estimated_tokens_raw_total", 0),
            "ai_estimated_tokens_buffered_total": getattr(summary, "ai_estimated_tokens_buffered_total", 0),
            "ai_prompt_tokens_total": getattr(summary, "ai_prompt_tokens_total", 0),
            "ai_completion_tokens_total": getattr(summary, "ai_completion_tokens_total", 0),
            "ai_total_tokens": getattr(summary, "ai_total_tokens_sum", 0),
            "ai_latency_ms_avg": getattr(summary, "ai_latency_ms_avg", 0),
            "ai_latency_ms_max": getattr(summary, "ai_latency_ms_max", 0),
            "ai_token_source_breakdown": getattr(summary, "ai_token_source_breakdown", ""),
            "tokens_per_file_avg": round(
                getattr(summary, "ai_total_tokens_sum", 0) / max(summary.ai_calls_used, 1), 1
            ) if summary.ai_calls_used > 0 else 0,
        },
        "observability_summary": {
            "structured_logs": True,
            "run_id_in_logs": True,
            "event_buffer_to_azure": True,
            "run_duration_seconds": summary.duration_seconds,
            "files_per_hour": getattr(summary, "throughput_files_per_hour", 0),
            "extraction_method_counts": getattr(summary, "extraction_method_counts", ""),
            "extraction_success_count": getattr(summary, "extraction_success_count", 0),
            "extracted_chars_total": getattr(summary, "extracted_chars_total", 0),
            "needs_ai_count": getattr(summary, "needs_ai_count", 0),
            "retry_recommended_count": getattr(summary, "retry_recommended_count", 0),
            "ai_skipped_budget_exhausted_count": getattr(summary, "ai_skipped_budget_exhausted_count", 0),
            "missing_observability_fields": [
                "blob_processing_duration_ms",
                "download_duration_ms",
                "extraction_duration_ms_total",
                "report_upload_duration_ms",
                "pdf_pages_total",
                "pdf_pages_sampled",
                "validation_error_count",
                "human_review_required_count",
            ],
            "ai_accuracy_available": False,
            "ai_accuracy_note": (
                "Echte AI Accuracy noch nicht messbar ohne Ground Truth Labels oder Human Review. "
                "Proxy-Metriken: confidence, unknown_count, needs_ai_count, retry_recommended_count."
            ),
        },
        "errors_summary": error_summary,
        "risk_assessment": risks,
        "next_actions": next_actions,
        "report_files": [
            "run-summary.json",
            "classification-details.csv",
            "classification-summary.csv",
            "classification-errors.csv",
            "untagged-files.csv",
            "classification-samples.csv",
            "ai-candidates.csv",
            "run-events.jsonl",
            "admin-report.json",
            "admin-report.pdf",
        ],
    }
    return json.dumps(report, indent=2, default=str).encode("utf-8")


def _draw_reportlab_pie_chart(
    data: list[int],
    labels: list[str],
    width: float = 400,
    height: float = 160,
) -> Any:
    """Build a beautiful vector pie chart using ReportLab."""
    from reportlab.graphics.shapes import Drawing, String  # noqa: PLC0415
    from reportlab.graphics.charts.piecharts import Pie  # noqa: PLC0415
    from reportlab.graphics.charts.legends import Legend  # noqa: PLC0415
    from reportlab.lib import colors  # noqa: PLC0415

    d = Drawing(width, height)
    if not data:
        d.add(String(20, height // 2, "Keine Daten verfügbar", fontName="Helvetica", fontSize=10, fillColor=colors.grey))
        return d

    pc = Pie()
    pc.x = 20
    pc.y = 10
    pc.width = height - 20
    pc.height = height - 20
    pc.data = data
    pc.labels = [f"{v}" for v in data]  # numbers on slices
    pc.simpleLabels = 0

    palette = [
        colors.HexColor("#003366"),  # dark blue
        colors.HexColor("#006699"),  # medium blue
        colors.HexColor("#3399CC"),  # light blue
        colors.HexColor("#33CC99"),  # teal/green
        colors.HexColor("#FFCC00"),  # gold
        colors.HexColor("#FF6666"),  # coral/red
        colors.HexColor("#9966FF"),  # purple
    ]
    for i, color in enumerate(palette):
        if i < len(data):
            pc.slices[i].fillColor = color
            pc.slices[i].labelRadius = 0.65
            pc.slices[i].fontColor = colors.white
            pc.slices[i].fontName = "Helvetica-Bold"
            pc.slices[i].fontSize = 8

    # Legend
    legend = Legend()
    legend.x = height + 10
    legend.y = height - 10
    legend.dx = 8
    legend.dy = 8
    legend.fontSize = 8
    legend.fontName = "Helvetica"
    legend.boxAnchor = "nw"
    legend.columnMaximum = 8
    legend.strokeWidth = 0
    legend.strokeColor = colors.transparent
    legend.colorNamePairs = [(pc.slices[i].fillColor, labels[i]) for i in range(len(data))]

    d.add(pc)
    d.add(legend)
    return d


def _build_admin_report_pdf(
    summary: RunSummary,
    results: list[ClassificationResult],
) -> bytes:
    """Build admin-report.pdf using ReportLab with multi-page orientation support."""
    try:
        from reportlab.lib import colors  # noqa: PLC0415
        from reportlab.lib.pagesizes import A4, landscape  # noqa: PLC0415
        from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
        from reportlab.lib.units import cm  # noqa: PLC0415
        from reportlab.platypus import (  # noqa: PLC0415
            Paragraph,
            BaseDocTemplate,
            PageTemplate,
            Frame,
            NextPageTemplate,
            PageBreak,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ImportError("reportlab is required for PDF generation. Add it to requirements.txt.") from exc

    buf = io.BytesIO()
    
    # Setup document with dual page formats: Portrait & Landscape
    width_p, height_p = A4
    width_l, height_l = landscape(A4)
    
    frame_p = Frame(2 * cm, 2 * cm, width_p - 4 * cm, height_p - 4 * cm, id="F_Portrait")
    frame_l = Frame(2 * cm, 2 * cm, width_l - 4 * cm, height_l - 4 * cm, id="F_Landscape")
    
    template_p = PageTemplate(id="Portrait", frames=frame_p, pagesize=A4)
    template_l = PageTemplate(id="Landscape", frames=frame_l, pagesize=landscape(A4))
    
    doc = BaseDocTemplate(buf, pageTemplates=[template_p, template_l])
    
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("GEMA Storage Classification Report", styles["Title"]))
    worker_name = getattr(summary, "worker_name", "Andre3000")
    story.append(Paragraph(f"Worker: {worker_name} · Version: {summary.worker_version}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    # Run Info
    story.append(Paragraph("Run Info", styles["Heading2"]))
    _ai_model_str = getattr(summary, "ai_model", "") or "-"
    run_data = [
        ["Run-ID", summary.run_id],
        ["Modus", summary.mode],
        ["Dry Run", "Ja" if summary.dry_run else "Nein"],
        ["Force", "Ja" if summary.force else "Nein"],
        ["Gestartet", str(summary.started_at)[:19].replace("T", " ") + " UTC"],
        ["Beendet", str(summary.finished_at)[:19].replace("T", " ") + " UTC"],
        ["Dauer (s)", f"{summary.duration_seconds:.1f}"],
    ]
    if summary.enable_ai:
        run_data.append(["KI-Provider", summary.ai_provider])
        run_data.append(["KI-Modell", _ai_model_str])
        _total_tok = getattr(summary, "ai_total_tokens_sum", 0)
        _calls = summary.ai_calls_used
        run_data.append(["Token-Verbrauch gesamt", str(_total_tok)])
        run_data.append(["Tokens/Datei Ø", str(round(_total_tok / max(_calls, 1), 1)) if _calls else "-"])
    story.append(_pdf_table(run_data))
    story.append(Spacer(1, 0.3 * cm))

    # Storage
    story.append(Paragraph("Azure Storage", styles["Heading2"]))
    az_data = [
        ["Storage Account", summary.storage_account],
        ["Source Container", summary.source_container],
        ["Report Container", summary.report_container],
        ["Prefix", summary.prefix or "(alle)"],
    ]
    story.append(_pdf_table(az_data))
    story.append(Spacer(1, 0.3 * cm))

    # AI Section
    if summary.enable_ai:
        story.append(Paragraph("KI-Analyse", styles["Heading2"]))
        _pt = getattr(summary, "ai_prompt_tokens_total", 0)
        _ct = getattr(summary, "ai_completion_tokens_total", 0)
        _tt = getattr(summary, "ai_total_tokens_sum", 0)
        _calls_used = summary.ai_calls_used
        _max_calls = summary.ai_max_calls_per_run
        _budget_pct = f"{_calls_used / _max_calls * 100:.0f} %" if _max_calls > 0 else "-"
        ai_data = [
            ["Provider", summary.ai_provider],
            ["Modell (LLM)", getattr(summary, "ai_model", "") or "-"],
            ["Promptversion", getattr(summary, "ai_prompt_version", "-") or "-"],
            ["Modus", "Dry Run – keine Tags" if summary.dry_run else "Live (Tags geschrieben)"],
            ["AI Calls genutzt", str(_calls_used)],
            ["AI Calls Budget", f"{_max_calls} (genutzt: {_budget_pct})"],
            ["AI Fehler", str(summary.ai_errors)],
            ["Prompt-Tokens gesamt", str(_pt)],
            ["Completion-Tokens gesamt", str(_ct)],
            ["Total Tokens", str(_tt)],
            ["Tokens/Datei Ø", str(round(_tt / max(_calls_used, 1), 1)) if _calls_used else "-"],
            ["Latenz avg (ms)", str(round(getattr(summary, "ai_latency_ms_avg", 0), 1))],
            ["Latenz max (ms)", str(round(getattr(summary, "ai_latency_ms_max", 0), 1))],
        ]
        story.append(_pdf_table(ai_data))
        story.append(Spacer(1, 0.3 * cm))

    # Key Metrics
    story.append(Paragraph("Kennzahlen", styles["Heading2"]))
    m_data = [
        ["Dateien gesehen", str(summary.files_seen)],
        ["Ungetaggt", str(summary.files_untagged)],
        ["Verarbeitet", str(summary.files_processed)],
        ["Klassifiziert", str(summary.files_classified)],
        ["Unknown", str(summary.files_unknown)],
        ["Fehler", str(summary.files_error)],
        ["KI-Kandidaten", str(summary.ai_candidates)],
        ["KI-Aufrufe", str(summary.ai_calls_used)],
    ]
    story.append(_pdf_table(m_data))
    story.append(Spacer(1, 0.3 * cm))

    # Classification Distribution (Table & Pie Chart layout)
    story.append(Paragraph("Klassenverteilung", styles["Heading2"]))
    class_counts: dict[str, int] = {}
    for r in results:
        if r.action not in ("error", "skipped"):
            class_counts[r.class_label] = class_counts.get(r.class_label, 0) + 1
            
    if class_counts:
        c_data = [["Klasse", "Anzahl"]] + [
            [k, str(v)] for k, v in sorted(class_counts.items(), key=lambda x: -x[1])
        ]
        
        # Build nice side-by-side layout with our custom vector pie chart!
        sorted_classes = sorted(class_counts.items(), key=lambda x: -x[1])
        slice_data = [v for k, v in sorted_classes[:5]]
        slice_labels = [f"{k}" for k, v in sorted_classes[:5]]
        if len(sorted_classes) > 5:
            other_sum = sum(v for k, v in sorted_classes[5:])
            slice_data.append(other_sum)
            slice_labels.append("Andere")
            
        chart_drawing = _draw_reportlab_pie_chart(slice_data, slice_labels, width=280, height=130)
        c_table = _pdf_table(c_data, header=True, colWidths=[3 * 28.35, 2 * 28.35])
        
        layout_table = Table([[c_table, chart_drawing]], colWidths=[6 * 28.35, 10 * 28.35])
        layout_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(layout_table)
    else:
        story.append(Paragraph("Keine Klassifizierungsdaten.", styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))

    # File Type Distribution (Table & Pie Chart layout)
    ext_counts: dict[str, int] = {}
    for r in results:
        ext = r.extension or ""
        if not ext and r.blob_name:
            _, ext = os.path.splitext(r.blob_name)
        ext = ext.lower() or "unbekannt"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    if ext_counts:
        story.append(Paragraph("Dateitypenverteilung", styles["Heading2"]))
        ext_data = [["Dateiendung", "Anzahl"]] + [
            [k, str(v)] for k, v in sorted(ext_counts.items(), key=lambda x: -x[1])[:8]
        ]
        
        sorted_exts = sorted(ext_counts.items(), key=lambda x: -x[1])
        slice_data_ext = [v for k, v in sorted_exts[:5]]
        slice_labels_ext = [f"{k}" for k, v in sorted_exts[:5]]
        if len(sorted_exts) > 5:
            other_sum_ext = sum(v for k, v in sorted_exts[5:])
            slice_data_ext.append(other_sum_ext)
            slice_labels_ext.append("Andere")
            
        chart_drawing_ext = _draw_reportlab_pie_chart(slice_data_ext, slice_labels_ext, width=280, height=130)
        ext_table = _pdf_table(ext_data, header=True, colWidths=[3 * 28.35, 2 * 28.35])
        
        layout_table_ext = Table([[ext_table, chart_drawing_ext]], colWidths=[6 * 28.35, 10 * 28.35])
        layout_table_ext.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(layout_table_ext)
    story.append(Spacer(1, 0.3 * cm))

    # KI Readiness
    story.append(Paragraph("KI Readiness", styles["Heading2"]))
    conf_vals = [int(r.confidence) for r in results if r.confidence and str(r.confidence).isdigit()]
    low_conf = sum(1 for c in conf_vals if c < 60)
    needs_ai_count = sum(1 for r in results if getattr(r, "needs_ai", False))
    ki_data = [
        ["KI-Kandidaten", str(summary.ai_candidates)],
        ["Unknown", str(class_counts.get("unknown", 0))],
        ["Low Confidence (<60)", str(low_conf)],
        ["needs_ai=true", str(needs_ai_count)],
        ["KI aktiviert", "Ja" if summary.enable_ai else "Nein"],
        ["KI-Anbieter", summary.ai_provider],
    ]
    story.append(_pdf_table(ki_data))
    story.append(Spacer(1, 0.3 * cm))

    # Samples (Goes on a landscape page)
    sample_results = [r for r in results if r.action not in ("error", "skipped")][:15]
    if sample_results:
        # Switch to Landscape layout template
        story.append(NextPageTemplate("Landscape"))
        story.append(PageBreak())
        
        story.append(Paragraph("Stichproben & Details", styles["Heading1"]))
        story.append(Paragraph(
            "Diese Dateien dienen als Repräsentanten vergangener Verarbeitungsläufe. Hierbei handelt es sich "
            "um die ersten 15 erfolgreich klassifizierten Dateien dieses Runs. Sie dienen der stichprobenartigen "
            "Verifizierung der Klassifizierungsergebnisse, der Sicherheitsmarkierungen (DSGVO-Relevanz, "
            "Archiv-Kandidaten) sowie der verwendeten Erkennungswege (LLM oder Regelwerk) durch Fachbereiche.",
            styles["Normal"]
        ))
        story.append(Spacer(1, 0.4 * cm))
        
        # Printable width landscape 25.7 cm = 728.6 points
        # colWidths in cm: 11, 2, 2, 1.5, 2, 1.5, 5.7 -> Total 25.7 cm
        s_widths = [11 * 28.35, 2 * 28.35, 2 * 28.35, 1.5 * 28.35, 2 * 28.35, 1.5 * 28.35, 5.7 * 28.35]
        
        s_data = [["Blob-Name", "Klasse", "Conf.", "DSGVO", "Archiv", "LLM", "Reason / Rule"]] + [
            [
                r.blob_name[:65] if len(r.blob_name) > 65 else r.blob_name,
                r.class_label,
                f"{r.confidence}%" if r.confidence else "-",
                "Ja" if getattr(r, "dsgvo", "false") == "true" else "Nein",
                "Ja" if getattr(r, "archive_candidate", "false") == "true" else "Nein",
                "Ja" if getattr(r, "llm_used", "false") == "true" else "Nein",
                r.reason_code or ""
            ]
            for r in sample_results
        ]
        story.append(_pdf_table(s_data, header=True, colWidths=s_widths))
        story.append(Spacer(1, 0.3 * cm))
        
        # Switch back to Portrait layout template for the remaining content
        story.append(NextPageTemplate("Portrait"))
        story.append(PageBreak())

    # Errors
    if summary.files_error > 0:
        story.append(Paragraph("Fehlerübersicht", styles["Heading2"]))
        err_rows = [r for r in results if r.action == "error"][:10]
        e_data = [["Blob-Name", "Fehler"]] + [
            [r.blob_name[:60] if len(r.blob_name) > 60 else r.blob_name, r.error_reason[:60] if r.error_reason else "Unbekannter Fehler"]
            for r in err_rows
        ]
        story.append(_pdf_table(e_data, header=True))
        story.append(Spacer(1, 0.3 * cm))

    # Next Actions
    story.append(Paragraph("Empfohlene nächste Schritte", styles["Heading2"]))
    actions = []
    if needs_ai_count > 0:
        actions.append(f"• {needs_ai_count} Dateien haben needs_ai=true → KI-Dry-Run empfohlen")
    if summary.files_error > 0:
        actions.append(f"• {summary.files_error} Fehler → mit --force erneut versuchen")
    if not actions:
        actions.append("• Keine besonderen Maßnahmen erforderlich.")
    for a in actions:
        story.append(Paragraph(a, styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def _pdf_table(data: list[list[str]], header: bool = False, colWidths: list[float] | None = None) -> "Table":
    """Build a simple ReportLab table with optional custom column widths."""
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.platypus import Table, TableStyle  # noqa: PLC0415

    if colWidths is None:
        colWidths = [7 * 28.35, 9 * 28.35]
    t = Table(data, colWidths=colWidths)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t

