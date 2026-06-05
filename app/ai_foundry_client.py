"""Azure AI Foundry client – optional, activated only when AI_PROVIDER=foundry.

Design principles:
  - No Mock provider in the production path
  - Never logs API keys or secrets
  - Errors are captured and returned, never raised to caller
  - Strict JSON response parsing and validation
  - Minimal token usage: only blob metadata, no file content in v0
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.validation import ALLOWED_CLASS, ALLOWED_STATUS, validate_confidence

if TYPE_CHECKING:
    from app.config import Config

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "Du bist ein Klassifizierungsassistent für Dokumentenmanagement bei GEMA. "
    "Analysiere die gegebenen Datei-Metadaten und klassifiziere die Datei. "
    "Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt, kein erklärender Text davor oder danach. "
    "Halte dich strikt an das vorgegebene Schema."
)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class AIClassificationResult:
    status: str
    class_label: str
    dsgvo: str               # "true" | "false"
    archive_candidate: str   # "true" | "false"
    confidence: str          # "0".."100"
    readable: str            # "true" | "false"
    reason_code: str
    explanation_short: str   # max 200 chars, for logs/reports
    input_chars: int
    provider: str = "foundry"


# ---------------------------------------------------------------------------
# Input builder – minimal, token-saving
# ---------------------------------------------------------------------------

def _build_input(
    blob_name: str,
    extension: str,
    size_bytes: int,
    rule_class: str,
    rule_confidence: int,
    max_chars: int,
) -> str:
    """Build minimal structured input for the AI – no file content in v0."""
    payload = {
        "blob_name": blob_name[:500],
        "extension": extension,
        "size_bytes": size_bytes,
        "rule_classification": {
            "class": rule_class,
            "confidence": rule_confidence,
        },
        "task": (
            "Klassifiziere die Datei anhand von Name/Pfad/Extension. "
            "Antworte mit JSON: {status, class, dsgvo, archive_candidate, "
            "confidence, readable, reason_code, explanation_short}"
        ),
    }
    text = json.dumps(payload, ensure_ascii=False)
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

def _validate_response(data: dict) -> tuple[bool, str]:
    if data.get("class") not in ALLOWED_CLASS:
        return False, f"invalid class: {data.get('class')!r}"
    if data.get("status") not in ALLOWED_STATUS:
        return False, f"invalid status: {data.get('status')!r}"
    if not validate_confidence(str(data.get("confidence", ""))):
        return False, f"invalid confidence: {data.get('confidence')!r}"
    for bool_field in ("dsgvo", "archive_candidate", "readable"):
        v = str(data.get(bool_field, "")).lower()
        if v not in ("true", "false"):
            return False, f"invalid bool field {bool_field}={v!r}"
    return True, ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class AIFoundryClient:
    """Thin client for Azure AI Foundry / Azure OpenAI chat completions.

    Initialisation failures are stored; callers check ``available`` before use.
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self._client = None
        self._available = False
        self._init_error = ""
        self._try_init()

    def _try_init(self) -> None:
        try:
            from openai import AzureOpenAI  # optional dependency
        except ImportError:
            self._init_error = "openai package not installed (pip install openai)"
            return

        if not self.config.ai_foundry_endpoint:
            self._init_error = "AI_FOUNDRY_ENDPOINT not set"
            return
        if not self.config.ai_foundry_model_deployment:
            self._init_error = "AI_FOUNDRY_MODEL_DEPLOYMENT not set"
            return

        try:
            api_version = self.config.ai_foundry_api_version or "2024-02-01"
            if self.config.ai_foundry_api_key:
                self._client = AzureOpenAI(
                    api_key=self.config.ai_foundry_api_key,
                    azure_endpoint=self.config.ai_foundry_endpoint,
                    api_version=api_version,
                )
            else:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                credential = DefaultAzureCredential()
                token_provider = get_bearer_token_provider(
                    credential, "https://cognitiveservices.azure.com/.default"
                )
                self._client = AzureOpenAI(
                    azure_ad_token_provider=token_provider,
                    azure_endpoint=self.config.ai_foundry_endpoint,
                    api_version=api_version,
                )
            self._available = True
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"Client init failed: {str(exc)[:200]}"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def init_error(self) -> str:
        return self._init_error

    def classify(
        self,
        blob_name: str,
        extension: str,
        size_bytes: int,
        rule_class: str,
        rule_confidence: int,
    ) -> Optional[AIClassificationResult]:
        """Call AI Foundry and return a validated result, or None on error.

        Raises RuntimeError with a descriptive message on failure so the
        caller can log and count the error without crashing the run.
        """
        if not self._available or not self._client:
            raise RuntimeError(
                f"AI client not available: {self._init_error or 'unknown reason'}"
            )

        input_text = _build_input(
            blob_name, extension, size_bytes,
            rule_class, rule_confidence,
            self.config.ai_max_chars_per_file,
        )
        input_chars = len(input_text)

        try:
            response = self._client.chat.completions.create(
                model=self.config.ai_foundry_model_deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
                max_tokens=300,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"AI API call failed: {str(exc)[:200]}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AI response not valid JSON: {raw[:100]}") from exc

        valid, err = _validate_response(data)
        if not valid:
            raise RuntimeError(f"AI response validation failed: {err}") from None

        return AIClassificationResult(
            status=str(data["status"]),
            class_label=str(data["class"]),
            dsgvo=str(data.get("dsgvo", "false")).lower(),
            archive_candidate=str(data.get("archive_candidate", "false")).lower(),
            confidence=str(int(data["confidence"])),
            readable=str(data.get("readable", "true")).lower(),
            reason_code=str(data.get("reason_code", "llm_path_match")),
            explanation_short=str(data.get("explanation_short", ""))[:200],
            input_chars=input_chars,
        )
