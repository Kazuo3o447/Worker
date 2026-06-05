"""Structured JSON logging to stdout + in-memory event buffer for run-events.jsonl.

Events are:
  1. Printed as JSON Lines to stdout (always)
  2. Buffered in memory when enable_event_buffering() is called
     → caller retrieves with get_event_buffer_bytes() and uploads to Azure
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# In-memory event buffer
# ---------------------------------------------------------------------------
_event_buffer: list[str] = []
_buffer_enabled: bool = False


def enable_event_buffering() -> None:
    """Start buffering events in memory (call once at run start)."""
    global _buffer_enabled, _event_buffer
    _buffer_enabled = True
    _event_buffer = []


def get_event_buffer_bytes() -> bytes:
    """Return all buffered events as UTF-8 JSONL bytes."""
    if not _event_buffer:
        return b""
    return ("\n".join(_event_buffer) + "\n").encode("utf-8")


def clear_event_buffer() -> None:
    _event_buffer.clear()


# ---------------------------------------------------------------------------
# Core emitter
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event: str, level: str = "INFO", message: str = "", **kwargs: Any) -> None:
    record: dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": level,
        "event": event,
        "message": message or event,
        **kwargs,
    }
    line = json.dumps(record, default=str)
    print(line, flush=True)
    if _buffer_enabled:
        _event_buffer.append(line)


# ---------------------------------------------------------------------------
# Public log helpers – standard
# ---------------------------------------------------------------------------

def log_run_started(run_id: str, mode: str, **kwargs: Any) -> None:
    _emit("run_started",
          message=f"Run {run_id} started in mode '{mode}'",
          run_id=run_id, mode=mode, **kwargs)


def log_run_finished(run_id: str, summary: dict[str, Any]) -> None:
    _emit("run_finished",
          message=(f"Run {run_id} finished. "
                   f"processed={summary.get('files_processed', 0)}, "
                   f"errors={summary.get('files_error', 0)}"),
          **summary)


def log_blob_seen(run_id: str, blob_name: str, size_bytes: int) -> None:
    _emit("blob_seen", message=f"Blob listed: {blob_name}",
          run_id=run_id, blob_name=blob_name, size_bytes=size_bytes)


def log_blob_skipped(run_id: str, blob_name: str, reason: str) -> None:
    _emit("blob_skipped", message=f"Blob skipped ({reason}): {blob_name}",
          run_id=run_id, blob_name=blob_name, reason=reason)


def log_blob_detected_untagged(run_id: str, blob_name: str, reason: str) -> None:
    _emit("blob_detected_untagged",
          message=f"Blob queued for processing ({reason}): {blob_name}",
          run_id=run_id, blob_name=blob_name, reason=reason)


def log_rule_classified(
    run_id: str,
    blob_name: str,
    class_label: str,
    confidence: str,
    reason_code: str,
) -> None:
    _emit("rule_classified",
          message=f"Rule classified '{class_label}' (conf={confidence}): {blob_name}",
          run_id=run_id, blob_name=blob_name, class_label=class_label,
          confidence=confidence, reason_code=reason_code)


def log_ai_candidate_detected(run_id: str, blob_name: str, reason: str) -> None:
    _emit("ai_candidate_detected",
          message=f"AI candidate detected ({reason}): {blob_name}",
          run_id=run_id, blob_name=blob_name, reason=reason)


def log_ai_skipped(run_id: str, blob_name: str, skip_reason: str) -> None:
    _emit("ai_skipped",
          message=f"AI skipped ({skip_reason}): {blob_name}",
          run_id=run_id, blob_name=blob_name, skip_reason=skip_reason)


def log_ai_called(run_id: str, blob_name: str, provider: str, input_chars: int) -> None:
    _emit("ai_called",
          message=f"AI called via {provider} ({input_chars} chars): {blob_name}",
          run_id=run_id, blob_name=blob_name, provider=provider, input_chars=input_chars)


def log_ai_result_validated(
    run_id: str,
    blob_name: str,
    class_label: str,
    confidence: str,
) -> None:
    _emit("ai_result_validated",
          message=f"AI result validated: class={class_label} conf={confidence} for {blob_name}",
          run_id=run_id, blob_name=blob_name, class_label=class_label, confidence=confidence)


def log_ai_error(run_id: str, blob_name: str, error: str) -> None:
    _emit("ai_error", level="ERROR",
          message=f"AI error for {blob_name}: {error[:120]}",
          run_id=run_id, blob_name=blob_name, error_reason=error)


def log_blob_classified(
    run_id: str,
    blob_name: str,
    class_label: str,
    confidence: str,
    reason_code: str,
    dry_run: bool = False,
    duration_ms: int = 0,
) -> None:
    _emit("blob_classified",
          message=f"Blob classified as '{class_label}' (conf={confidence}): {blob_name}",
          run_id=run_id, blob_name=blob_name, class_label=class_label,
          confidence=confidence, reason_code=reason_code,
          dry_run=dry_run, duration_ms=duration_ms)


def log_blob_error(run_id: str, blob_name: str, stage: str, error: str) -> None:
    _emit("blob_error", level="ERROR",
          message=f"Blob error at '{stage}': {blob_name} – {error[:120]}",
          run_id=run_id, blob_name=blob_name, stage=stage, error_reason=error)


def log_reports_written(run_id: str, local_dir: str, files: list[str]) -> None:
    _emit("report_written",
          message=f"Reports written to {local_dir} ({len(files)} files)",
          run_id=run_id, local_dir=local_dir, files=files)


def log_reports_uploaded(run_id: str, container: str, prefix: str, count: int) -> None:
    _emit("reports_uploaded",
          message=f"Reports uploaded to {container}/{prefix} ({count} files)",
          run_id=run_id, container=container, prefix=prefix, count=count)


def log_warning(run_id: str, message: str, **kwargs: Any) -> None:
    _emit("warning", level="WARNING", run_id=run_id, message=message, **kwargs)


def log_error(run_id: str, message: str, **kwargs: Any) -> None:
    _emit("error", level="ERROR", run_id=run_id, message=message, **kwargs)
