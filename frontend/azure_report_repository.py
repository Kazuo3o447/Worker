"""Read-only Azure Blob repository for the Streamlit dashboard.

Lists run IDs and downloads report files from the Azure reports container.
No writes – dashboard is strictly read-only.
"""

from __future__ import annotations

import io
import pathlib
import sys
import tempfile
from typing import Optional

import pandas as pd
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

# Temp file used to pass device-code URL into the Streamlit UI
_DEVICE_CODE_MSG_FILE = pathlib.Path(tempfile.gettempdir()) / "azure_device_code.txt"

# Persisted AuthenticationRecord so worker subprocesses can acquire tokens silently
# without a second device-code prompt.  Stored inside the token-cache volume.
_AUTH_RECORD_PATH = pathlib.Path.home() / ".IdentityService" / "auth_record.json"

try:
    from frontend.config import FrontendConfig
except ModuleNotFoundError:
    from config import FrontendConfig  # type: ignore[no-redef]


class AzureReportRepository:
    """Lists run IDs and fetches report files from Azure."""

    def __init__(self, config: FrontendConfig) -> None:
        self.config = config
        self._client: BlobServiceClient = self._build_client()

    def _build_client(self) -> BlobServiceClient:
        mode = self.config.auth_mode

        if mode == "connection_string" or self.config.connection_string:
            cs = self.config.connection_string
            if not cs:
                raise ValueError(
                    "AUTH_MODE=connection_string requires AZURE_STORAGE_CONNECTION_STRING"
                )
            return BlobServiceClient.from_connection_string(cs)

        if mode == "device_code":
            from azure.identity import (  # noqa: PLC0415
                AuthenticationRecord,
                DeviceCodeCredential,
                TokenCachePersistenceOptions,
            )

            def _device_code_cb(verification_uri: str, user_code: str, expires_on: object) -> None:  # noqa: ANN001
                msg = (
                    f"### Azure-Login erforderlich\n\n"
                    f"1. Öffne im Browser: {verification_uri}\n\n"
                    f"2. Code eingeben: **`{user_code}`**\n\n"
                    f"*(Seite aktualisiert sich automatisch nach dem Login.)*"
                )
                try:
                    _DEVICE_CODE_MSG_FILE.write_text(msg, encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass  # Non-critical – message also printed to stderr
                print(
                    f"\n[DEVICE CODE AUTH] Open {verification_uri} and enter code: {user_code}\n",
                    file=sys.__stderr__,
                    flush=True,
                )

            # Load persisted AuthenticationRecord so silent token refresh works
            # for both this process AND any worker subprocesses.
            auth_record: Optional[AuthenticationRecord] = None
            if _AUTH_RECORD_PATH.exists():
                try:
                    auth_record = AuthenticationRecord.deserialize(
                        _AUTH_RECORD_PATH.read_text(encoding="utf-8")
                    )
                except Exception:  # noqa: BLE001
                    auth_record = None

            cache_opts = TokenCachePersistenceOptions(
                name="andre3000",
                allow_unencrypted_storage=True,
            )
            credential = DeviceCodeCredential(
                prompt_callback=_device_code_cb,
                authentication_record=auth_record,
                cache_persistence_options=cache_opts,
            )
            # Store credential on the instance so is_available() can save the
            # AuthenticationRecord after the first successful token acquisition.
            self._credential = credential
            self._cache_opts = cache_opts
        else:
            credential = DefaultAzureCredential()

        return BlobServiceClient(
            account_url=self.config.account_url,
            credential=credential,
        )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def is_available(self) -> tuple[bool, str]:
        """Return (ok, error_message). ok=False means dashboard should show error.

        On first successful connection, persists the AuthenticationRecord so
        worker subprocesses can acquire tokens silently without a new device code.
        """
        try:
            cc = self._client.get_container_client(self.config.report_container)
            cc.get_container_properties()
            # Save AuthenticationRecord after first successful auth so subprocesses
            # (python -m app.main) can silently reuse the token.
            self._save_auth_record()
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _save_auth_record(self) -> None:
        """Persist AuthenticationRecord for subprocess reuse (idempotent)."""
        if _AUTH_RECORD_PATH.exists():
            return  # Already saved
        cred = getattr(self, "_credential", None)
        cache_opts = getattr(self, "_cache_opts", None)
        if cred is None or cache_opts is None:
            return
        try:
            from azure.identity import DeviceCodeCredential, AuthenticationRecord  # noqa: PLC0415
            record: AuthenticationRecord = cred.authenticate(
                scopes=["https://storage.azure.com/.default"]
            )
            _AUTH_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
            _AUTH_RECORD_PATH.write_text(record.serialize(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass  # Non-fatal – subprocess will prompt if needed

    # ------------------------------------------------------------------
    # Run discovery
    # ------------------------------------------------------------------

    def list_run_ids(self) -> list[str]:
        """Return run IDs from the reports container, sorted newest first.

        Blob layout: ``{worker_version}/{run_id}/{filename}``
        """
        cc = self._client.get_container_client(self.config.report_container)
        prefix = f"{self.config.worker_version}/"
        run_ids: set[str] = set()
        try:
            for blob in cc.list_blobs(name_starts_with=prefix):
                tail = blob.name[len(prefix):]
                parts = tail.split("/")
                if len(parts) >= 2 and parts[0]:
                    run_ids.add(parts[0])
        except Exception:  # noqa: BLE001
            pass
        return sorted(run_ids, reverse=True)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def _download(self, run_id: str, filename: str) -> Optional[bytes]:
        blob_path = f"{self.config.worker_version}/{run_id}/{filename}"
        try:
            bc = self._client.get_blob_client(
                container=self.config.report_container, blob=blob_path
            )
            return bc.download_blob().readall()
        except Exception:  # noqa: BLE001
            return None

    def get_run_summary(self, run_id: str) -> dict:
        import json
        data = self._download(run_id, "run-summary.json")
        if data is None:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def get_csv(self, run_id: str, filename: str) -> pd.DataFrame:
        data = self._download(run_id, filename)
        if data is None:
            return pd.DataFrame()
        try:
            return pd.read_csv(io.BytesIO(data))
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

    def get_events(self, run_id: str) -> pd.DataFrame:
        import json as _json
        data = self._download(run_id, "run-events.jsonl")
        if data is None:
            return pd.DataFrame()
        rows = []
        for line in data.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def get_report_bytes(self, run_id: str, filename: str) -> Optional[bytes]:
        """Generic download of any report file by run_id and filename."""
        return self._download(run_id, filename)

    # ------------------------------------------------------------------
    # Extended API
    # ------------------------------------------------------------------

    def list_runs(self) -> list[str]:
        """Alias for list_run_ids() – returns run IDs sorted newest first."""
        return self.list_run_ids()

    def get_report_json(self, run_id: str, filename: str) -> dict:
        """Download and parse a JSON report file. Returns {} on error."""
        import json
        data = self._download(run_id, filename)
        if data is None:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def get_report_csv(self, run_id: str, filename: str) -> pd.DataFrame:
        """Download and parse a CSV report file. Returns empty DataFrame on error."""
        return self.get_csv(run_id, filename)

    def report_exists(self, run_id: str, filename: str) -> bool:
        """Return True if the report file exists in Azure."""
        return self._download(run_id, filename) is not None

    def list_report_files(self, run_id: str) -> list[str]:
        """List all filenames in the given run's report folder."""
        cc = self._client.get_container_client(self.config.report_container)
        prefix = f"{self.config.worker_version}/{run_id}/"
        files: list[str] = []
        try:
            for blob in cc.list_blobs(name_starts_with=prefix):
                filename = blob.name[len(prefix):]
                if filename:
                    files.append(filename)
        except Exception:  # noqa: BLE001
            pass
        return sorted(files)
