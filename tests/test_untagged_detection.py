"""Tests for untagged blob detection, force mode, dry-run behaviour, and JSONL event format."""

from __future__ import annotations

import json

import pytest

from app.classifier_rules import should_process_blob
from app.logging_utils import (
    _emit,
    enable_event_buffering,
    get_event_buffer_bytes,
    clear_event_buffer,
    log_blob_classified,
    log_blob_error,
    log_blob_seen,
    log_blob_skipped,
)
from app.models import BlobRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_blob(blob_name: str = "test/file.docx", tags: dict | None = None) -> BlobRecord:
    return BlobRecord(
        blob_name=blob_name,
        container="cool-stage-test",
        size_bytes=1024,
        extension=".docx",
        last_modified=None,
        etag='"abc"',
        existing_tags=tags or {},
        existing_status_before=(tags or {}).get("status", ""),
    )


# ---------------------------------------------------------------------------
# Untagged detection via should_process_blob
# ---------------------------------------------------------------------------

class TestUntaggedDetection:
    """Test detection of blobs that need processing in various tag states."""

    def test_completely_untagged_blob_is_detected(self):
        blob = _make_blob(tags={})
        ok, reason = should_process_blob(blob.existing_tags)
        assert ok is True
        assert "none" in reason

    def test_blob_with_status_new_is_detected(self):
        blob = _make_blob(tags={"status": "new"})
        ok, _ = should_process_blob(blob.existing_tags)
        assert ok is True

    def test_blob_with_status_error_is_detected_for_retry(self):
        blob = _make_blob(tags={"status": "error"})
        ok, reason = should_process_blob(blob.existing_tags)
        assert ok is True
        assert "error" in reason

    def test_blob_with_status_classified_is_skipped(self):
        blob = _make_blob(tags={"status": "classified"})
        ok, reason = should_process_blob(blob.existing_tags)
        assert ok is False
        assert "classified" in reason

    def test_blob_with_status_skipped_is_skipped(self):
        blob = _make_blob(tags={"status": "skipped"})
        ok, _ = should_process_blob(blob.existing_tags)
        assert ok is False

    def test_blob_with_status_unreadable_is_skipped(self):
        blob = _make_blob(tags={"status": "unreadable"})
        ok, _ = should_process_blob(blob.existing_tags)
        assert ok is False

    def test_blob_with_other_tags_but_no_status_is_detected(self):
        blob = _make_blob(tags={"dsgvo": "true", "class": "hr"})
        ok, _ = should_process_blob(blob.existing_tags)
        assert ok is True  # no 'status' tag → detect as untagged

    def test_empty_string_status_is_detected(self):
        blob = _make_blob(tags={"status": ""})
        ok, _ = should_process_blob(blob.existing_tags)
        assert ok is True  # empty string is treated as missing


# ---------------------------------------------------------------------------
# Force mode
# ---------------------------------------------------------------------------

class TestForceMode:
    """force=True must override final statuses."""

    def test_force_processes_classified(self):
        blob = _make_blob(tags={"status": "classified"})
        ok, reason = should_process_blob(blob.existing_tags, force=True)
        assert ok is True
        assert "force=true" in reason

    def test_force_processes_skipped(self):
        blob = _make_blob(tags={"status": "skipped"})
        ok, _ = should_process_blob(blob.existing_tags, force=True)
        assert ok is True

    def test_force_processes_unreadable(self):
        blob = _make_blob(tags={"status": "unreadable"})
        ok, _ = should_process_blob(blob.existing_tags, force=True)
        assert ok is True

    def test_force_false_still_skips_classified(self):
        blob = _make_blob(tags={"status": "classified"})
        ok, _ = should_process_blob(blob.existing_tags, force=False)
        assert ok is False

    def test_force_does_not_affect_untagged(self):
        # Untagged blobs are always processed regardless of force
        blob = _make_blob(tags={})
        ok_no_force, _ = should_process_blob(blob.existing_tags, force=False)
        ok_force, _ = should_process_blob(blob.existing_tags, force=True)
        assert ok_no_force is True
        assert ok_force is True

    def test_force_with_error_status_still_processes(self):
        blob = _make_blob(tags={"status": "error"})
        ok, _ = should_process_blob(blob.existing_tags, force=True)
        assert ok is True


# ---------------------------------------------------------------------------
# Dry-run behaviour (detection is unaffected by dry_run)
# ---------------------------------------------------------------------------

class TestDryRunDetection:
    """dry_run only affects writes, not detection. should_process_blob has no dry_run param."""

    def test_detection_same_with_or_without_force(self):
        # dry_run is a downstream concern; detection always based on tags only
        blob = _make_blob(tags={"status": "new"})
        ok, _ = should_process_blob(blob.existing_tags, force=False)
        assert ok is True

    def test_classified_skipped_regardless_of_force_false(self):
        blob = _make_blob(tags={"status": "classified"})
        ok, _ = should_process_blob(blob.existing_tags, force=False)
        assert ok is False


