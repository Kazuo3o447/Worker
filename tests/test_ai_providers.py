"""Tests for provider-neutral AI interface (AP4) and Groq integration.

Tests cover:
- AiClassificationRequest and AiClassificationResponse dataclasses
- AiProvider Protocol compliance
- GroqProvider (no real HTTP calls; mocked groq SDK)
- estimate_tokens utility
- validate_ai_schema
- Token tracking (provider_usage vs estimated)
- AzureFoundryProvider (no real calls; offline tests)

Run with:
    python -m pytest tests/test_ai_providers.py -v
"""

from __future__ import annotations

import json
import os
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest

from app.ai.providers.base import (
    AiClassificationRequest,
    AiClassificationResponse,
    get_provider,
    estimate_tokens,
)
from app.ai.providers.groq_client import GroqProvider, validate_ai_schema
from app.ai.providers.azure_foundry_client import AzureFoundryProvider


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_four_chars_one_token(self):
        assert estimate_tokens("abcd") == 1

    def test_five_chars_two_tokens(self):
        assert estimate_tokens("abcde") == 2

    def test_large_text(self):
        text = "x" * 2000
        # 2000 chars / 4 = 500 tokens
        assert estimate_tokens(text) == 500

    def test_returns_int(self):
        assert isinstance(estimate_tokens("hello world"), int)

    def test_german_text(self):
        text = "Das ist ein Dokument ueber Betriebsrat und Datenschutz."
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert tokens == -(-len(text) // 4)  # ceil division


# ---------------------------------------------------------------------------
# validate_ai_schema
# ---------------------------------------------------------------------------

class TestValidateAiSchema:
    def _valid(self):
        return {
            "status": "classified",
            "class": "contract",
            "dsgvo": True,
            "archive_candidate": True,
            "confidence": 82,
            "readable": True,
            "reason_code": "ai_contract_match",
            "explanation_short": "Contract keywords found",
        }

    def test_valid_json_ok(self):
        ok, err = validate_ai_schema(self._valid())
        assert ok, err

    def test_invalid_class_fails(self):
        data = self._valid()
        data["class"] = "illegal_class_xyz"
        ok, err = validate_ai_schema(data)
        assert not ok
        assert "class" in err.lower() or "Invalid" in err

    def test_invalid_status_gets_coerced(self):
        """Invalid status is coerced to a valid value (not rejected)."""
        data = self._valid()
        data["status"] = "deleted"
        ok, err = validate_ai_schema(data)
        assert ok  # coerced to 'classified'
        assert data["status"] in ("classified", "unknown", "unreadable")

    def test_confidence_too_high_fails(self):
        data = self._valid()
        data["confidence"] = 150
        ok, err = validate_ai_schema(data)
        assert not ok
        assert "confidence" in err.lower() or "range" in err.lower()

    def test_confidence_negative_fails(self):
        data = self._valid()
        data["confidence"] = -1
        ok, err = validate_ai_schema(data)
        assert not ok

    def test_explanation_short_too_long_gets_truncated(self):
        """explanation_short > 200 chars gets truncated to 200, not rejected."""
        data = self._valid()
        data["explanation_short"] = "x" * 201
        ok, err = validate_ai_schema(data)
        assert ok  # truncated to 200
        assert len(data["explanation_short"]) == 200

    def test_explanation_short_200_ok(self):
        data = self._valid()
        data["explanation_short"] = "x" * 200
        ok, err = validate_ai_schema(data)
        assert ok, err

    def test_reason_code_with_spaces_gets_sanitized(self):
        """reason_code with spaces gets sanitized (spaces -> underscores), not rejected."""
        data = self._valid()
        data["reason_code"] = "has spaces"
        ok, err = validate_ai_schema(data)
        assert ok  # sanitized
        assert " " not in data["reason_code"]

    def test_reason_code_snake_case_ok(self):
        data = self._valid()
        data["reason_code"] = "ai_content_match_v1"
        ok, err = validate_ai_schema(data)
        assert ok, err

    def test_not_a_dict_fails(self):
        ok, err = validate_ai_schema("not a dict")
        assert not ok

    def test_all_allowed_classes(self):
        for cls in ("br", "dsgvo", "hr", "finance", "contract", "technical", "unknown", "unreadable"):
            data = self._valid()
            data["class"] = cls
            ok, err = validate_ai_schema(data)
            assert ok, f"Class {cls!r} should be valid, got: {err}"


# ---------------------------------------------------------------------------
# AiClassificationRequest
# ---------------------------------------------------------------------------

class TestAiClassificationRequest:
    def test_instantiation(self):
        req = AiClassificationRequest(
            blob_name="docs/contract.docx",
            extension=".docx",
            size_bytes=10240,
            rule_class="unknown",
            rule_confidence=40,
            text_for_ai="Some document text.",
            max_chars=4000,
        )
        assert req.blob_name == "docs/contract.docx"
        assert req.text_for_ai == "Some document text."
        assert req.max_chars == 4000

    def test_route_strategy_default_empty(self):
        req = AiClassificationRequest(
            blob_name="f.txt", extension=".txt", size_bytes=10,
            rule_class="unknown", rule_confidence=30, text_for_ai="x",
        )
        assert req.route_strategy == ""
        assert req.rule_reason_code == "no_rule_match"

    def test_all_required_fields_present(self):
        field_names = {f.name for f in fields(AiClassificationRequest)}
        required = {"blob_name", "extension", "size_bytes", "rule_class", "rule_confidence", "text_for_ai"}
        assert required.issubset(field_names)


# ---------------------------------------------------------------------------
# AiClassificationResponse
# ---------------------------------------------------------------------------

class TestAiClassificationResponse:
    def test_has_token_fields(self):
        field_names = {f.name for f in fields(AiClassificationResponse)}
        for field_name in (
            "ai_prompt_chars", "ai_text_extract_chars",
            "ai_estimated_prompt_tokens", "ai_prompt_tokens",
            "ai_completion_tokens", "ai_total_tokens",
            "ai_token_source", "ai_latency_ms", "ai_request_id",
            "ai_error", "ai_model", "ai_prompt_version",
        ):
            assert field_name in field_names, f"Missing field: {field_name}"

    def test_default_token_source_estimated(self):
        resp = AiClassificationResponse(
            status="classified", class_label="contract",
            dsgvo="false", archive_candidate="false",
            confidence="80", readable="true",
            reason_code="test", explanation_short="ok",
            input_chars=100, provider="groq",
        )
        assert resp.ai_token_source == "estimated"
        assert resp.ai_prompt_tokens is None
        assert resp.ai_completion_tokens is None


# ---------------------------------------------------------------------------
# GroqProvider (offline / no real API calls)
# ---------------------------------------------------------------------------

class TestGroqProvider:
    def test_provider_name(self):
        prov = GroqProvider()
        assert prov.name == "groq"

    def test_unavailable_without_api_key(self):
        """Without GROQ_API_KEY env, provider should be unavailable."""
        with patch.dict(os.environ, {}, clear=True):
            prov = GroqProvider()
            assert prov.available is False
            assert prov.init_error  # non-empty error message

    def test_available_with_api_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-abc123"}):
            prov = GroqProvider()
            assert prov.available is True
            assert not prov.init_error

    def test_classify_missing_api_key_returns_error_code(self):
        """classify() with no key returns ai_error=missing_api_key."""
        with patch.dict(os.environ, {}, clear=True):
            prov = GroqProvider()
            req = AiClassificationRequest(
                blob_name="file.txt", extension=".txt", size_bytes=100,
                rule_class="unknown", rule_confidence=40, text_for_ai="hello",
            )
            resp = prov.classify(req)
            assert resp.status == "error"
            assert resp.class_label == "unknown"
            assert resp.provider == "groq"
            assert resp.ai_error == "missing_api_key"

    def test_classify_does_not_log_api_key(self):
        """classify() error message must not contain the actual API key value."""
        secret = "super-secret-key-xyz-99887766"
        with patch.dict(os.environ, {}, clear=True):
            prov = GroqProvider()
            prov._api_key = secret  # inject secret to test redaction
            req = AiClassificationRequest(
                blob_name="file.txt", extension=".txt", size_bytes=100,
                rule_class="unknown", rule_confidence=40, text_for_ai="hello",
            )
            resp = prov.classify(req)
            assert secret not in (resp.error_message or "")
            assert secret not in (resp.explanation_short or "")

    def test_mock_successful_classify_with_usage(self):
        """With a mocked groq client, classify() returns structured response with provider_usage tokens."""
        valid_content = json.dumps({
            "status": "classified",
            "class": "contract",
            "dsgvo": True,
            "archive_candidate": True,
            "confidence": 82,
            "readable": True,
            "reason_code": "ai_contract_match",
            "explanation_short": "Contract structure detected",
        })

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 150
        mock_usage.completion_tokens = 40
        mock_usage.total_tokens = 190

        mock_message = MagicMock()
        mock_message.content = valid_content

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.id = "req-abc123"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            prov = GroqProvider()
            req = AiClassificationRequest(
                blob_name="contract.txt", extension=".txt", size_bytes=500,
                rule_class="unknown", rule_confidence=40,
                text_for_ai="This agreement is entered into by...",
            )
            with patch("groq.Groq", return_value=mock_client):
                resp = prov.classify(req)

        assert resp.status == "classified"
        assert resp.class_label == "contract"
        assert resp.confidence == "82"
        assert resp.provider == "groq"
        # Token fields from provider
        assert resp.ai_prompt_tokens == 150
        assert resp.ai_completion_tokens == 40
        assert resp.ai_total_tokens == 190
        assert resp.ai_token_source == "provider_usage"
        assert resp.ai_request_id == "req-abc123"

    def test_mock_classify_without_usage_uses_estimated(self):
        """When usage is None in response, estimated tokens are used."""
        valid_content = json.dumps({
            "status": "classified",
            "class": "hr",
            "dsgvo": True,
            "archive_candidate": True,
            "confidence": 70,
            "readable": True,
            "reason_code": "ai_content_match",
            "explanation_short": "HR related content",
        })

        mock_message = MagicMock()
        mock_message.content = valid_content

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_response.id = ""

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            prov = GroqProvider()
            req = AiClassificationRequest(
                blob_name="personal_file.txt", extension=".txt", size_bytes=300,
                rule_class="unknown", rule_confidence=35,
                text_for_ai="Employee record dated 2024",
            )
            with patch("groq.Groq", return_value=mock_client):
                resp = prov.classify(req)

        assert resp.class_label == "hr"
        assert resp.ai_token_source == "estimated"
        assert resp.ai_estimated_prompt_tokens > 0
        # With no usage, prompt_tokens falls back to estimated
        assert resp.ai_prompt_tokens == resp.ai_estimated_prompt_tokens

    def test_mock_classify_invalid_json_error(self):
        """When AI returns invalid JSON, ai_error=invalid_json."""
        mock_message = MagicMock()
        mock_message.content = "this is not json at all"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            prov = GroqProvider()
            req = AiClassificationRequest(
                blob_name="file.txt", extension=".txt", size_bytes=100,
                rule_class="unknown", rule_confidence=30, text_for_ai="text",
            )
            with patch("groq.Groq", return_value=mock_client):
                resp = prov.classify(req)

        assert resp.ai_error == "invalid_json"
        assert resp.status == "error"

    def test_mock_classify_schema_validation_failed(self):
        """When AI returns valid JSON but fails schema: ai_error=schema_validation_failed."""
        bad_content = json.dumps({
            "status": "classified",
            "class": "INVALID_CLASS_NAME",  # not in allowed classes
            "confidence": 50,
            "dsgvo": True,
            "archive_candidate": False,
            "readable": True,
        })

        mock_message = MagicMock()
        mock_message.content = bad_content

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            prov = GroqProvider()
            req = AiClassificationRequest(
                blob_name="file.txt", extension=".txt", size_bytes=100,
                rule_class="unknown", rule_confidence=30, text_for_ai="text",
            )
            with patch("groq.Groq", return_value=mock_client):
                resp = prov.classify(req)

        assert resp.ai_error == "schema_validation_failed"
        assert resp.status == "error"


# ---------------------------------------------------------------------------
# AzureFoundryProvider (offline)
# ---------------------------------------------------------------------------

class TestAzureFoundryProvider:
    def test_unavailable_without_endpoint(self):
        """Without AI_FOUNDRY_ENDPOINT env, provider should gracefully report unavailable."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_FOUNDRY_ENDPOINT", None)
            prov = AzureFoundryProvider()
            assert prov.available is False
            assert prov.init_error

    def test_classify_returns_error_without_endpoint(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_FOUNDRY_ENDPOINT", None)
            prov = AzureFoundryProvider()
            req = AiClassificationRequest(
                blob_name="file.docx", extension=".docx", size_bytes=200,
                rule_class="unknown", rule_confidence=45, text_for_ai="some content",
            )
            resp = prov.classify(req)
            assert resp.status == "error"
            assert resp.provider in ("azure_foundry", "foundry")


# ---------------------------------------------------------------------------
# get_provider factory
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_get_groq_provider(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            prov = get_provider("groq")
            assert isinstance(prov, GroqProvider)

    def test_get_azure_foundry_provider(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_FOUNDRY_ENDPOINT", None)
            prov = get_provider("foundry")
            assert isinstance(prov, AzureFoundryProvider)

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError):
            get_provider("nonexistent_provider_xyz")
