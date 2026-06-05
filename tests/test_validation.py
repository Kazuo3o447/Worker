"""Tests for app/validation.py – tag and metadata validation."""

from __future__ import annotations

import pytest

from app.validation import (
    ALLOWED_BOOL,
    ALLOWED_CLASS,
    ALLOWED_STATUS,
    validate_confidence,
    validate_metadata,
    validate_tags,
)


# ---------------------------------------------------------------------------
# validate_confidence
# ---------------------------------------------------------------------------

class TestValidateConfidence:
    def test_zero_is_valid(self):
        assert validate_confidence("0") is True

    def test_hundred_is_valid(self):
        assert validate_confidence("100") is True

    def test_midrange_valid(self):
        assert validate_confidence("75") is True

    def test_above_100_invalid(self):
        assert validate_confidence("101") is False

    def test_negative_invalid(self):
        assert validate_confidence("-1") is False

    def test_non_numeric_invalid(self):
        assert validate_confidence("abc") is False

    def test_empty_invalid(self):
        assert validate_confidence("") is False

    def test_float_string_invalid(self):
        assert validate_confidence("75.5") is False

    def test_none_invalid(self):
        assert validate_confidence(None) is False  # type: ignore


# ---------------------------------------------------------------------------
# validate_tags – valid cases
# ---------------------------------------------------------------------------

class TestValidateTagsValid:
    def test_all_required_tags_valid(self):
        tags = {
            "status": "classified",
            "class": "finance",
            "dsgvo": "false",
            "archive_candidate": "true",
            "confidence": "80",
            "readable": "true",
            "llm_used": "false",
        }
        valid, errors = validate_tags(tags)
        assert errors == []
        assert valid == tags

    def test_status_all_allowed_values(self):
        for s in ALLOWED_STATUS:
            valid, errors = validate_tags({"status": s})
            assert "status" in valid, f"Status '{s}' should be valid (key 'status' missing from result)"
            assert valid["status"] == s
            assert not errors

    def test_class_all_allowed_values(self):
        for c in ALLOWED_CLASS:
            valid, errors = validate_tags({"class": c})
            assert "class" in valid, f"Class '{c}' should be valid"
            assert not errors

    def test_bool_tags_true_false(self):
        for key in ("dsgvo", "archive_candidate", "readable", "llm_used"):
            for val in ("true", "false"):
                valid, errors = validate_tags({key: val})
                assert key in valid
                assert not errors

    def test_unknown_tag_key_passes_through(self):
        # Custom / future tag keys without a validator should pass value-through
        valid, errors = validate_tags({"custom_tag": "some_value"})
        assert "custom_tag" in valid
        assert not errors


# ---------------------------------------------------------------------------
# validate_tags – invalid cases
# ---------------------------------------------------------------------------

class TestValidateTagsInvalid:
    def test_invalid_status_value(self):
        _, errors = validate_tags({"status": "processing"})
        assert errors

    def test_invalid_class_value(self):
        _, errors = validate_tags({"class": "office"})
        assert errors

    def test_invalid_dsgvo_value(self):
        _, errors = validate_tags({"dsgvo": "yes"})
        assert errors

    def test_invalid_confidence_above_100(self):
        _, errors = validate_tags({"confidence": "200"})
        assert errors

    def test_invalid_confidence_negative(self):
        _, errors = validate_tags({"confidence": "-5"})
        assert errors

    def test_key_with_space_rejected(self):
        valid, errors = validate_tags({"my tag": "value"})
        assert "my tag" not in valid
        assert errors

    def test_value_too_long_rejected(self):
        _, errors = validate_tags({"status": "x" * 300})
        assert errors

    def test_non_ascii_key_rejected(self):
        valid, errors = validate_tags({"ünlaut": "value"})
        assert "ünlaut" not in valid
        assert errors

    def test_too_many_tags_warns(self):
        tags = {f"tag_{i}": "value" for i in range(12)}
        _, errors = validate_tags(tags)
        assert any("too many" in e.lower() for e in errors)

    def test_invalid_tag_excluded_from_valid(self):
        valid, errors = validate_tags({"status": "WRONG", "class": "finance"})
        assert "status" not in valid
        assert "class" in valid
        assert errors