# ---------------------------------------------------------------------------
# Mixed batch detection
# ---------------------------------------------------------------------------

class TestBatchDetection:
    """Simulate processing a list of blobs and counting which need work."""

    def _count_processable(self, blobs: list[BlobRecord], force: bool = False) -> int:
        return sum(1 for b in blobs if should_process_blob(b.existing_tags, force=force)[0])

    def test_mixed_batch_correct_count(self):
        blobs = [
            _make_blob(tags={}),                          # untagged → process
            _make_blob(tags={"status": "new"}),           # process
            _make_blob(tags={"status": "error"}),         # process (retry)
            _make_blob(tags={"status": "classified"}),    # skip
            _make_blob(tags={"status": "skipped"}),       # skip
            _make_blob(tags={"status": "unreadable"}),    # skip
        ]
        assert self._count_processable(blobs) == 3

    def test_mixed_batch_with_force(self):
        blobs = [
            _make_blob(tags={"status": "classified"}),
            _make_blob(tags={"status": "skipped"}),
            _make_blob(tags={"status": "unreadable"}),
        ]
        assert self._count_processable(blobs, force=True) == 3

    def test_all_classified_batch_nothing_to_do(self):
        blobs = [_make_blob(tags={"status": "classified"}) for _ in range(5)]
        assert self._count_processable(blobs) == 0

    def test_all_untagged_batch_all_processed(self):
        blobs = [_make_blob(tags={}) for _ in range(5)]
        assert self._count_processable(blobs) == 5


# ---------------------------------------------------------------------------
# run-events.jsonl format  (in-memory buffer)
# ---------------------------------------------------------------------------

class TestRunEventsJsonlFormat:
    """Verify that buffered log events are valid JSON Lines with required fields."""

    def setup_method(self):
        enable_event_buffering()
        clear_event_buffer()

    def _events(self) -> list[dict]:
        data = get_event_buffer_bytes()
        events = []
        for line in data.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def test_events_are_valid_json_lines(self):
        _emit("test_event", run_id="test123")
        _emit("test_event2", run_id="test123")
        events = self._events()
        assert len(events) == 2

    def test_each_event_has_required_fields(self):
        _emit("blob_seen", run_id="test123", blob_name="folder/file.docx")
        events = self._events()
        assert len(events) == 1
        e = events[0]
        assert "timestamp" in e
        assert "level" in e
        assert "event" in e
        assert "message" in e
        assert e["event"] == "blob_seen"

    def test_log_blob_classified_event_format(self):
        log_blob_classified(
            "run001", "docs/vertrag.pdf", "contract", "75", "path_rule_contract",
            dry_run=False, duration_ms=12,
        )
        events = self._events()
        assert len(events) == 1
        e = events[0]
        assert e["event"] == "blob_classified"
        assert e["class_label"] == "contract"
        assert e["confidence"] == "75"
        assert e["duration_ms"] == 12
        assert e["dry_run"] is False

    def test_log_blob_error_has_error_level(self):
        log_blob_error("run001", "file.docx", "set_tags", "Permission denied")
        events = self._events()
        assert events[0]["level"] == "ERROR"
        assert events[0]["event"] == "blob_error"

    def test_no_buffer_does_not_crash(self):
        """Logging before enable_event_buffering() should only go to stdout."""
        # Fresh module state: call without buffering → just stdout, no crash
        clear_event_buffer()
        log_blob_seen("run_x", "file.txt", 1024)
        log_blob_skipped("run_x", "file.txt", "already_classified")

    def test_event_buffer_contains_all_expected_events(self):
        log_blob_seen("r1", "file.docx", 512)
        log_blob_skipped("r1", "file.docx", "classified")
        log_blob_classified("r1", "hr/file.docx", "hr", "80", "path_rule_hr")
        log_blob_error("r1", "bad.docx", "set_tags", "403 Forbidden")
        events = self._events()
        event_types = [e["event"] for e in events]
        assert "blob_seen" in event_types
        assert "blob_skipped" in event_types
        assert "blob_classified" in event_types
        assert "blob_error" in event_types

    def test_timestamps_are_iso_format(self):
        _emit("ping", run_id="r1")
        events = self._events()
        ts = events[0]["timestamp"]
        from datetime import datetime
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

    def test_get_event_buffer_bytes_empty_when_no_events(self):
        clear_event_buffer()
        data = get_event_buffer_bytes()
        assert data == b""

    def test_clear_event_buffer_resets(self):
        _emit("ping", run_id="r1")
        assert get_event_buffer_bytes() != b""
        clear_event_buffer()
        assert get_event_buffer_bytes() == b""
