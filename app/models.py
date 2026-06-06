"""Data models for the GEMA Storage Classification Worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def get_extension(blob_name: str) -> str:
    """Extract lowercase file extension including the dot. Returns '' if none."""
    parts = blob_name.rsplit(".", 1)
    if len(parts) == 2 and parts[1]:
        return "." + parts[1].lower()
    return ""


@dataclass
class BlobRecord:
    """Represents a single blob as seen during listing."""

    blob_name: str
    container: str
    size_bytes: int
    extension: str
    last_modified: Optional[datetime]
    etag: str
    existing_tags: Dict[str, str] = field(default_factory=dict)
    existing_status_before: str = ""


@dataclass
class RuleResult:
    """Output of the rule-based classifier."""

    class_label: str          # br | hr | finance | contract | technical | unknown | unreadable
    dsgvo: str                # "true" | "false"
    archive_candidate: str    # "true" | "false"
    confidence: str           # "0".."100"
    reason_code: str
    readable: str = "true"
    llm_used: str = "false"


@dataclass
class ClassificationResult:
    """Complete record for one blob after a classify or report run."""

    run_id: str
    processed_at: str
    blob_name: str
    container: str
    size_bytes: int
    extension: str
    last_modified: str
    etag: str
    existing_status_before: str
    action: str               # classified | skipped | error | report
    status: str               # new | classified | error | unreadable | skipped
    class_label: str
    dsgvo: str
    archive_candidate: str
    confidence: str
    readable: str
    llm_used: str
    reason_code: str
    error_reason: str
    metadata_written: str     # "true" | "false"
    tags_written: str         # "true" | "false"
    duration_ms: int
    # AI fields
    ai_candidate: bool = False
    ai_reason: str = ""
    ai_provider: str = ""
    ai_input_chars: int = 0
    ai_skipped_reason: str = ""
    rule_class_before_ai: str = ""  # rule class label before any AI override
    needs_ai: bool = False  # true when class=unknown, low confidence, or no_rule_match
    # AI detailed token fields
    ai_called: bool = False
    ai_success: bool = False
    ai_error: str = ""
    ai_model: str = ""
    ai_prompt_version: str = ""
    ai_prompt_chars: int = 0
    ai_text_extract_chars: int = 0
    ai_estimated_prompt_tokens: int = 0      # raw estimate (ceil(chars/4))
    ai_estimated_prompt_tokens_raw: int = 0  # same as above, explicit label
    ai_estimated_prompt_tokens_buffered: int = 0  # raw * safety_factor
    ai_prompt_tokens: Optional[int] = None
    ai_completion_tokens: Optional[int] = None
    ai_total_tokens: Optional[int] = None
    ai_token_source: str = ""
    ai_latency_ms: int = 0
    ai_class: str = ""
    ai_confidence_ai: int = 0
    ai_reason_code_ai: str = ""
    ai_explanation_short: str = ""
    retry_recommended: bool = False  # True when budget_exhausted or ai needs retry
    # Extraction fields (AP2) – populated in extract mode
    extractor_type: str = ""
    extraction_status: str = ""
    extraction_method: str = ""
    text_available: bool = False
    text_chars_total: int = 0
    text_chars_for_ai: int = 0
    content_hash_sha256: str = ""
    extraction_error_code: str = ""
    extraction_error_message_sanitized: str = ""
    pages_total: int = 0
    pages_sampled: int = 0
    extraction_duration_ms: int = 0


@dataclass
class RunSummary:
    """Aggregated summary for the entire worker run."""

    run_id: str
    mode: str
    status: str               # ok | partial | error
    # Configuration snapshot
    worker_name: str = "Andre3000"
    worker_version: str = ""
    storage_account: str = ""
    source_container: str = ""
    report_container: str = ""
    prefix: str = ""
    dry_run: bool = False
    force: bool = False
    max_files: int = 0
    # Timing
    started_at: str = ""
    finished_at: str = ""
    # Counters
    files_seen: int = 0
    files_untagged: int = 0
    files_skipped: int = 0
    files_processed: int = 0
    files_classified: int = 0
    files_unknown: int = 0
    files_error: int = 0
    bytes_seen: int = 0
    bytes_processed: int = 0
    duration_seconds: float = 0.0
    # Classification breakdown
    rules_only_count: int = 0
    llm_used_count: int = 0
    # Reports
    reports_uploaded: bool = False
    # AI stats
    enable_ai: bool = False
    ai_provider: str = "none"
    ai_max_calls_per_run: int = 0
    ai_calls_used: int = 0
    ai_calls_skipped: int = 0
    ai_errors: int = 0
    ai_candidates: int = 0
    # AI token totals
    ai_model: str = ""
    ai_prompt_version: str = ""
    ai_prompt_tokens_total: int = 0
    ai_completion_tokens_total: int = 0
    ai_total_tokens_sum: int = 0
    ai_estimated_tokens_total: int = 0
    ai_latency_ms_avg: float = 0.0
    ai_latency_ms_max: int = 0
    ai_token_source_breakdown: str = ""
    # Retry / needs_ai summary
    ai_skipped_budget_exhausted_count: int = 0
    needs_ai_count: int = 0
    retry_recommended_count: int = 0
    # Token estimation details
    ai_estimated_tokens_raw_total: int = 0
    ai_estimated_tokens_buffered_total: int = 0
    ai_token_estimation_safety_factor: float = 1.4
    # Extraction stats (AP2)
    files_readable: int = 0
    files_unreadable: int = 0
    text_available_count: int = 0
    estimated_ai_input_chars: int = 0
    files_with_extract: int = 0
    files_without_extract: int = 0
    extraction_success_count: int = 0
    extraction_failed_count: int = 0
    extraction_no_text_count: int = 0
    extraction_tool_missing_count: int = 0
    extracted_chars_total: int = 0
    extraction_method_counts: str = ""  # e.g. "antiword:5,pymupdf:3"

    def to_dict(self) -> Dict[str, Any]:
        duration_hours = self.duration_seconds / 3600 if self.duration_seconds > 0 else 0
        gb_processed = self.bytes_processed / (1024 ** 3)
        throughput_files = round(self.files_processed / duration_hours, 2) if duration_hours > 0 else 0
        throughput_gb = round(gb_processed / duration_hours, 4) if duration_hours > 0 else 0
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "status": self.status,
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "storage_account": self.storage_account,
            "source_container": self.source_container,
            "report_container": self.report_container,
            "prefix": self.prefix,
            "dry_run": self.dry_run,
            "force": self.force,
            "max_files": self.max_files,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "enable_ai": self.enable_ai,
            "ai_provider": self.ai_provider,
            "ai_max_calls_per_run": self.ai_max_calls_per_run,
            "ai_calls_used": self.ai_calls_used,
            "ai_calls_skipped": self.ai_calls_skipped,
            "ai_errors": self.ai_errors,
            "ai_candidates": self.ai_candidates,
            "ai_model": self.ai_model,
            "ai_prompt_version": self.ai_prompt_version,
            "ai_prompt_tokens_total": self.ai_prompt_tokens_total,
            "ai_completion_tokens_total": self.ai_completion_tokens_total,
            "ai_total_tokens": self.ai_total_tokens_sum,
            "ai_estimated_tokens_total": self.ai_estimated_tokens_total,
            "ai_estimated_tokens_raw_total": self.ai_estimated_tokens_raw_total,
            "ai_estimated_tokens_buffered_total": self.ai_estimated_tokens_buffered_total,
            "ai_token_estimation_safety_factor": self.ai_token_estimation_safety_factor,
            "ai_latency_ms_avg": self.ai_latency_ms_avg,
            "ai_latency_ms_max": self.ai_latency_ms_max,
            "ai_token_source_breakdown": self.ai_token_source_breakdown,
            "ai_skipped_budget_exhausted_count": self.ai_skipped_budget_exhausted_count,
            "needs_ai_count": self.needs_ai_count,
            "retry_recommended_count": self.retry_recommended_count,
            "duration_seconds": self.duration_seconds,
            "files_seen": self.files_seen,
            "files_untagged": self.files_untagged,
            "files_skipped": self.files_skipped,
            "files_processed": self.files_processed,
            "files_classified": self.files_classified,
            "files_unknown": self.files_unknown,
            "files_error": self.files_error,
            "bytes_seen": self.bytes_seen,
            "bytes_processed": self.bytes_processed,
            "gb_processed": round(gb_processed, 6),
            "throughput_files_per_hour": throughput_files,
            "throughput_gb_per_hour": throughput_gb,
            "rules_only_count": self.rules_only_count,
            "llm_used_count": self.llm_used_count,
            "reports_uploaded": self.reports_uploaded,
            "files_with_extract": self.files_with_extract,
            "files_without_extract": self.files_without_extract,
            "extraction_success_count": self.extraction_success_count,
            "extraction_failed_count": self.extraction_failed_count,
            "extraction_no_text_count": self.extraction_no_text_count,
            "extraction_tool_missing_count": self.extraction_tool_missing_count,
            "extracted_chars_total": self.extracted_chars_total,
            "extraction_method_counts": self.extraction_method_counts,
        }
