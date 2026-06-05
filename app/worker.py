"""Worker: extracted processing logic for scan, classify and report modes.

This module contains the three main operation stages. Each returns an exit code
(0 = success, 1 = failure). They are called by app/main.py.

Stage overview:
  run_scan()     – list blobs, detect untagged, write scan results to Azure
  run_classify() – classify untagged blobs (rules → optional AI), upload reports
  run_report()   – (re)build report from an existing run's results in Azure
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app import logging_utils as L
from app.ai_foundry_client import AIFoundryClient
from app.ai_policy import should_call_ai
from app.classifier_rules import classify_blob, should_process_blob
from app.config import Config
from app.models import BlobRecord, ClassificationResult, RunSummary
from app.reports import ReportWriter
from app.validation import validate_metadata, validate_tags


# ---------------------------------------------------------------------------
# Helper: iso timestamp
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stage 1: Scan
# ---------------------------------------------------------------------------

def run_scan(
    run_id: str,
    config: Config,
    repo: Any,
    prefix: Optional[str] = None,
    max_files: int = 0,
    dry_run: bool = False,
) -> int:
    """List blobs, detect which ones need processing, upload scan results.

    Returns 0 on success, 1 on failure.
    """
    from app.azure_blob_repository import AzureBlobRepository

    assert isinstance(repo, AzureBlobRepository)

    L.log_run_started(run_id, "scan", prefix=prefix, max_files=max_files, dry_run=dry_run)

    start_dt = datetime.now(timezone.utc)
    started_at = start_dt.isoformat()

    files_seen = 0
    bytes_seen = 0
    files_untagged = 0
    files_skipped = 0
    untagged_rows: list[dict[str, Any]] = []
    errors = 0

    limit = max_files if max_files > 0 else config.default_max_files
    effective_prefix = prefix or config.default_prefix

    try:
        for blob in repo.list_source_blobs(prefix=effective_prefix or None):
            files_seen += 1
            bytes_seen += blob.size_bytes
            L.log_blob_seen(run_id, blob.blob_name, blob.size_bytes)

            should_process, reason = should_process_blob(blob.existing_tags, force=False)
            if not should_process:
                files_skipped += 1
                L.log_blob_skipped(run_id, blob.blob_name, reason)
            else:
                files_untagged += 1
                L.log_blob_detected_untagged(run_id, blob.blob_name, reason)
                untagged_rows.append({
                    "run_id": run_id,
                    "detected_at": _now(),
                    "blob_name": blob.blob_name,
                    "size_bytes": blob.size_bytes,
                    "extension": blob.extension,
                    "last_modified": blob.last_modified,
                    "reason": reason,
                })

            # Limit check: only untagged/to-process blobs count toward max_files in scan
            if 0 < limit <= files_untagged:
                break
    except Exception as exc:  # noqa: BLE001
        L.log_error(run_id, f"Scan failed: {exc}")
        errors += 1

    # Build and upload scan report
    end_dt = datetime.now(timezone.utc)
    finished_at = end_dt.isoformat()
    duration_seconds = (end_dt - start_dt).total_seconds()

    summary = RunSummary(
        run_id=run_id, mode="scan", status="ok" if errors == 0 else "error",
        worker_name=config.worker_name,
        worker_version=config.worker_version,
        storage_account=config.storage_account,
        source_container=config.source_container,
        report_container=config.report_container,
        prefix=effective_prefix or "",
        dry_run=dry_run,
        force=False,
        max_files=limit,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        files_seen=files_seen, bytes_seen=bytes_seen,
        files_untagged=files_untagged, files_skipped=files_skipped,
        files_processed=0, files_classified=0, files_unknown=0,
        files_error=errors, bytes_processed=0,
    )
    writer = ReportWriter(run_id)
    reports = writer.build_all_reports(summary, [], untagged_rows)

    # Append run-events.jsonl from in-memory buffer
    event_bytes = L.get_event_buffer_bytes()
    if event_bytes:
        reports["run-events.jsonl"] = event_bytes

    if config.upload_reports:
        count = repo.upload_run_reports(run_id, reports)
        summary.reports_uploaded = count > 0
        L.log_reports_uploaded(run_id, config.report_container, f"{config.worker_version}/{run_id}", count)
    else:
        summary.reports_uploaded = False
        L.log_reports_uploaded(run_id, config.report_container, "(skipped: UPLOAD_REPORTS=false)", 0)
    L.log_run_finished(run_id, summary.to_dict())
    return 0 if errors == 0 else 1


# ---------------------------------------------------------------------------
# Stage 2: Classify
# ---------------------------------------------------------------------------

def run_classify(
    run_id: str,
    config: Config,
    repo: Any,
    prefix: Optional[str] = None,
    max_files: int = 0,
    dry_run: bool = False,
    force: bool = False,
    ai_client: Optional[AIFoundryClient] = None,
) -> int:
    """Classify untagged blobs with rules + optional AI, upload reports.

    Returns 0 on success, 1 on failure.
    """
    from app.azure_blob_repository import AzureBlobRepository

    assert isinstance(repo, AzureBlobRepository)

    L.log_run_started(
        run_id, "classify", prefix=prefix, max_files=max_files,
        dry_run=dry_run, force=force,
        enable_ai=config.enable_ai, ai_provider=config.ai_provider,
    )

    start_dt = datetime.now(timezone.utc)
    started_at = start_dt.isoformat()

    limit = max_files if max_files > 0 else config.default_max_files
    effective_prefix = prefix or config.default_prefix

    files_seen = 0
    bytes_seen = 0
    files_untagged = 0
    files_skipped = 0
    files_processed = 0
    files_classified = 0
    files_unknown = 0
    files_error = 0
    bytes_processed = 0
    ai_calls_used = 0
    ai_calls_skipped = 0
    ai_errors = 0
    ai_candidates = 0

    results: list[ClassificationResult] = []
    untagged_rows: list[dict[str, Any]] = []
    ai_candidate_rows: list[dict[str, Any]] = []

    try:
        for blob in repo.list_source_blobs(prefix=effective_prefix or None):
            files_seen += 1
            bytes_seen += blob.size_bytes
            L.log_blob_seen(run_id, blob.blob_name, blob.size_bytes)

            should_process, reason = should_process_blob(blob.existing_tags, force=force)
            if not should_process:
                files_skipped += 1
                L.log_blob_skipped(run_id, blob.blob_name, reason)
                continue

            files_untagged += 1
            L.log_blob_detected_untagged(run_id, blob.blob_name, reason)
            untagged_rows.append({
                "run_id": run_id, "detected_at": _now(),
                "blob_name": blob.blob_name, "size_bytes": blob.size_bytes,
                "extension": blob.extension, "last_modified": blob.last_modified,
                "reason": reason,
            })

            result = _classify_blob(
                run_id=run_id, config=config, blob=blob,
                dry_run=dry_run, ai_client=ai_client,
                ai_calls_used=ai_calls_used,
            )

            # Update AI counters from result
            if result.ai_candidate:
                ai_candidates += 1
                ai_candidate_rows.append({
                    "run_id": run_id, "detected_at": _now(),
                    "blob_name": blob.blob_name, "extension": blob.extension,
                    "size_bytes": blob.size_bytes,
                    "rule_class": result.rule_class_before_ai,
                    "rule_confidence": result.confidence,
                    "reason_code": result.reason_code,
                    "ai_candidate_reason": result.ai_reason,
                    "ai_would_call": result.llm_used == "true",
                    "ai_skipped_reason": result.ai_skipped_reason,
                })
            if result.llm_used == "true":
                ai_calls_used += 1
            elif result.ai_skipped_reason:
                ai_calls_skipped += 1
            if result.error_reason and result.ai_candidate:
                ai_errors += 1

            results.append(result)
            files_processed += 1

            if result.action == "error":
                files_error += 1
            else:
                files_classified += 1
                bytes_processed += blob.size_bytes
                if result.class_label == "unknown":
                    files_unknown += 1
                # Write tags + metadata (skip in dry-run)
                if not dry_run:
                    _write_to_azure(run_id, blob.blob_name, result, repo, config)

            # Limit check: only processable blobs count toward max_files
            if 0 < limit <= files_processed:
                break

    except Exception as exc:  # noqa: BLE001
        L.log_error(run_id, f"Classify loop failed: {exc}")
        files_error += 1

    end_dt = datetime.now(timezone.utc)
    finished_at = end_dt.isoformat()
    duration_seconds = (end_dt - start_dt).total_seconds()

    summary = RunSummary(
        run_id=run_id, mode="classify", status="ok" if files_error == 0 else "partial",
        worker_name=config.worker_name,
        worker_version=config.worker_version,
        storage_account=config.storage_account,
        source_container=config.source_container,
        report_container=config.report_container,
        prefix=effective_prefix or "",
        dry_run=dry_run,
        force=force,
        max_files=limit,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        files_seen=files_seen, bytes_seen=bytes_seen,
        files_untagged=files_untagged, files_skipped=files_skipped,
        files_processed=files_processed, files_classified=files_classified,
        files_unknown=files_unknown, files_error=files_error,
        bytes_processed=bytes_processed,
        rules_only_count=files_classified - ai_calls_used,
        llm_used_count=ai_calls_used,
        enable_ai=config.enable_ai, ai_provider=config.ai_provider,
        ai_max_calls_per_run=config.ai_max_calls_per_run,
        ai_calls_used=ai_calls_used, ai_calls_skipped=ai_calls_skipped,
        ai_errors=ai_errors, ai_candidates=ai_candidates,
    )

    writer = ReportWriter(run_id)
    reports = writer.build_all_reports(summary, results, untagged_rows, ai_candidate_rows)
    event_bytes = L.get_event_buffer_bytes()
    if event_bytes:
        reports["run-events.jsonl"] = event_bytes

    if config.upload_reports:
        count = repo.upload_run_reports(run_id, reports)
        summary.reports_uploaded = count > 0
        L.log_reports_uploaded(run_id, config.report_container, f"{config.worker_version}/{run_id}", count)
    else:
        summary.reports_uploaded = False
        L.log_reports_uploaded(run_id, config.report_container, "(skipped: UPLOAD_REPORTS=false)", 0)
    L.log_run_finished(run_id, summary.to_dict())
    return 0 if files_error == 0 else 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_blob(
    run_id: str,
    config: Config,
    blob: BlobRecord,
    dry_run: bool,
    ai_client: Optional[AIFoundryClient],
    ai_calls_used: int,
) -> ClassificationResult:
    """Run rules + optional AI for a single blob. Never raises."""
    from datetime import datetime as dt, timezone as tz
    start = dt.now(tz.utc)

    rule_result = classify_blob(blob.blob_name)
    L.log_rule_classified(
        run_id, blob.blob_name, rule_result.class_label,
        rule_result.confidence, rule_result.reason_code,
    )

    decision = should_call_ai(
        rule_class=rule_result.class_label,
        rule_confidence=int(rule_result.confidence),
        reason_code=rule_result.reason_code,
        extension=blob.extension,
        config=config,
        ai_calls_used=ai_calls_used,
        mode="classify",
        dry_run=dry_run,
    )

    # Start with rule defaults
    class_label = rule_result.class_label
    rule_class_before_ai = rule_result.class_label  # capture before any AI override
    dsgvo = rule_result.dsgvo
    archive_candidate = rule_result.archive_candidate
    confidence = rule_result.confidence
    readable = rule_result.readable
    llm_used = "false"
    ai_reason = decision.candidate_reason
    ai_provider = ""
    ai_input_chars = 0
    ai_skipped_reason = ""
    error_reason = ""

    if decision.is_ai_candidate:
        L.log_ai_candidate_detected(run_id, blob.blob_name, decision.candidate_reason)

    if decision.should_call and ai_client is not None:
        L.log_ai_called(run_id, blob.blob_name, config.ai_provider, 0)
        try:
            ai_result = ai_client.classify(
                blob_name=blob.blob_name,
                extension=blob.extension,
                size_bytes=blob.size_bytes,
                rule_class=rule_result.class_label,
                rule_confidence=int(rule_result.confidence),
            )
            if ai_result is not None:
                class_label = ai_result.class_label
                dsgvo = ai_result.dsgvo
                archive_candidate = ai_result.archive_candidate
                confidence = ai_result.confidence
                readable = ai_result.readable
                llm_used = "true"
                ai_provider = ai_result.provider
                ai_input_chars = ai_result.input_chars
                L.log_ai_result_validated(run_id, blob.blob_name, class_label, confidence)
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)[:200]
            L.log_ai_error(run_id, blob.blob_name, error_msg)
            error_reason = error_msg
    elif decision.is_ai_candidate and not decision.should_call:
        ai_skipped_reason = decision.skip_reason
        L.log_ai_skipped(run_id, blob.blob_name, ai_skipped_reason)

    end = dt.now(tz.utc)
    duration_ms = int((end - start).total_seconds() * 1000)

    # Compute needs_ai flag
    conf_int = int(confidence) if str(confidence).isdigit() else 0
    _ai_min = config.ai_min_confidence_threshold if config else 60
    needs_ai_val = (
        class_label == "unknown"
        or conf_int < _ai_min
        or rule_result.reason_code == "no_rule_match"
    ) and llm_used == "false"

    new_tags = {
        "class": class_label,
        "dsgvo": dsgvo,
        "archive_candidate": archive_candidate,
        "confidence": confidence,
        "status": "classified",
        "needs_ai": "true" if needs_ai_val else "false",
    }
    clean_tags, _tag_errors = validate_tags(new_tags)

    new_metadata = {
        "worker_version": config.worker_version,
        "reason_code": rule_result.reason_code,
        "readable": readable,
        "llm_used": llm_used,
        "run_id": run_id,
    }
    clean_meta, _meta_errors = validate_metadata(new_metadata)

    L.log_blob_classified(
        run_id, blob.blob_name, class_label, confidence,
        rule_result.reason_code, dry_run=dry_run, duration_ms=duration_ms,
    )

    action = "error" if error_reason else "classified"
    return ClassificationResult(
        run_id=run_id,
        processed_at=end.isoformat(),
        blob_name=blob.blob_name,
        container=blob.container,
        size_bytes=blob.size_bytes,
        extension=blob.extension,
        last_modified=blob.last_modified,
        etag=blob.etag,
        existing_status_before=blob.existing_status_before,
        action=action,
        status="error" if error_reason else clean_tags.get("status", "classified"),
        class_label=class_label,
        dsgvo=dsgvo,
        archive_candidate=archive_candidate,
        confidence=confidence,
        readable=readable,
        llm_used=llm_used,
        ai_candidate=decision.is_ai_candidate,
        ai_reason=ai_reason,
        ai_provider=ai_provider,
        ai_input_chars=ai_input_chars,
        ai_skipped_reason=ai_skipped_reason,
        rule_class_before_ai=rule_class_before_ai,
        needs_ai=needs_ai_val,
        reason_code=rule_result.reason_code,
        error_reason=error_reason,
        metadata_written="false",
        tags_written="false",
        duration_ms=duration_ms,
    )


def _write_to_azure(
    run_id: str,
    blob_name: str,
    result: ClassificationResult,
    repo: Any,
    config: Optional[Config] = None,
) -> None:
    """Write tags and metadata to Azure. Logs on failure but does not raise."""
    tags = {
        "class": result.class_label,
        "dsgvo": result.dsgvo,
        "archive_candidate": result.archive_candidate,
        "confidence": result.confidence,
        "readable": result.readable,
        "llm_used": result.llm_used,
        "status": result.status,
        "needs_ai": "true" if result.needs_ai else "false",
    }
    ok_tags, err_tags = repo.set_blob_tags(blob_name, tags)
    if not ok_tags:
        L.log_blob_error(run_id, blob_name, "set_blob_tags", err_tags)

    worker_version = config.worker_version if config else "unknown"
    metadata: dict[str, str] = {
        "worker_version": worker_version,
        "run_id": run_id,
        "original_path": blob_name,
        "reason_code": result.reason_code,
        "readable": result.readable,
        "llm_used": result.llm_used,
        "model_name": result.ai_provider or "rules",
        "processed_at": result.processed_at,
    }
    if result.llm_used == "true":
        metadata["ai_provider"] = result.ai_provider
        metadata["ai_input_chars"] = str(result.ai_input_chars)
    if result.ai_skipped_reason:
        metadata["ai_skipped_reason"] = result.ai_skipped_reason

    ok_meta, err_meta = repo.set_blob_metadata(blob_name, metadata)
    if not ok_meta:
        L.log_blob_error(run_id, blob_name, "set_blob_metadata", err_meta)

    result.tags_written = "true" if ok_tags else "false"
    result.metadata_written = "true" if ok_meta else "false"
