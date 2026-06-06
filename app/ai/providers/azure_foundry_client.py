"""Azure AI Foundry / Azure OpenAI provider adapter – placeholder.

This module bridges the new provider-neutral interface (app/ai/providers/base.py)
and the existing AIFoundryClient in app/ai_foundry_client.py.

Status: Interface ready – real calls delegate to the existing client.
        Activate by setting ENABLE_AI=true and AI_PROVIDER=foundry.
"""

from __future__ import annotations

from typing import Optional

from app.ai.providers.base import (
    AiClassificationRequest,
    AiClassificationResponse,
)


class AzureFoundryProvider:
    """Azure AI Foundry / Azure OpenAI provider.

    Wraps the existing ``AIFoundryClient`` and maps its interface
    to the provider-neutral AiProvider protocol.
    """

    def __init__(self) -> None:
        self._available = False
        self._init_error = ""
        self._client: Optional[object] = None
        self._try_init()

    def _try_init(self) -> None:
        try:
            from app.config import load_config  # noqa: PLC0415
            cfg = load_config()
            if not cfg.ai_foundry_endpoint:
                self._init_error = (
                    "AI_FOUNDRY_ENDPOINT is not set. "
                    "Configure Azure AI Foundry endpoint to use this provider."
                )
                return
            from app.ai_foundry_client import AIFoundryClient  # noqa: PLC0415
            client = AIFoundryClient(cfg)
            if not client.available:
                self._init_error = client.init_error
                return
            self._client = client
            self._available = True
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"AzureFoundry init error: {str(exc)[:300]}"

    @property
    def name(self) -> str:
        return "foundry"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def init_error(self) -> str:
        return self._init_error

    def classify(self, request: AiClassificationRequest) -> AiClassificationResponse:
        """Delegate to the existing AIFoundryClient."""
        if not self._available or self._client is None:
            return AiClassificationResponse(
                status="error",
                class_label="unknown",
                dsgvo="false",
                archive_candidate="false",
                confidence="0",
                readable="true",
                reason_code="foundry_not_available",
                explanation_short=self._init_error[:200],
                input_chars=0,
                provider="foundry",
                error_message=self._init_error,
            )

        try:
            from app.ai_foundry_client import AIFoundryClient  # noqa: PLC0415
            client: AIFoundryClient = self._client  # type: ignore[assignment]
            result = client.classify(
                blob_name=request.blob_name,
                extension=request.extension,
                size_bytes=request.size_bytes,
                rule_class=request.rule_class,
                rule_confidence=request.rule_confidence,
            )
            if result is None:
                return AiClassificationResponse(
                    status="error",
                    class_label="unknown",
                    dsgvo="false",
                    archive_candidate="false",
                    confidence="0",
                    readable="true",
                    reason_code="foundry_no_result",
                    explanation_short="AIFoundryClient returned None",
                    input_chars=request.max_chars,
                    provider="foundry",
                    error_message="AIFoundryClient returned None",
                )
            return AiClassificationResponse(
                status=result.status,
                class_label=result.class_label,
                dsgvo=result.dsgvo,
                archive_candidate=result.archive_candidate,
                confidence=result.confidence,
                readable=result.readable,
                reason_code=result.reason_code,
                explanation_short=result.explanation_short[:200],
                input_chars=result.input_chars,
                provider="foundry",
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)[:300]
            return AiClassificationResponse(
                status="error",
                class_label="unknown",
                dsgvo="false",
                archive_candidate="false",
                confidence="0",
                readable="true",
                reason_code="foundry_exception",
                explanation_short=msg[:200],
                input_chars=0,
                provider="foundry",
                error_message=msg,
            )
