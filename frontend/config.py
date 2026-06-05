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
    report_container: str
    worker_version: str
    connection_string: str   # optional – emergency access

    @property
    def account_url(self) -> str:
        return f"https://{self.storage_account}.blob.core.windows.net"


def load_frontend_config() -> FrontendConfig:
    return FrontendConfig(
        auth_mode=os.environ.get("AUTH_MODE", "default"),
        storage_account=os.environ.get("AZURE_STORAGE_ACCOUNT", "stgemaclasspilot001"),
        report_container=os.environ.get("REPORT_CONTAINER", "reports"),
        worker_version=os.environ.get("WORKER_VERSION", "pilot-v0.1"),
        connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING", ""),
    )
