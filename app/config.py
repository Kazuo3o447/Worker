"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

AUTH_MODES = frozenset({"connection_string", "default", "device_code"})


def _parse_bool(value: str, default: bool = True) -> bool:
    return str(value).lower() not in ("false", "0", "no")


@dataclass
class Config:
    # Azure Storage
    storage_account: str
    source_container: str
    report_container: str
    quarantine_container: str
    worker_version: str
    default_max_files: int
    default_prefix: Optional[str]
    # Auth
    auth_mode: str
    connection_string: Optional[str]  # never logged
    # Reports
    upload_reports: bool
    dashboard_report_source: str     # azure | local
    # AI
    enable_ai: bool
    ai_provider: str                 # none | foundry
    ai_policy_mode: str              # conservative | balanced
    ai_max_calls_per_run: int
    ai_max_chars_per_file: int
    ai_min_confidence_threshold: int
    ai_foundry_endpoint: Optional[str]
    ai_foundry_model_deployment: Optional[str]
    ai_foundry_api_version: Optional[str]
    ai_foundry_api_key: Optional[str]  # never logged

    @property
    def account_url(self) -> str:
        return f"https://{self.storage_account}.blob.core.windows.net"


def load_config() -> Config:
    """Build Config from environment variables with GEMA pilot defaults."""
    auth_mode = os.getenv("AUTH_MODE", "device_code").lower()
    if auth_mode not in AUTH_MODES:
        auth_mode = "device_code"
    return Config(
        storage_account=os.getenv("AZURE_STORAGE_ACCOUNT", "stgemaclasspilot001"),
        source_container=os.getenv("SOURCE_CONTAINER", "cool-stage-test"),
        report_container=os.getenv("REPORT_CONTAINER", "reports"),
        quarantine_container=os.getenv("QUARANTINE_CONTAINER", "quarantine-test"),
        worker_version=os.getenv("WORKER_VERSION", "pilot-v0.1"),
        default_max_files=int(os.getenv("DEFAULT_MAX_FILES", "50")),
        default_prefix=os.getenv("DEFAULT_PREFIX") or None,
        auth_mode=auth_mode,
        connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING") or None,
        upload_reports=_parse_bool(os.getenv("UPLOAD_REPORTS", "true")),
        dashboard_report_source=os.getenv("DASHBOARD_REPORT_SOURCE", "azure"),
        enable_ai=_parse_bool(os.getenv("ENABLE_AI", "false"), default=False),
        ai_provider=os.getenv("AI_PROVIDER", "none").lower(),
        ai_policy_mode=os.getenv("AI_POLICY_MODE", "conservative").lower(),
        ai_max_calls_per_run=int(os.getenv("AI_MAX_CALLS_PER_RUN", "20")),
        ai_max_chars_per_file=int(os.getenv("AI_MAX_CHARS_PER_FILE", "4000")),
        ai_min_confidence_threshold=int(os.getenv("AI_MIN_CONFIDENCE_THRESHOLD", "60")),
        ai_foundry_endpoint=os.getenv("AI_FOUNDRY_ENDPOINT") or None,
        ai_foundry_model_deployment=os.getenv("AI_FOUNDRY_MODEL_DEPLOYMENT") or None,
        ai_foundry_api_version=os.getenv("AI_FOUNDRY_API_VERSION") or None,
        ai_foundry_api_key=os.getenv("AI_FOUNDRY_API_KEY") or None,
    )



