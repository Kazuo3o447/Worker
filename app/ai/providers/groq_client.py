"""Groq AI provider - uses groq SDK, activated only when AI_PROVIDER=groq.

Security rules:
  - API key read ONLY from GROQ_API_KEY environment variable.
  - Key is NEVER logged, printed, or stored in reports.
  - No calls in scan mode or when provider is disabled.
  - Controlled ai_error if key is missing: ai_error=missing_api_key
  - No real calls in unit tests (mock the groq.Groq client).

Prompt version: v1
  - System: classification instructions (no tools, no web search).
  - User: JSON payload with blob metadata + text extract (max AI_MAX_CHARS_PER_FILE chars).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from app.ai.providers.base import (
    AiClassificationRequest,
    AiClassificationResponse,
    estimate_tokens,
)
from app.validation import ALLOWED_CLASS

# ---------------------------------------------------------------------------
# Prompt v1
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_V1 = (
    "Du klassifizierst Dokumente fuer einen Azure Blob Storage Archivierungspiloten.\n"
    "Antworte AUSSCHLIESSLICH mit diesem JSON-Objekt (alle Felder PFLICHT):\n"
    "{\"status\": \"classified\", \"class\": \"<erlaubte_klasse>\", \"dsgvo\": true, "
    "\"archive_candidate\": true, \"confidence\": 80, \"readable\": true, "
    "\"reason_code\": \"ai_content_match\", \"explanation_short\": \"max 200 Zeichen\"}\n"
    "Erlaubte status-Werte: classified, unknown, unreadable.\n"
    "Erlaubte class-Werte: br, dsgvo, hr, finance, contract, technical, unknown, unreadable.\n"
    "confidence: Integer 0-100. dsgvo/archive_candidate/readable: true oder false.\n"
    "reason_code: lowercase_snake_case, kein Leerzeichen.\n"
    "Wenn der Inhalt nicht reicht, nutze class=unknown, status=unknown, confidence=10.\n"
    "Kein erklaerende Text ausserhalb des JSON. Nur das JSON-Objekt zurueckgeben."
)

_ALLOWED_STATUSES = frozenset({"classified", "unknown", "unreadable"})
_REASON_CODE_RE = re.compile(r"^[a-z0-9_]+$")

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_ai_schema(data: object) -> tuple[bool, str]:
    """Validate AI JSON response against the classification schema.

    Only `class` and `confidence` are strictly required.
    All other fields are optional with safe defaults.
    Returns (ok, error_message).
    """
    if not isinstance(data, dict):
        return False, "Response is not a JSON object"

    cls = data.get("class")
    if cls not in ALLOWED_CLASS:
        return False, f"Invalid class: {cls!r}"

    # status: optional – default to 'classified' if missing/invalid
    status = data.get("status")
    if status is not None and status not in _ALLOWED_STATUSES:
        # Try to coerce: if status missing or bad, we set it from class
        data["status"] = "unknown" if cls == "unknown" else "classified"

    if data.get("status") is None:
        data["status"] = "unknown" if cls == "unknown" else "classified"

    try:
        conf = int(data.get("confidence", -1))
        if not (0 <= conf <= 100):
            return False, f"Confidence out of range: {conf}"
    except (ValueError, TypeError):
        return False, f"Invalid confidence: {data.get('confidence')!r}"

    # Bool fields: optional with defaults
    for bool_field, default in (("dsgvo", False), ("archive_candidate", False), ("readable", True)):
        v = data.get(bool_field)
        if v is None:
            data[bool_field] = default
        elif not isinstance(v, bool) and str(v).lower() not in ("true", "false"):
            data[bool_field] = default  # coerce to default on bad value

    explanation = str(data.get("explanation_short", ""))
    if len(explanation) > 200:
        data["explanation_short"] = explanation[:200]

    reason_code = str(data.get("reason_code", ""))
    if reason_code and not _REASON_CODE_RE.match(reason_code):
        # Sanitize: replace spaces/invalid chars with underscore
        data["reason_code"] = re.sub(r"[^a-z0-9_]", "_", reason_code.lower())

    if not data.get("reason_code"):
        data["reason_code"] = "ai_content_match"

    return True, ""


# ---------------------------------------------------------------------------
# GroqProvider
# ---------------------------------------------------------------------------

class GroqProvider:
    """Groq AI provider using the groq SDK (OpenAI-compatible endpoint).

    Disabled by default. Activated only when:
      - ENABLE_AI=true
      - AI_PROVIDER=groq
      - GROQ_API_KEY is set
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = None
        self._available = False
        self._init_error = ""
        self._model = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
        self._temperature = float(os.getenv("AI_TEMPERATURE", "0"))
        self._max_output_tokens = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "300"))
        self._prompt_version = os.getenv("AI_PROMPT_VERSION", "v1")
        self._try_init()

    def _try_init(self) -> None:
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            self._init_error = "GROQ_API_KEY not set"
            return
        self._api_key = key  # never logged
        self._available = True

    @property
    def name(self) -> str:
        return "groq"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def init_error(self) -> str:
        return self._init_error

    def classify(self, request: AiClassificationRequest) -> AiClassificationResponse:
        """Call Groq API for a single classification.

        Never raises - errors are captured in the response object.
        ai_error codes: missing_api_key | invalid_json | schema_validation_failed
                        | rate_limited | provider_error
        """
        if not self._available:
            return self._error_resp("missing_api_key", self._init_error, 0, 0)

        text = request.text_for_ai[:request.max_chars]
        text_chars = len(text)

        # Build user payload (prompt v1 format)
        user_payload = {
            "blob_name": request.blob_name[:500],
            "extension": request.extension,
            "size_bytes": request.size_bytes,
            "route_strategy": request.route_strategy,
            "rule_result": {
                "class": request.rule_class,
                "confidence": request.rule_confidence,
                "reason_code": request.rule_reason_code,
            },
            "text_extract": text,
            "allowed_classes": sorted(ALLOWED_CLASS),
        }
        user_content = json.dumps(user_payload, ensure_ascii=False)

        # Token estimates (before call)
        prompt_content = _SYSTEM_PROMPT_V1 + user_content
        total_prompt_chars = len(prompt_content)
        est_prompt_tokens = estimate_tokens(prompt_content)

        # Import groq SDK (lazy, so tests can patch easily)
        try:
            from groq import Groq  # noqa: PLC0415
            from groq import RateLimitError, APIStatusError  # noqa: PLC0415
        except ImportError:
            return self._error_resp(
                "provider_error", "groq package not installed (pip install groq)",
                text_chars, est_prompt_tokens,
            )

        client = Groq(api_key=self._api_key)

        latency_ms = 0
        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT_V1},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=self._max_output_tokens,
                temperature=self._temperature,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            exc_str = str(exc)[:300]
            # Redact API key from error messages
            safe_msg = exc_str.replace(self._api_key or "", "[REDACTED]")
            exc_type = type(exc).__name__
            # Classify by type name (avoid import errors in except clause)
            if "RateLimitError" in exc_type:
                code = "rate_limited"
            elif "APIStatusError" in exc_type or "APIError" in exc_type:
                code = "provider_error"
            else:
                code = "provider_error"
            return self._error_resp(code, safe_msg, text_chars, est_prompt_tokens, latency_ms)

        # Parse response
        raw = ""
        try:
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            return self._error_resp(
                "invalid_json", f"Cannot parse: {raw[:100]}",
                text_chars, est_prompt_tokens, latency_ms,
            )

        # Schema validation
        ok, err = validate_ai_schema(data)
        if not ok:
            return self._error_resp(
                "schema_validation_failed", err,
                text_chars, est_prompt_tokens, latency_ms,
            )

        # Token usage from provider
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            token_source = "provider_usage"
        else:
            prompt_tokens = est_prompt_tokens
            completion_tokens = None
            total_tokens = est_prompt_tokens
            token_source = "estimated"

        request_id = getattr(response, "id", "") or ""

        return AiClassificationResponse(
            status=str(data.get("status", "classified")),
            class_label=str(data["class"]),
            dsgvo=str(data.get("dsgvo", False)).lower(),
            archive_candidate=str(data.get("archive_candidate", False)).lower(),
            confidence=str(int(data.get("confidence", 50))),
            readable=str(data.get("readable", True)).lower(),
            reason_code=str(data.get("reason_code", "ai_content_match")),
            explanation_short=str(data.get("explanation_short", ""))[:200],
            input_chars=text_chars,
            provider="groq",
            # Token fields
            ai_prompt_chars=total_prompt_chars,
            ai_text_extract_chars=text_chars,
            ai_estimated_prompt_tokens=est_prompt_tokens,
            ai_estimated_total_input_tokens=est_prompt_tokens,
            ai_prompt_tokens=prompt_tokens,
            ai_completion_tokens=completion_tokens,
            ai_total_tokens=total_tokens,
            ai_token_source=token_source,
            ai_latency_ms=latency_ms,
            ai_request_id=request_id,
            ai_model=self._model,
            ai_prompt_version=self._prompt_version,
        )

    def _error_resp(
        self,
        error_code: str,
        msg: str,
        input_chars: int,
        est_tokens: int,
        latency_ms: int = 0,
    ) -> AiClassificationResponse:
        # Never include API key in error messages
        safe_msg = (msg or "").replace(self._api_key or "", "[REDACTED]")
        return AiClassificationResponse(
            status="error",
            class_label="unknown",
            dsgvo="false",
            archive_candidate="false",
            confidence="0",
            readable="true",
            reason_code="ai_error",
            explanation_short=safe_msg[:200],
            input_chars=input_chars,
            provider="groq",
            error_message=safe_msg,
            ai_error=error_code,
            ai_estimated_prompt_tokens=est_tokens,
            ai_estimated_total_input_tokens=est_tokens,
            ai_prompt_tokens=est_tokens if est_tokens > 0 else None,
            ai_token_source="estimated",
            ai_latency_ms=latency_ms,
            ai_model=self._model,
            ai_prompt_version=self._prompt_version,
        )