"""Data job handle and polling helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from openbot_sdk._errors import APIResponseError, DataJobError
from openbot_sdk._paths import api_path, resource_id

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
        self.job_id = resource_id(job_id, name="job id")
        self._data = data or {}

    @property
    def id(self) -> str:
        return self.job_id

    @property
    def status(self) -> str:
        return str(self._data.get("status", "unknown"))

    @property
    def stage(self) -> str | None:
        value = self._data.get("stage")
        return str(value) if value is not None else None

    @property
    def stage_updated_at(self) -> int | None:
        value = self._data.get("stage_updated_at")
        return int(value) if value is not None else None

    @property
    def attempt_count(self) -> int:
        return int(self._data.get("attempt_count", 0))

    @property
    def cancel_requested(self) -> bool:
        return bool(self._data.get("cancel_requested", False))

    @property
    def warnings(self) -> list[dict[str, Any]]:
        value = self._data.get("warnings")
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @property
    def error(self) -> dict[str, Any] | None:
        value = self._data.get("error")
        return dict(value) if isinstance(value, dict) else None

    @property
    def result_url(self) -> str | None:
        value = self._data.get("result_url")
        return str(value) if value is not None else None

    def refresh(self) -> DataJob:
        self._data = self._client._request(
            "GET", api_path("data", "jobs", self.job_id)
        )
        return self

    def cancel(self) -> DataJob:
        self._data = self._client._request(
            "POST",
            api_path("data", "jobs", self.job_id, "cancel"),
            headers={"Idempotency-Key": f"cancel-{self.job_id}"},
        )
        return self

    def wait(self, *, poll_interval: float = 5.0, timeout: float = 3600.0) -> "DataJobResult":
        deadline = self._client._clock() + timeout
        while self._client._clock() < deadline:
            self.refresh()
            status = self.status.lower()
            if status == "done":
                return DataJobResult(self._data)
            if status in {"failed", "cancelled"}:
                error = self.error
                message = error.get("message") if error else self._data.get("error_message")
                suffix = f": {message}" if message else ""
                raise DataJobError(f"Data job {self.job_id} ended with status '{status}'{suffix}")
            if status not in {"queued", "running", "finalizing"}:
                raise APIResponseError(f"Data job returned unknown status {status!r}")
            self._client._sleep(poll_interval)
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
