"""Self-service private Data upload resource."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

import httpx

from openbot_sdk._errors import APIResponseError, DataUploadError, NetworkError
from openbot_sdk._paths import api_path, resource_id
from openbot_sdk._upload_source import UploadSource

if TYPE_CHECKING:
    from openbot_sdk._client import Client


class DataUpload:
    """Handle for a direct single or multipart Data upload."""

    def __init__(
        self,
        client: Client,
        upload_id: str,
        *,
        path: str | Path | None = None,
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        source: UploadSource | None = None,
        require_server_identity: bool = False,
    ) -> None:
        self._client = client
        self.upload_id = resource_id(upload_id, name="upload id")
        self.path = Path(path) if path is not None else None
        self._source = source
        self._require_server_identity = require_server_identity
        self._data = data or {}
        self._idempotency_key = idempotency_key or f"upload-{upload_id}"
        self._completed_parts: dict[int, str] = {}
        completed = self._data.get("completed_parts", [])
        if isinstance(completed, list):
            for item in completed:
                if isinstance(item, dict) and item.get("part_number") is not None:
                    etag = item.get("etag")
                    if etag is not None:
                        self._completed_parts[int(item["part_number"])] = str(etag)

    @property
    def id(self) -> str:
        return self.upload_id

    @property
    def status(self) -> str:
        return str(self._data.get("status", "unknown"))

    @property
    def mode(self) -> str:
        return str(self._data.get("mode", "unknown"))

    @property
    def retention_until(self) -> int | None:
        value = self._data.get("retention_until")
        return int(value) if value is not None else None

    @property
    def media(self) -> dict[str, Any]:
        value = self._data.get("media")
        return dict(value) if isinstance(value, dict) else {}

    def refresh(self) -> DataUpload:
        self._data = self._client._request(
            "GET", api_path("data", "uploads", self.upload_id)
        )
        return self

    def upload(self, *, part_concurrency: int = 4) -> DataUpload:
        """Transfer the local file, complete it, and return the updated resource."""
        if self.path is None:
            raise DataUploadError("A local path is required to transfer an upload")
        if not self.path.is_file():
            raise DataUploadError(f"Upload file was not found: {self.path}")
        if part_concurrency < 1:
            raise ValueError("part_concurrency must be at least 1")
        self._verify_local_identity()

        if self.mode == "single":
            self._upload_single()
            parts: list[dict[str, Any]] = []
        elif self.mode == "multipart":
            parts = self._upload_multipart(part_concurrency)
        else:
            raise APIResponseError(f"Unsupported upload mode: {self.mode}")

        self._data = self._client._request(
            "POST",
            api_path("data", "uploads", self.upload_id, "complete"),
            json={"parts": parts},
            headers={"Idempotency-Key": f"{self._idempotency_key}:complete"},
        )
        return self

    def wait_until_ready(
        self,
        *,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
    ) -> DataUpload:
        deadline = self._client._clock() + timeout
        while self._client._clock() < deadline:
            self.refresh()
            status = self.status.lower()
            if status == "ready":
                return self
            if status in {"rejected", "expired", "aborted", "deleted"}:
                error = self._data.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                suffix = f": {message}" if message else ""
                raise DataUploadError(
                    f"Data upload {self.upload_id} ended with status '{status}'{suffix}"
                )
            if status not in {"pending_upload", "uploading", "verifying"}:
                raise APIResponseError(
                    f"Data upload returned unknown status {status!r}"
                )
            self._client._sleep(poll_interval)
        raise TimeoutError(
            f"Data upload {self.upload_id} did not become ready within {timeout} seconds"
        )

    def delete(self) -> None:
        self._client._request_empty(
            "DELETE", api_path("data", "uploads", self.upload_id)
        )
        self._data["status"] = "deleted"

    def __getitem__(self, key: str) -> Any:
        """Return a raw response field for forward-compatible server additions."""
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Return a raw response field for forward-compatible server additions."""
        return self._data.get(key, default)

    def _upload_single(self) -> None:
        source = self._require_source()
        upload = self._data.get("upload")
        if not isinstance(upload, dict):
            raise APIResponseError("Single upload response has no upload instructions")
        url = upload.get("url")
        if not isinstance(url, str):
            raise APIResponseError("Single upload response has no presigned URL")
        method = upload.get("method", "PUT")
        if not isinstance(method, str) or method.upper() != "PUT":
            raise APIResponseError("Single upload response must use PUT")
        headers = upload.get("headers")
        normalized_headers = (
            {str(key): str(value) for key, value in headers.items()}
            if isinstance(headers, dict)
            else {}
        )
        self._send_file("PUT", url, normalized_headers, 0, source.size_bytes)

    def _upload_multipart(self, part_concurrency: int) -> list[dict[str, Any]]:
        part_size = int(self._data.get("part_size_bytes", 0))
        part_count = int(self._data.get("part_count", 0))
        if part_size <= 0 or part_count <= 0:
            raise APIResponseError("Multipart upload response has invalid part metadata")
        source = self._require_source()
        expected_count = max(1, (source.size_bytes + part_size - 1) // part_size)
        if expected_count != part_count:
            raise APIResponseError("Multipart part count does not match the local file size")
        missing = [
            part_number
            for part_number in range(1, part_count + 1)
            if part_number not in self._completed_parts
        ]
        for offset in range(0, len(missing), 20):
            batch = missing[offset : offset + 20]
            instructions = self._sign_parts(batch)
            with ThreadPoolExecutor(max_workers=min(part_concurrency, len(batch))) as executor:
                futures = {
                    executor.submit(
                        self._upload_part,
                        instruction,
                        part_size,
                    ): int(instruction["part_number"])
                    for instruction in instructions
                }
                first_error: Exception | None = None
                for future in as_completed(futures):
                    part_number = futures[future]
                    try:
                        self._completed_parts[part_number] = future.result()
                    except Exception as exc:
                        if first_error is None:
                            first_error = exc
                if first_error is not None:
                    raise first_error
        return [
            {"part_number": number, "etag": self._completed_parts[number]}
            for number in sorted(self._completed_parts)
        ]

    def _sign_parts(self, part_numbers: list[int]) -> list[dict[str, Any]]:
        response = self._client._request(
            "POST",
            api_path("data", "uploads", self.upload_id, "parts"),
            json={"part_numbers": part_numbers},
            headers={
                "Idempotency-Key": (
                    f"{self._idempotency_key}:parts:{part_numbers[0]}-{part_numbers[-1]}"
                )
            },
        )
        value = response.get("parts", response.get("data"))
        if not isinstance(value, list):
            raise APIResponseError("Multipart signer response has no parts list")
        instructions = [item for item in value if isinstance(item, dict)]
        returned = {int(item.get("part_number", 0)) for item in instructions}
        if returned != set(part_numbers) or len(instructions) != len(part_numbers):
            raise APIResponseError("Multipart signer returned unexpected part numbers")
        return instructions

    def _upload_part(self, instruction: dict[str, Any], part_size: int) -> str:
        part_number = int(instruction["part_number"])
        url = instruction.get("url")
        if not isinstance(url, str):
            raise APIResponseError(f"Part {part_number} has no presigned URL")
        headers = instruction.get("headers")
        normalized_headers = (
            {str(key): str(value) for key, value in headers.items()}
            if isinstance(headers, dict)
            else {}
        )
        offset = (part_number - 1) * part_size
        source = self._require_source()
        size = min(part_size, max(0, source.size_bytes - offset))
        response = self._send_file("PUT", url, normalized_headers, offset, size)
        etag = response.headers.get("ETag")
        if not etag:
            raise APIResponseError(f"Part {part_number} response has no ETag")
        return str(etag)

    def _send_file(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        offset: int,
        size: int,
    ) -> httpx.Response:
        source = self._require_source()
        last_error: Exception | None = None
        request_headers = {str(key): str(value) for key, value in headers.items()}
        request_headers.setdefault("Content-Length", str(size))
        for attempt in range(self._client.max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = self._client._external_request(
                    method,
                    url,
                    headers=request_headers,
                    content=source.stream(offset, size),
                )
                if 200 <= response.status_code < 300:
                    return response
                if response.status_code not in {429, 502, 503, 504}:
                    raise DataUploadError(
                        f"Presigned upload failed with status {response.status_code}"
                    )
                last_error = DataUploadError(
                    f"Presigned upload failed with status {response.status_code}"
                )
            except NetworkError as exc:
                last_error = exc
            if attempt < self._client.max_retries:
                retry_after = (
                    response.headers.get("Retry-After") if response is not None else None
                )
                self._client._sleep_before_retry(attempt, retry_after)
        raise DataUploadError(f"Presigned upload failed after retries: {last_error}")

    def _require_path(self) -> Path:
        if self.path is None:
            raise DataUploadError("A local path is required to transfer an upload")
        return self.path

    def _require_source(self) -> UploadSource:
        path = self._require_path()
        if self._source is None:
            self._source = UploadSource.from_path(path)
        return self._source

    def _verify_local_identity(self) -> None:
        source = self._require_source()
        source.assert_unchanged()
        declared_size = self._data.get("size_bytes")
        declared_checksum = self._data.get("checksum_sha256")
        if self._require_server_identity and (
            declared_size is None or declared_checksum is None
        ):
            raise APIResponseError(
                "Resumable upload response must include size_bytes and checksum_sha256"
            )
        if declared_size is not None and int(declared_size) != source.size_bytes:
            raise DataUploadError("Local file size does not match the upload resource")
        if (
            declared_checksum is not None
            and str(declared_checksum).lower() != source.checksum_sha256
        ):
            raise DataUploadError("Local file checksum does not match the upload resource")
