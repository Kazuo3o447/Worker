"""Azure Blob Storage client with flexible auth and per-operation error handling.

Authentication modes (AUTH_MODE env var):
  connection_string – BlobServiceClient.from_connection_string()  (local tests only)
  default           – DefaultAzureCredential (Azure CLI / Managed Identity)
  device_code       – DeviceCodeCredential  (local Docker, no Azure CLI in container)
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


class AzureStorageClient:
    """Thin wrapper around Azure SDK with project-specific helpers."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client: BlobServiceClient = self._build_client()

    # ------------------------------------------------------------------
    # Initialisation
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
            # Prints a login URL + code to stdout on first auth – intended for local Docker use.
            from azure.identity import DeviceCodeCredential  # noqa: PLC0415
            credential = DeviceCodeCredential()
        else:
            # AUTH_MODE=default: works with `az login` locally and Managed Identity in Azure.
            credential = DefaultAzureCredential()

        return BlobServiceClient(
            account_url=self.config.account_url,
            credential=credential,
        )

    # ------------------------------------------------------------------
    # Connectivity check
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if the source container is reachable.

        Requires at minimum Storage Blob Data Reader on the container.
        """
        try:
            cc = self._client.get_container_client(self.config.source_container)
            cc.get_container_properties()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Blob listing – tags included to minimise API calls
    # ------------------------------------------------------------------

    def list_blobs(
        self,
        container: str,
        prefix: Optional[str] = None,
    ) -> Iterator[BlobRecord]:
        """Yield one BlobRecord per blob.  Tags are fetched inline via include=['tags']."""
        cc = self._client.get_container_client(container)
        kwargs: dict = {}
        if prefix:
            kwargs["name_starts_with"] = prefix
        for blob in cc.list_blobs(include=["tags"], **kwargs):
            tags: dict[str, str] = dict(blob.tags) if blob.tags else {}
            yield BlobRecord(
                blob_name=blob.name,
                container=container,
                size_bytes=blob.size or 0,
                extension=_get_extension(blob.name),
                last_modified=blob.last_modified,
                etag=blob.etag or "",
                existing_tags=tags,
                existing_status_before=tags.get("status", ""),
            )

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def get_blob_tags(self, container: str, blob_name: str) -> dict[str, str]:
        """Fetch current index tags; returns {} on error."""
        try:
            bc = self._client.get_blob_client(container=container, blob=blob_name)
            result = bc.get_blob_tags()
            return dict(result) if result else {}
        except AzureError:
            return {}

    def set_blob_tags(
        self,
        container: str,
        blob_name: str,
        tags: dict[str, str],
    ) -> tuple[bool, str]:
        """Write index tags.  Returns (success, error_message)."""
        try:
            bc = self._client.get_blob_client(container=container, blob=blob_name)
            bc.set_blob_tags(tags)
            return True, ""
        except AzureError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Metadata operations
    # ------------------------------------------------------------------

    def set_blob_metadata(
        self,
        container: str,
        blob_name: str,
        metadata: dict[str, str],
    ) -> tuple[bool, str]:
        """Write blob metadata.  Returns (success, error_message)."""
        try:
            bc = self._client.get_blob_client(container=container, blob=blob_name)
            bc.set_blob_metadata(metadata)
            return True, ""
        except AzureError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Report upload
    # ------------------------------------------------------------------

    def upload_bytes(
        self,
        container: str,
        blob_name: str,
        data: bytes,
        content_type: str = "text/plain",
    ) -> tuple[bool, str]:
        """Upload *data* as a blob.  Overwrites if exists.  Returns (success, error_message)."""
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
