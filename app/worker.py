"""Worker: extracted processing logic for scan, classify, extract and report modes.

This module contains the three main operation stages. Each returns an exit code
(0 = success, 1 = failure). They are called by app/main.py.

Stage overview:
  run_scan()     – list blobs, detect untagged, write scan results to Azure
  run_classify() – classify untagged blobs (rules → optional AI), upload reports
  run_extract()  – download blobs, extract metrics (no raw text), upload reports
  run_report()   – (re)build report from an existing run's results in Azure
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app import logging_utils as L
from app.ai.providers.base import AiClassificationRequest, AiClassificationResponse, get_provider
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
    ai_provider: Optional[Any] = None,
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

    # Create AI provider if not provided externally (and AI is enabled)
    if ai_provider is None and config.enable_ai and config.ai_provider not in ("none", ""):
        try:
            from app.ai.providers.base import get_provider as _get_provider  # noqa: PLC0415
            ai_provider = _get_provider(config.ai_provider)
            if not ai_provider.available:
                L.log_error(run_id, f"AI provider '{config.ai_provider}' unavailable: {ai_provider.init_error}")
                ai_provider = None
        except Exception as _prov_exc:  # noqa: BLE001
            L.log_error(run_id, f"AI provider init failed: {str(_prov_exc)[:200]}")
            ai_provider = None

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
    ai_prompt_tokens_total = 0
    ai_completion_tokens_total = 0
    ai_total_tokens_sum = 0
    ai_estimated_tokens_total = 0
    ai_estimated_tokens_raw_total = 0
    ai_estimated_tokens_buffered_total = 0
    ai_skipped_budget_exhausted_count = 0
    needs_ai_count = 0
    retry_recommended_count = 0
    ai_latency_ms_list: list = []
    ai_token_source_counts: dict = {}
    # Extraction aggregates
    extraction_success_count = 0
    extraction_failed_count = 0
    extraction_no_text_count = 0
    extraction_tool_missing_count = 0
    extracted_chars_total = 0
    extraction_method_counter: dict = {}

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
                dry_run=dry_run, ai_provider=ai_provider,
                ai_calls_used=ai_calls_used,
                repo=repo,
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
                    "extraction_status": result.extraction_status,
                    "extraction_method": result.extraction_method,
                    "extracted_chars": result.text_chars_for_ai,
                })
            if result.ai_called:
                ai_calls_used += 1
                if result.ai_prompt_tokens is not None:
                    ai_prompt_tokens_total += result.ai_prompt_tokens
                if result.ai_completion_tokens is not None:
                    ai_completion_tokens_total += result.ai_completion_tokens
                if result.ai_total_tokens is not None:
                    ai_total_tokens_sum += result.ai_total_tokens
                ai_estimated_tokens_total += result.ai_estimated_prompt_tokens
                ai_estimated_tokens_raw_total += result.ai_estimated_prompt_tokens_raw
                ai_estimated_tokens_buffered_total += result.ai_estimated_prompt_tokens_buffered
                if result.ai_latency_ms > 0:
                    ai_latency_ms_list.append(result.ai_latency_ms)
                src = result.ai_token_source or "estimated"
                ai_token_source_counts[src] = ai_token_source_counts.get(src, 0) + 1
            elif result.ai_skipped_reason:
                ai_calls_skipped += 1
                if result.ai_skipped_reason == "budget_exhausted":
                    ai_skipped_budget_exhausted_count += 1
            if result.ai_error and result.ai_candidate:
                ai_errors += 1
            if result.needs_ai:
                needs_ai_count += 1
            if result.retry_recommended:
                retry_recommended_count += 1

            results.append(result)
            files_processed += 1

            # Extraction aggregation
            if result.extraction_status == "success":
                extraction_success_count += 1
                extracted_chars_total += result.text_chars_for_ai
            elif result.extraction_status == "tool_missing":
                extraction_tool_missing_count += 1
            elif result.extraction_status in ("no_text_found", "encrypted", "not_readable"):
                extraction_no_text_count += 1
            elif result.extraction_status in ("failure", "timeout", "error"):
                extraction_failed_count += 1
            if result.extraction_method:
                m = result.extraction_method
                extraction_method_counter[m] = extraction_method_counter.get(m, 0) + 1

            if result.action == "error":
                files_error += 1
            else:
                files_classified += 1
                bytes_processed += blob.size_bytes
                if result.class_label == "unknown":
                    files_unknown += 1
                # Write tags + metadata:
                # - never in dry_run
                # - for AI results: only if AI_WRITE_TAGS=true
                write_ok = (
                    not dry_run
                    and (
                        result.llm_used != "true"
                        or getattr(config, "ai_write_tags", False)
                    )
                )
                if write_ok:
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
        ai_model=getattr(config, "ai_model", ""),
        ai_prompt_version=getattr(config, "ai_prompt_version", ""),
        ai_prompt_tokens_total=ai_prompt_tokens_total,
        ai_completion_tokens_total=ai_completion_tokens_total,
        ai_total_tokens_sum=ai_total_tokens_sum,
        ai_estimated_tokens_total=ai_estimated_tokens_total,
        ai_estimated_tokens_raw_total=ai_estimated_tokens_raw_total,
        ai_estimated_tokens_buffered_total=ai_estimated_tokens_buffered_total,
        ai_token_estimation_safety_factor=getattr(config, "ai_token_estimation_safety_factor", 1.4),
        ai_latency_ms_avg=round(sum(ai_latency_ms_list) / len(ai_latency_ms_list), 1) if ai_latency_ms_list else 0.0,
        ai_latency_ms_max=max(ai_latency_ms_list) if ai_latency_ms_list else 0,
        ai_token_source_breakdown=",".join(f"{k}:{v}" for k, v in sorted(ai_token_source_counts.items())),
        ai_skipped_budget_exhausted_count=ai_skipped_budget_exhausted_count,
        needs_ai_count=needs_ai_count,
        retry_recommended_count=retry_recommended_count,
        files_with_extract=extraction_success_count,
        files_without_extract=extraction_failed_count + extraction_no_text_count + extraction_tool_missing_count,
        extraction_success_count=extraction_success_count,
        extraction_failed_count=extraction_failed_count,
        extraction_no_text_count=extraction_no_text_count,
        extraction_tool_missing_count=extraction_tool_missing_count,
        extracted_chars_total=extracted_chars_total,
        extraction_method_counts=",".join(f"{k}:{v}" for k, v in sorted(extraction_method_counter.items())),
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
    ai_provider: Optional[Any],
    ai_calls_used: int,
    repo: Any = None,
) -> ClassificationResult:
    """Run rules + optional AI for a single blob. Never raises.

    AI flow:
      1. Rule classification (path/name-based, no download)
      2. AI policy decision
      3. If AI candidate + should_call: download limited content, extract text
      4. If text available: call AI provider, record all token fields
      5. If no text / skipped: record reason
      6. Tags/metadata written only by _write_to_azure (controlled by dry_run + ai_write_tags)
    """
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
    rule_class_before_ai = rule_result.class_label
    dsgvo = rule_result.dsgvo
    archive_candidate = rule_result.archive_candidate
    confidence = rule_result.confidence
    readable = rule_result.readable
    llm_used = "false"
    ai_reason = decision.candidate_reason
    ai_prov_name = ""
    ai_input_chars = 0
    ai_skipped_reason = ""
    error_reason = ""

    # AI token tracking
    ai_called = False
    ai_success = False
    ai_error_code = ""
    ai_model_used = ""
    ai_prompt_version_used = ""
    ai_prompt_chars = 0
    ai_text_extract_chars = 0
    ai_estimated_prompt_tokens = 0
    ai_prompt_tokens = None
    ai_completion_tokens = None
    ai_total_tokens = None
    ai_token_source = ""
    ai_latency_ms = 0
    ai_class = ""
    ai_confidence_ai = 0
    ai_reason_code_ai = ""
    ai_explanation_short = ""

    # Extraction tracking
    extractor_type_val = ""
    extraction_status_val = ""
    extraction_method_val = ""
    text_available_val = False
    text_chars_total_val = 0
    text_chars_for_ai_val = 0
    content_hash_val = ""
    extraction_error_code_val = ""
    extraction_error_msg_val = ""
    pages_total_val = 0
    pages_sampled_val = 0
    extraction_duration_ms_val = 0

    if decision.is_ai_candidate:
        L.log_ai_candidate_detected(run_id, blob.blob_name, decision.candidate_reason)

    if decision.should_call and ai_provider is not None and getattr(ai_provider, "available", False):
        # Step 1: Try to get text extract for AI input
        text_extract = ""
        extraction_status = ""
        route_strategy = ""

        if repo is not None:
            try:
                from app.file_type_router import route_blob as file_type_route_blob  # noqa: PLC0415
                from app.extraction.router import route_and_extract  # noqa: PLC0415
                file_route = file_type_route_blob(blob.blob_name, blob.size_bytes)
                route_strategy = file_route.strategy
                if file_route.extraction_required:
                    max_dl = min(blob.size_bytes, 512 * 1024)
                    content_bytes, dl_err = repo.download_blob_content(
                        blob.blob_name, max_bytes=max_dl
                    )
                    if content_bytes:
                        ext_result = route_and_extract(
                            blob_name=blob.blob_name,
                            strategy=file_route.strategy,
                            content=content_bytes,
                            ai_min_confidence=config.ai_min_confidence_threshold,
                        )
                        # Capture extraction metadata for report
                        extractor_type_val = ext_result.extractor_type
                        extraction_status_val = ext_result.extraction_status
                        extraction_method_val = ext_result.extraction_method
                        text_available_val = ext_result.text_available
                        text_chars_total_val = ext_result.text_chars_total
                        text_chars_for_ai_val = ext_result.text_chars_for_ai
                        content_hash_val = ext_result.content_hash_sha256 or ""
                        extraction_error_code_val = ext_result.error_code or ""
                        extraction_error_msg_val = ext_result.error_message_sanitized or ""
                        pages_total_val = ext_result.pages_total
                        pages_sampled_val = ext_result.pages_sampled
                        extraction_duration_ms_val = ext_result.extraction_duration_ms
                        if ext_result.text_available:
                            max_chars = getattr(config, "ai_max_chars_per_file", 2000)
                            text_extract = (ext_result._text_for_ai or "")[:max_chars]
                            extraction_status = ext_result.extraction_status
            except Exception as ext_exc:  # noqa: BLE001
                L.log_blob_error(run_id, blob.blob_name, "ai_text_extract", str(ext_exc)[:200])

        if not text_extract:
            # No text available – skip AI, mark reason
            ai_skipped_reason = "no_text_extract"
            ai_called = False
            L.log_ai_skipped(run_id, blob.blob_name, "no_text_extract")
        else:
            # Step 2: Call AI
            L.log_ai_called(run_id, blob.blob_name, config.ai_provider, len(text_extract))
            from app.ai.providers.base import AiClassificationRequest  # noqa: PLC0415
            request = AiClassificationRequest(
                blob_name=blob.blob_name,
                extension=blob.extension,
                size_bytes=blob.size_bytes,
                rule_class=rule_result.class_label,
                rule_confidence=int(rule_result.confidence),
                text_for_ai=text_extract,
                max_chars=getattr(config, "ai_max_chars_per_file", 2000),
                route_strategy=route_strategy,
                rule_reason_code=rule_result.reason_code,
            )
            ai_resp = ai_provider.classify(request)
            ai_called = True
            ai_prov_name = ai_resp.provider
            ai_input_chars = ai_resp.input_chars
            ai_model_used = ai_resp.ai_model or getattr(config, "ai_model", "")
            ai_prompt_version_used = ai_resp.ai_prompt_version or getattr(config, "ai_prompt_version", "v1")
            ai_prompt_chars = ai_resp.ai_prompt_chars
            ai_text_extract_chars = ai_resp.ai_text_extract_chars
            ai_estimated_prompt_tokens = ai_resp.ai_estimated_prompt_tokens
            ai_prompt_tokens = ai_resp.ai_prompt_tokens
            ai_completion_tokens = ai_resp.ai_completion_tokens
            ai_total_tokens = ai_resp.ai_total_tokens
            ai_token_source = ai_resp.ai_token_source
            ai_latency_ms = ai_resp.ai_latency_ms
            ai_class = ai_resp.class_label
            ai_confidence_ai = int(ai_resp.confidence) if str(ai_resp.confidence).isdigit() else 0
            ai_reason_code_ai = ai_resp.reason_code
            ai_explanation_short = ai_resp.explanation_short

            if ai_resp.ai_error:
                # AI call failed
                ai_success = False
                ai_error_code = ai_resp.ai_error
                L.log_ai_error(run_id, blob.blob_name, ai_resp.error_message or ai_resp.ai_error)
            else:
                # AI call succeeded – apply results
                ai_success = True
                class_label = ai_resp.class_label
                dsgvo = ai_resp.dsgvo
                archive_candidate = ai_resp.archive_candidate
                confidence = ai_resp.confidence
                readable = ai_resp.readable
                llm_used = "true"
                L.log_ai_result_validated(run_id, blob.blob_name, class_label, confidence)

    elif decision.is_ai_candidate and not decision.should_call:
        ai_skipped_reason = decision.skip_reason
        L.log_ai_skipped(run_id, blob.blob_name, ai_skipped_reason)
    elif decision.should_call and ai_provider is None:
        ai_skipped_reason = "no_provider_configured"

    end = dt.now(tz.utc)
    duration_ms = int((end - start).total_seconds() * 1000)

    # Compute needs_ai flag first (used by retry_recommended below)
    conf_int = int(confidence) if str(confidence).isdigit() else 0
    _ai_min = getattr(config, "ai_min_confidence_threshold", 60)
    needs_ai_val = (
        class_label == "unknown"
        or conf_int < _ai_min
        or rule_result.reason_code == "no_rule_match"
    ) and llm_used == "false"

    # Compute buffered token estimate (safety factor applied)
    _safety_factor = getattr(config, "ai_token_estimation_safety_factor", 1.4)
    import math as _math  # noqa: PLC0415
    _ai_est_raw = ai_estimated_prompt_tokens
    _ai_est_buffered = _math.ceil(_ai_est_raw * _safety_factor) if _ai_est_raw > 0 else 0

    # retry_recommended: budget_exhausted means KI has not yet processed this file
    retry_recommended_val = ai_skipped_reason == "budget_exhausted" or (
        needs_ai_val and not ai_called
    )

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

    action = "classified"
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
        status=clean_tags.get("status", "classified"),
        class_label=class_label,
        dsgvo=dsgvo,
        archive_candidate=archive_candidate,
        confidence=confidence,
        readable=readable,
        llm_used=llm_used,
        ai_candidate=decision.is_ai_candidate,
        ai_reason=ai_reason,
        ai_provider=ai_prov_name,
        ai_input_chars=ai_input_chars,
        ai_skipped_reason=ai_skipped_reason,
        rule_class_before_ai=rule_class_before_ai,
        needs_ai=needs_ai_val,
        retry_recommended=retry_recommended_val,
        reason_code=rule_result.reason_code,
        error_reason=error_reason,
        metadata_written="false",
        tags_written="false",
        duration_ms=duration_ms,
        # AI token fields
        ai_called=ai_called,
        ai_success=ai_success,
        ai_error=ai_error_code,
        ai_model=ai_model_used,
        ai_prompt_version=ai_prompt_version_used,
        ai_prompt_chars=ai_prompt_chars,
        ai_text_extract_chars=ai_text_extract_chars,
        ai_estimated_prompt_tokens=ai_estimated_prompt_tokens,
        ai_estimated_prompt_tokens_raw=_ai_est_raw,
        ai_estimated_prompt_tokens_buffered=_ai_est_buffered,
        ai_prompt_tokens=ai_prompt_tokens,
        ai_completion_tokens=ai_completion_tokens,
        ai_total_tokens=ai_total_tokens,
        ai_token_source=ai_token_source,
        ai_latency_ms=ai_latency_ms,
        ai_class=ai_class,
        ai_confidence_ai=ai_confidence_ai,
        ai_reason_code_ai=ai_reason_code_ai,
        ai_explanation_short=ai_explanation_short,
        # Extraction fields
        extractor_type=extractor_type_val,
        extraction_status=extraction_status_val,
        extraction_method=extraction_method_val,
        text_available=text_available_val,
        text_chars_total=text_chars_total_val,
        text_chars_for_ai=text_chars_for_ai_val,
        content_hash_sha256=content_hash_val,
        extraction_error_code=extraction_error_code_val,
        extraction_error_message_sanitized=extraction_error_msg_val,
        pages_total=pages_total_val,
        pages_sampled=pages_sampled_val,
        extraction_duration_ms=extraction_duration_ms_val,
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


# ---------------------------------------------------------------------------
# Stage 3: Extract (AP1)
# ---------------------------------------------------------------------------

def run_extract(
    run_id: str,
    config: Config,
    repo: Any,
    prefix: Optional[str] = None,
    max_files: int = 0,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Download blobs, extract text metrics (no raw text persisted), upload reports.

    Returns 0 on success, 1 on failure.

    Security guarantees:
    - No raw text is stored anywhere (reports, logs, tags, metadata).
    - dry_run=True: no tags/metadata written; reports written only if UPLOAD_REPORTS=true.
    - AI is NEVER called in extract mode – only candidate marking.
    """
    from app.azure_blob_repository import AzureBlobRepository
    from app.extraction.router import route_and_extract
    from app.file_type_router import route_blob as file_type_route_blob
    from app.extraction.safety import assert_no_raw_text

    assert isinstance(repo, AzureBlobRepository)

    L.log_run_started(
        run_id, "extract",
        prefix=prefix, max_files=max_files, dry_run=dry_run, force=force,
        enable_ai=False, ai_provider="none",  # AI always disabled in extract mode
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
    files_error = 0
    bytes_processed = 0
    files_readable = 0
    files_unreadable = 0
    text_available_count = 0
    estimated_ai_chars = 0
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
                if 0 < limit <= files_processed:
                    break
                continue

            files_untagged += 1
            L.log_blob_detected_untagged(run_id, blob.blob_name, reason)
            untagged_rows.append({
                "run_id": run_id, "detected_at": _now(),
                "blob_name": blob.blob_name, "size_bytes": blob.size_bytes,
                "extension": blob.extension, "last_modified": blob.last_modified,
                "reason": reason,
            })

            t_start = datetime.now(timezone.utc)

            # 1. Rule classification (path-based, no download)
            rule_result = classify_blob(blob.blob_name)

            # 2. File type routing (determines extraction strategy)
            file_route = file_type_route_blob(blob.blob_name, blob.size_bytes)

            # 3. Content download (limited) and extraction
            content: Optional[bytes] = None
            download_error = ""
            if file_route.extraction_required:
                max_dl = min(blob.size_bytes, 512 * 1024)  # cap at 512 KB
                content, download_error = repo.download_blob_content(
                    blob.blob_name, max_bytes=max_dl
                )
                if not content and download_error:
                    L.log_blob_error(run_id, blob.blob_name, "download", download_error)

            ext_result = route_and_extract(
                blob_name=blob.blob_name,
                strategy=file_route.strategy,
                content=content,
                ai_min_confidence=config.ai_min_confidence_threshold,
            )

            # 4. Safety check – never persists raw text
            safe_dict = ext_result.to_safe_dict()
            try:
                assert_no_raw_text(safe_dict)
            except Exception as safety_exc:  # noqa: BLE001
                L.log_blob_error(run_id, blob.blob_name, "safety_check", str(safety_exc)[:200])
                # Reset to safe minimal result
                from app.extraction.models import ExtractionResult  # noqa: PLC0415
                ext_result = ExtractionResult.skipped("safety_check_failed")
                safe_dict = ext_result.to_safe_dict()

            # 5. Build ClassificationResult with extraction metadata
            t_end = datetime.now(timezone.utc)
            duration_ms = int((t_end - t_start).total_seconds() * 1000)

            conf_int = int(rule_result.confidence)
            needs_ai_val = (
                rule_result.class_label == "unknown"
                or conf_int < config.ai_min_confidence_threshold
                or rule_result.reason_code == "no_rule_match"
                or ext_result.needs_ai
            )

            if needs_ai_val:
                ai_candidates += 1
                ai_candidate_rows.append({
                    "run_id": run_id, "detected_at": _now(),
                    "blob_name": blob.blob_name, "extension": blob.extension,
                    "size_bytes": blob.size_bytes,
                    "rule_class": rule_result.class_label,
                    "rule_confidence": rule_result.confidence,
                    "reason_code": rule_result.reason_code,
                    "ai_candidate_reason": ext_result.ai_candidate_reason or "needs_ai",
                    "ai_would_call": False,   # extract mode never calls AI
                    "ai_skipped_reason": "extract_mode_no_ai",
                })

            result = ClassificationResult(
                run_id=run_id,
                processed_at=_now(),
                blob_name=blob.blob_name,
                container=blob.container,
                size_bytes=blob.size_bytes,
                extension=blob.extension,
                last_modified=str(blob.last_modified),
                etag=blob.etag,
                existing_status_before=blob.existing_status_before,
                action="classified",  # extraction is a form of classification
                status=blob.existing_status_before or "new",
                class_label=rule_result.class_label,
                dsgvo=rule_result.dsgvo,
                archive_candidate=rule_result.archive_candidate,
                confidence=rule_result.confidence,
                readable="true" if ext_result.readable else "false",
                llm_used="false",  # never in extract mode
                reason_code=rule_result.reason_code,
                error_reason=safe_dict.get("error_message_sanitized") or "",
                metadata_written="false",
                tags_written="false",
                duration_ms=duration_ms,
                ai_candidate=needs_ai_val,
                ai_reason=ext_result.ai_candidate_reason or "",
                needs_ai=needs_ai_val,
                # Extraction fields
                extractor_type=safe_dict["extractor_type"],
                extraction_status=safe_dict["extraction_status"],
                text_available=safe_dict["text_available"],
                text_chars_total=safe_dict["text_chars_total"],
                text_chars_for_ai=safe_dict["text_chars_for_ai"],
                content_hash_sha256=safe_dict.get("content_hash_sha256") or "",
                extraction_error_code=safe_dict.get("error_code") or "",
                extraction_error_message_sanitized=safe_dict.get("error_message_sanitized") or "",
            )

            # Accumulate counters
            if ext_result.readable:
                files_readable += 1
            else:
                files_unreadable += 1
            if ext_result.text_available:
                text_available_count += 1
                estimated_ai_chars += ext_result.text_chars_for_ai

            results.append(result)
            files_processed += 1
            bytes_processed += blob.size_bytes

            # In non-dry-run, we deliberately do NOT write blob tags/metadata in extract mode.
            # Extract mode is a preparatory read-only pass; tags are written in classify mode.

            if 0 < limit <= files_processed:
                break

    except Exception as exc:  # noqa: BLE001
        L.log_error(run_id, f"Extract loop failed: {exc}")
        files_error += 1

    end_dt = datetime.now(timezone.utc)
    duration_seconds = (end_dt - start_dt).total_seconds()

    summary = RunSummary(
        run_id=run_id, mode="extract",
        status="ok" if files_error == 0 else "partial",
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
        finished_at=end_dt.isoformat(),
        duration_seconds=duration_seconds,
        files_seen=files_seen, bytes_seen=bytes_seen,
        files_untagged=files_untagged, files_skipped=files_skipped,
        files_processed=files_processed,
        files_classified=files_processed - files_error,
        files_unknown=sum(1 for r in results if r.class_label == "unknown"),
        files_error=files_error,
        bytes_processed=bytes_processed,
        enable_ai=False, ai_provider="none",
        ai_max_calls_per_run=config.ai_max_calls_per_run,
        ai_calls_used=0, ai_calls_skipped=0,
        ai_errors=0, ai_candidates=ai_candidates,
        # Extraction-specific
        files_readable=files_readable,
        files_unreadable=files_unreadable,
        text_available_count=text_available_count,
        estimated_ai_input_chars=estimated_ai_chars,
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
