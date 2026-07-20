"""Data job handle and polling helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from openbot_sdk._errors import DataJobError

if TYPE_CHECKING:
    from openbot_sdk._client import Client


class DataJob:
    """Handle for an asynchronous OpenBot Data job."""

    def __init__(
        self,
        client: Client,
        job_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self.job_id = job_id
        self._data = data or {}

    @property
    def id(self) -> str:
        return self.job_id

    @property
    def status(self) -> str:
        return str(self._data.get("status", "unknown"))

    @property
    def result_url(self) -> str | None:
        value = self._data.get("result_url")
        return str(value) if value is not None else None

    def refresh(self) -> DataJob:
        self._data = self._client._request("GET", f"/data/jobs/{self.job_id}")
        return self

    def wait(self, *, poll_interval: float = 5.0, timeout: float = 3600.0) -> "DataJobResult":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.refresh()
            status = self.status.lower()
            if status in {"done", "success", "completed"}:
                return DataJobResult(self._data)
            if status in {"failed", "error", "cancelled", "canceled"}:
                message = self._data.get("error_message")
                suffix = f": {message}" if message else ""
                raise DataJobError(f"Data job {self.job_id} ended with status '{status}'{suffix}")
            time.sleep(poll_interval)
        raise TimeoutError(f"Data job {self.job_id} did not complete within {timeout} seconds")


class DataJobResult:
    """Convenience wrapper for a completed Data job and its review output."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def review_output(self) -> dict[str, Any] | None:
        value = self._data.get("review_output")
        return cast(dict[str, Any], value) if isinstance(value, dict) else None

    @property
    def review_output_id(self) -> str | None:
        review = self.review_output
        return str(review["id"]) if review and review.get("id") is not None else None

    @property
    def annotations(self) -> dict[str, Any]:
        review = self.review_output or {}
        value = review.get("annotations")
        return cast(dict[str, Any], value) if isinstance(value, dict) else {}

    @property
    def timeline(self) -> dict[str, Any]:
        value = self.annotations.get("timeline")
        return cast(dict[str, Any], value) if isinstance(value, dict) else {}

    @property
    def artifact_url(self) -> str | None:
        value = self._data.get("artifact_url")
        return str(value) if value is not None else None

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
