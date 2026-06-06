"""Unified Azure Blob Storage repository for the GEMA Classification Worker.

Handles all Azure SDK interactions:
  - source blob listing (with tags)
  - writing blob index tags
  - writing blob metadata
  - uploading report files to the reports container

Auth modes:
  device_code      – DeviceCodeCredential  (local Docker, no Azure CLI in container)
  default          – DefaultAzureCredential (az login locally / Managed Identity in Azure)
  connection_string – direct connection string (local emergency only)
"""

from __future__ import annotations

import io
from typing import Iterator, Optional

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from app.classifier_rules import _get_extension
from app.config import Config
from app.models import BlobRecord


class AzureBlobRepository:
    """Primary Azure Blob Storage access layer for the worker."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client: BlobServiceClient = self._build_client()

    # ------------------------------------------------------------------
    # Client initialisation
    # ------------------------------------------------------------------

    def _build_client(self) -> BlobServiceClient:
        mode = self.config.auth_mode

        if mode == "connection_string" or self.config.connection_string:
            cs = self.config.connection_string
            if not cs:
                raise ValueError(
                    "AUTH_MODE=connection_string requires AZURE_STORAGE_CONNECTION_STRING to be set"
                )
            return BlobServiceClient.from_connection_string(cs)

        if mode == "device_code":
            from azure.identity import DeviceCodeCredential, TokenCachePersistenceOptions  # noqa: PLC0415
            credential = DeviceCodeCredential(
                cache_persistence_options=TokenCachePersistenceOptions(
                    name="andre3000",
                    allow_unencrypted_storage=True,  # required on Linux (Docker)
                )
            )
        else:
            credential = DefaultAzureCredential()

        return BlobServiceClient(
            account_url=self.config.account_url,
            credential=credential,
        )

    # ------------------------------------------------------------------
    # Connectivity check
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if the source container is reachable."""
        try:
            cc = self._client.get_container_client(self.config.source_container)
            cc.get_container_properties()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Blob listing (worker)
    # ------------------------------------------------------------------

    def list_source_blobs(
        self,
        prefix: Optional[str] = None,
    ) -> Iterator[BlobRecord]:
        """Yield BlobRecord for every blob in the source container.

        Tags are fetched inline via ``include=['tags']`` to avoid extra API calls.
        """
        cc = self._client.get_container_client(self.config.source_container)
        kwargs: dict = {}
        if prefix:
            kwargs["name_starts_with"] = prefix
        for blob in cc.list_blobs(include=["tags"], **kwargs):
            tags: dict[str, str] = dict(blob.tags) if blob.tags else {}
            yield BlobRecord(
                blob_name=blob.name,
                container=self.config.source_container,
                size_bytes=blob.size or 0,
                extension=_get_extension(blob.name),
                last_modified=blob.last_modified,
                etag=blob.etag or "",
                existing_tags=tags,
                existing_status_before=tags.get("status", ""),
            )

    # ------------------------------------------------------------------
    # Blob content download (worker – extract mode)
    # ------------------------------------------------------------------

    def download_blob_content(
        self,
        blob_name: str,
        max_bytes: int = 262144,  # 256 KB default
    ) -> tuple[bytes, str]:
        """Download up to *max_bytes* from a source blob.

        Returns ``(content_bytes, error_message)``.
        On error, content_bytes is empty and error_message is non-empty.

        Security: content bytes MUST NOT be persisted by callers.
        They are passed to extractors for in-memory analysis only.
        """
        try:
            bc = self._client.get_blob_client(
                container=self.config.source_container, blob=blob_name
            )
            stream = bc.download_blob(offset=0, length=max_bytes)
            data: bytes = stream.readall()
            return data, ""
        except AzureError as exc:
            return b"", str(exc)[:500]
        except Exception as exc:  # noqa: BLE001
            return b"", str(exc)[:500]

    # ------------------------------------------------------------------
    # Tag operations (worker)
    # ------------------------------------------------------------------

    def set_blob_tags(
        self,
        blob_name: str,
        tags: dict[str, str],
    ) -> tuple[bool, str]:
        """Write blob index tags. Returns (success, error_message)."""
        try:
            bc = self._client.get_blob_client(
                container=self.config.source_container, blob=blob_name
            )
            bc.set_blob_tags(tags)
            return True, ""
        except AzureError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Metadata operations (worker)
    # ------------------------------------------------------------------

    def set_blob_metadata(
        self,
        blob_name: str,
        metadata: dict[str, str],
    ) -> tuple[bool, str]:
        """Write blob metadata. Returns (success, error_message)."""
        try:
            bc = self._client.get_blob_client(
                container=self.config.source_container, blob=blob_name
            )
            bc.set_blob_metadata(metadata)
            return True, ""
        except AzureError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Report upload (worker)
    # ------------------------------------------------------------------

    def upload_bytes(
        self,
        container: str,
        blob_name: str,
        data: bytes,
        content_type: str = "text/plain",
    ) -> tuple[bool, str]:
        """Upload *data* as a blob. Overwrites if exists. Returns (success, error_message)."""
        try:
            bc = self._client.get_blob_client(container=container, blob=blob_name)
            bc.upload_blob(
                io.BytesIO(data),
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            return True, ""
        except AzureError as exc:
            return False, str(exc)

    def upload_run_reports(
        self,
        run_id: str,
        reports: dict[str, bytes],
    ) -> int:
        """Upload all *reports* to the reports container. Returns count of successful uploads."""
        prefix = f"{self.config.worker_version}/{run_id}"
        count = 0
        for filename, data in reports.items():
            if filename.endswith(".json"):
                ct = "application/json"
            elif filename.endswith(".jsonl"):
                ct = "application/x-ndjson"
            else:
                ct = "text/csv"
            blob_path = f"{prefix}/{filename}"
            ok, _ = self.upload_bytes(self.config.report_container, blob_path, data, ct)
            if ok:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Report listing + download (dashboard / report mode)
    # ------------------------------------------------------------------

    def list_run_ids(self) -> list[str]:
        """List run IDs from the reports container, newest first.

        Blob paths follow: ``{worker_version}/{run_id}/{filename}``
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

    def download_report_bytes(
        self,
        run_id: str,
        filename: str,
    ) -> Optional[bytes]:
        """Download a single report file. Returns None on error."""
        blob_path = f"{self.config.worker_version}/{run_id}/{filename}"
        try:
            bc = self._client.get_blob_client(
                container=self.config.report_container, blob=blob_path
            )
            stream = bc.download_blob()
            return stream.readall()
        except Exception:  # noqa: BLE001
            return None