# ---------------------------------------------------------------------------
# needs_ai tag validation
# ---------------------------------------------------------------------------

class TestNeedsAiTag:
    def test_needs_ai_true_valid(self):
        valid, errors = validate_tags({"needs_ai": "true"})
        assert "needs_ai" in valid
        assert not errors

    def test_needs_ai_false_valid(self):
        valid, errors = validate_tags({"needs_ai": "false"})
        assert "needs_ai" in valid
        assert not errors

    def test_needs_ai_invalid_value(self):
        valid, errors = validate_tags({"needs_ai": "yes"})
        assert "needs_ai" not in valid
        assert errors

    def test_needs_ai_with_full_tag_set_within_limit(self):
        # 8 tags total – still under Azure limit of 10
        tags = {
            "status": "classified",
            "class": "finance",
            "dsgvo": "false",
            "archive_candidate": "true",
            "confidence": "80",
            "readable": "true",
            "llm_used": "false",
            "needs_ai": "false",
        }
        valid, errors = validate_tags(tags)
        assert errors == []
        assert "needs_ai" in valid


# ---------------------------------------------------------------------------
# validate_metadata – valid cases
# ---------------------------------------------------------------------------

class TestValidateMetadataValid:
    def test_standard_metadata_passes(self):
        meta = {
            "original_path": "folder/file.docx",
            "classifier_version": "pilot-v0.1",
            "model_name": "rules-v0",
            "reason_code": "path_rule_finance",
            "processed_at": "2024-01-01T12:00:00+00:00",
        }
        valid, errors = validate_metadata(meta)
        assert errors == []
        assert valid == meta

    def test_value_is_sanitised(self):
        meta = {"reason": "hello\x00world"}  # null byte
        valid, errors = validate_metadata(meta)
        assert valid["reason"] == "helloworld"  # null byte stripped

    def test_uppercase_key_auto_lowercased(self):
        meta = {"OriginalPath": "some/path"}
        valid, errors = validate_metadata(meta)
        assert "originalpath" in valid
        assert errors  # warns about auto-correction

    def test_long_value_truncated(self):
        meta = {"notes": "x" * 10000}
        valid, errors = validate_metadata(meta)
        assert len(valid["notes"]) <= 8192
        assert any("truncated" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# validate_metadata – invalid cases
# ---------------------------------------------------------------------------

class TestValidateMetadataInvalid:
    def test_key_with_space_rejected(self):
        valid, errors = validate_metadata({"my key": "value"})
        assert "my key" not in valid
        assert errors

    def test_empty_key_skipped(self):
        valid, errors = validate_metadata({"": "value"})
        assert "" not in valid
        assert errors

    def test_non_ascii_key_rejected(self):
        valid, errors = validate_metadata({"schüssel": "value"})
        assert "schüssel" not in valid
        assert errors

    def test_valid_keys_pass_alongside_invalid(self):
        valid, errors = validate_metadata({"good_key": "ok", "bad key": "nok"})
        assert "good_key" in valid
        assert "bad key" not in valid


# ---------------------------------------------------------------------------
# Allowed value set completeness
# ---------------------------------------------------------------------------

class TestAllowedSets:
    def test_allowed_status_completeness(self):
        expected = {"new", "classified", "error", "unreadable", "skipped"}
        assert ALLOWED_STATUS == expected

    def test_allowed_class_includes_dsgvo(self):
        assert "dsgvo" in ALLOWED_CLASS

    def test_allowed_class_completeness(self):
        expected = {"br", "dsgvo", "hr", "finance", "contract", "technical", "unknown", "unreadable"}
        assert ALLOWED_CLASS == expected

    def test_allowed_bool(self):
        assert ALLOWED_BOOL == {"true", "false"}
