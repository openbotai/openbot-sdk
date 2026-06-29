"""Rollout run handle and polling."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from openbotai._errors import RunError

if TYPE_CHECKING:
    from openbotai._client import Client


class Run:
    """
    Handle for an asynchronous Bench rollout.

    Provides access to run metadata and a blocking ``wait()`` helper that
    polls until the run reaches a terminal state.
    """

    def __init__(self, client: Client, run_id: str, data: dict[str, Any] | None = None) -> None:
        self._client = client
        self.run_id = run_id
        self._data = data or {}

    @property
    def id(self) -> str:
        return self.run_id

    @property
    def status(self) -> str:
        """Current run status (e.g. queued, running, success, failed)."""
        return str(self._data.get("status", "unknown"))

    @property
    def result_url(self) -> str | None:
        """URL to fetch the full result."""
        return self._data.get("result_url")

    def refresh(self) -> Run:
        """Fetch the latest run state from the API."""
        data = self._client._request("GET", f"/bench/runs/{self.run_id}")
        self._data = data
        return self

    def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
    ) -> "RunResult":
        """
        Poll until the run completes or fails.

        Args:
            poll_interval: Seconds between polls.
            timeout: Maximum seconds to wait.

        Returns:
            RunResult with task success, subtask breakdown, and other metrics.

        Raises:
            RunError: if the run fails or is cancelled.
            APIError: if polling returns an API error.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.refresh()
            status = self.status.lower()
            if status in {"success", "completed"}:
                return RunResult(self._data.get("result", {}))
            if status in {"failed", "error", "cancelled"}:
                raise RunError(f"Run {self.run_id} ended with status '{status}'")
            time.sleep(poll_interval)

        raise TimeoutError(f"Run {self.run_id} did not complete within {timeout} seconds")


class RunResult:
    """Convenience wrapper for a completed rollout result."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def task_success(self) -> float | None:
        """Overall task success rate."""
        value = self._data.get("task_success")
        return float(value) if value is not None else None

    @property
    def intervention_rate(self) -> float | None:
        """Rate of human intervention."""
        value = self._data.get("intervention_rate")
        return float(value) if value is not None else None

    @property
    def sim_to_real_gap(self) -> float | None:
        """Sim-to-real success rate gap."""
        value = self._data.get("sim_to_real_gap")
        return float(value) if value is not None else None

    @property
    def subtask(self) -> dict[str, Any]:
        """Per-subtask metrics."""
        return cast(dict[str, Any], self._data.get("subtask", {}))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
