"""Provider-neutral AI interface (Protocol + shared types).

Design:
  - Any AI provider MUST implement AiProvider (duck-typed via Protocol).
  - No concrete provider is imported here.
  - The factory function get_provider() selects the right backend at runtime.

Security:
  - No API keys in this module.
  - Keys are read exclusively from environment variables inside each provider.
  - extract mode never calls get_provider() or any classify() method.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Token estimation (shared utility)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate token count from character count.

    Simple fallback heuristic: ceil(chars / 4).
    NOT exact -- use provider_usage when the API returns it.
    Works for European languages (German/English mix).
    """
    return math.ceil(len(text) / 4)


# ---------------------------------------------------------------------------
# Request / Response types
# ---------------------------------------------------------------------------

@dataclass
class AiClassificationRequest:
    """Input for a single AI classification call."""

    blob_name: str              # max 500 chars, for context only
    extension: str
    size_bytes: int
    rule_class: str             # prior classification from path rules
    rule_confidence: int        # 0-100
    text_for_ai: str            # extracted text snippet - IN-MEMORY only
    max_chars: int = 4_000      # enforce before sending
    route_strategy: str = ""    # extraction strategy (e.g. office_text, plain_text)
    rule_reason_code: str = "no_rule_match"  # rule reason code for prompt context


@dataclass
class AiClassificationResponse:
    """Validated response from an AI provider."""

    status: str                 # classified | error | unsupported
    class_label: str            # br | dsgvo | hr | finance | contract | technical | unknown
    dsgvo: str                  # "true" | "false"
    archive_candidate: str      # "true" | "false"
    confidence: str             # "0".."100"
    readable: str               # "true" | "false"
    reason_code: str
    explanation_short: str      # max 200 chars (for logs/reports)
    input_chars: int
    provider: str               # "groq" | "foundry" | "fake"
    error_message: str = ""
    # Error code (structured, machine-readable)
    ai_error: str = ""          # missing_api_key | invalid_json | schema_validation_failed | rate_limited | provider_error
    # Token tracking - pre-call estimates
    ai_prompt_chars: int = 0
    ai_text_extract_chars: int = 0
    ai_estimated_prompt_tokens: int = 0
    ai_estimated_total_input_tokens: int = 0
    # Token tracking - from provider response (None if not available)
    ai_prompt_tokens: Optional[int] = None
    ai_completion_tokens: Optional[int] = None
    ai_total_tokens: Optional[int] = None
    ai_token_source: str = "estimated"  # "estimated" | "provider_usage"
    # Timing / tracing
    ai_latency_ms: int = 0
    ai_request_id: str = ""
    ai_rate_limit_remaining_requests: str = ""
    ai_rate_limit_remaining_tokens: str = ""
    # Model / prompt metadata
    ai_model: str = ""
    ai_prompt_version: str = ""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AiProvider(Protocol):
    """Interface that all AI provider implementations must satisfy."""

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'groq', 'foundry')."""
        ...

    @property
    def available(self) -> bool:
        """True if the provider is configured and ready for calls."""
        ...

    @property
    def init_error(self) -> str:
        """Non-empty if initialisation failed; reason why unavailable."""
        ...

    def classify(
        self,
        request: AiClassificationRequest,
    ) -> AiClassificationResponse:
        """Perform a single classification.  Never raises; errors returned in response."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(provider_name: str) -> AiProvider:
    """Return the provider instance for *provider_name*.

    Raises ValueError for unknown names.
    Providers are disabled by default - callers must check provider.available.

    Args:
        provider_name: "groq" | "foundry" | "none"
    """
    name = provider_name.lower().strip()
    if name == "groq":
        from app.ai.providers.groq_client import GroqProvider  # noqa: PLC0415
        return GroqProvider()
    if name in ("foundry", "azure_foundry"):
        from app.ai.providers.azure_foundry_client import AzureFoundryProvider  # noqa: PLC0415
        return AzureFoundryProvider()
    raise ValueError(
        f"Unknown AI provider '{provider_name}'. "
        "Choose one of: groq, foundry.  "
        "Set AI_PROVIDER env var and ENABLE_AI=true to activate."
    )