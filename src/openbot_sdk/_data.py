"""OpenBot Data API resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from openbot_sdk._data_job import DataJob

if TYPE_CHECKING:
    from openbot_sdk._client import Client


ReviewStatus = Literal["needs_review", "approved", "changes_requested", "rejected"]
ExportFormat = Literal["jsonl", "lerobot_sidecar", "rlds_metadata"]


class DataResource:
    """Register robot datasets and create evidence-backed annotation jobs."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def register_dataset(
        self,
        *,
        name: str,
        source: str,
        format: str,
        embodiment: str | None = None,
        description: str | None = None,
        size_bytes: int | None = None,
        episode_count: int | None = None,
        version_tag: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "source": source, "format": format}
        optional = {
            "embodiment": embodiment,
            "description": description,
            "size_bytes": size_bytes,
            "episode_count": episode_count,
            "version_tag": version_tag,
            "metadata": metadata,
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._client._request("POST", "/data/datasets", json=body, headers=headers)

    def subtask_job(
        self,
        *,
        dataset_id: str,
        video_key: str,
        taxonomy: list[str],
        video_url: str | None = None,
        task_hint: str | None = None,
        sample_fps: float = 1.0,
        max_frames: int = 32,
        contact_sheet_columns: int = 5,
        prompt_version: str = "subtask-timeline-v1",
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DataJob:
        body: dict[str, Any] = {
            "dataset_id": dataset_id,
            "video_key": video_key,
            "segmentation": {
                "strategy": "contact_sheet_vlm",
                "sample_fps": sample_fps,
                "max_frames": max_frames,
                "contact_sheet": {
                    "columns": contact_sheet_columns,
                    "timestamp_overlay": True,
                },
            },
            "labeling": {
                "strategy": "vlm_with_before_after_context",
                "taxonomy": taxonomy,
            },
            "review": {"required": True},
            "prompt_version": prompt_version,
        }
        if video_url is not None:
            body["video_url"] = video_url
        if task_hint is not None:
            body["task_hint"] = task_hint
        if metadata is not None:
            body["metadata"] = metadata
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = self._client._request(
            "POST",
            "/data/subtask-jobs",
            json=body,
            headers=headers,
        )
        return DataJob(self._client, str(response["id"]), data=response)

    def get_job(self, job_id: str) -> DataJob:
        return DataJob(self._client, job_id).refresh()

    def review(
        self,
        review_output_id: str,
        *,
        status: ReviewStatus,
        notes: str | None = None,
        annotations: dict[str, Any] | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"status": status, "decisions": decisions or []}
        if notes is not None:
            body["notes"] = notes
        if annotations is not None:
            body["annotations"] = annotations
        return self._client._request(
            "PATCH",
            f"/data/review-outputs/{review_output_id}",
            json=body,
        )

    def export(self, review_output_id: str, *, format: ExportFormat) -> dict[str, Any]:
        return self._client._request(
            "POST",
            f"/data/review-outputs/{review_output_id}/exports",
            json={"format": format},
        )

    def download_export(self, export_id: str) -> bytes:
        """Download an approved export through the org-scoped Data API."""
        return self._client._request_bytes("GET", f"/data/exports/{export_id}/content")
