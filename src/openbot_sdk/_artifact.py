"""Authenticated Data artifact resource."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

if TYPE_CHECKING:
    from openbot_sdk._client import Client
from openbot_sdk._paths import api_path, resource_id


class DataArtifact:
    """Metadata and authenticated content operations for a Data artifact."""

    def __init__(self, client: Client, data: dict[str, Any]) -> None:
        self._client = client
        self._data = data
        resource_id(self.id, name="artifact id")

    @property
    def id(self) -> str:
        return str(self._data["id"])

    @property
    def kind(self) -> str:
        return str(self._data.get("kind", "unknown"))

    @property
    def content_type(self) -> str | None:
        value = self._data.get("content_type")
        return str(value) if value is not None else None

    @property
    def size_bytes(self) -> int | None:
        value = self._data.get("size_bytes")
        return int(value) if value is not None else None

    @property
    def retention_until(self) -> int | None:
        value = self._data.get("retention_until")
        return int(value) if value is not None else None

    def head(self) -> dict[str, str]:
        return self._client._request_headers(
            "HEAD", api_path("data", "artifacts", self.id, "content")
        )

    def download_to(
        self,
        destination: str | Path | BinaryIO,
        *,
        byte_range: str | None = None,
        timeout: float | None = None,
    ) -> Path | None:
        return self._client._stream_to(
            api_path("data", "artifacts", self.id, "content"),
            destination,
            byte_range=byte_range,
            timeout=timeout,
        )

    def __getitem__(self, key: str) -> Any:
        """Return a raw response field for forward-compatible server additions."""
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Return a raw response field for forward-compatible server additions."""
        return self._data.get(key, default)
