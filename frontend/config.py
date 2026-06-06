"""Frontend configuration – read-only access to Azure reports container.

Loaded from environment variables. No CLI args in the dashboard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class FrontendConfig:
    auth_mode: str           # device_code | default | connection_string
    storage_account: str
    source_container: str
    report_container: str
    quarantine_container: str
    worker_name: str
    worker_version: str
    default_prefix: str
    default_max_files: int
    enable_ai: bool
    ai_provider: str
    ai_model: str
    ai_prompt_version: str
    ai_max_calls_per_run: int
    pdf_max_pages: int
    ai_token_estimation_safety_factor: float
    connection_string: str   # optional – emergency access; never shown in UI

    @property
    def account_url(self) -> str:
        return f"https://{self.storage_account}.blob.core.windows.net"


def load_frontend_config() -> FrontendConfig:
    def _bool(v: str, default: bool = False) -> bool:
        return str(v).lower() not in ("false", "0", "no")

    return FrontendConfig(
        auth_mode=os.environ.get("AUTH_MODE", "default"),
        storage_account=os.environ.get("AZURE_STORAGE_ACCOUNT", "stgemaclasspilot001"),
        source_container=os.environ.get("SOURCE_CONTAINER", "cool-stage-test"),
        report_container=os.environ.get("REPORT_CONTAINER", "reports"),
        quarantine_container=os.environ.get("QUARANTINE_CONTAINER", "quarantine-test"),
        worker_name=os.environ.get("WORKER_NAME", "Andre3000"),
        worker_version=os.environ.get("WORKER_VERSION", "pilot-v0.1"),
        default_prefix=os.environ.get("DEFAULT_PREFIX", ""),
        default_max_files=int(os.environ.get("DEFAULT_MAX_FILES", "50")),
        enable_ai=_bool(os.environ.get("ENABLE_AI", "false")),
        ai_provider=os.environ.get("AI_PROVIDER", "none"),
        ai_model=os.environ.get("AI_MODEL", ""),
        ai_prompt_version=os.environ.get("AI_PROMPT_VERSION", "v1"),
        ai_max_calls_per_run=int(os.environ.get("AI_MAX_CALLS_PER_RUN", "20")),
        pdf_max_pages=int(os.environ.get("PDF_MAX_PAGES", "3")),
        ai_token_estimation_safety_factor=float(os.environ.get("AI_TOKEN_ESTIMATION_SAFETY_FACTOR", "1.5")),
        connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING", ""),
    )
