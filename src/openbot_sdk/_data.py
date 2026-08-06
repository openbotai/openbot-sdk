"""OpenBot Data API resource."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Iterator, Literal

from openbot_sdk._artifact import DataArtifact
from openbot_sdk._data_job import DataJob
from openbot_sdk._errors import APIResponseError
from openbot_sdk._models import DataExport, Dataset, ReviewOutput
from openbot_sdk._paths import api_path, resource_id
from openbot_sdk._upload import DataUpload
from openbot_sdk._upload_source import UploadSource

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
        format: str,
        source: str | None = None,
        upload_id: str | None = None,
        embodiment: str | None = None,
        description: str | None = None,
        size_bytes: int | None = None,
        episode_count: int | None = None,
        version_tag: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Dataset:
        if source is None and upload_id is None:
            raise ValueError("source or upload_id is required")
        body: dict[str, Any] = {"name": name, "format": format}
        optional = {
            "source": source,
            "upload_id": upload_id,
            "embodiment": embodiment,
            "description": description,
            "size_bytes": size_bytes,
            "episode_count": episode_count,
            "version_tag": version_tag,
            "metadata": metadata,
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return Dataset(
            self._client._request("POST", "/data/datasets", json=body, headers=headers)
        )

    def subtask_job(
        self,
        *,
        dataset_id: str,
        video_key: str,
        taxonomy: list[str],
        video_url: str | None = None,
        upload_id: str | None = None,
        task_hint: str | None = None,
        sample_fps: float = 1.0,
        max_frames: int = 32,
        contact_sheet_columns: int = 5,
        prompt_version: str = "subtask-timeline-v1",
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DataJob:
        if (video_url is None) == (upload_id is None):
            raise ValueError("Exactly one of video_url or upload_id is required")
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
        if upload_id is not None:
            body["upload_id"] = upload_id
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
        job_id = response.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise APIResponseError("Subtask job response has no valid id")
        return DataJob(self._client, job_id, data=response)

    def get_job(self, job_id: str) -> DataJob:
        return DataJob(self._client, job_id).refresh()

    def create_upload(
        self,
        *,
        path: str | Path,
        dataset_id: str | None = None,
        content_type: str | None = None,
        idempotency_key: str | None = None,
    ) -> DataUpload:
        source = UploadSource.from_path(path)
        resolved_content_type = content_type or mimetypes.guess_type(source.path.name)[0]
        resolved_content_type = resolved_content_type or "application/octet-stream"
        key = idempotency_key or f"upload-{uuid.uuid4().hex}"
        body: dict[str, Any] = {
            "filename": source.path.name,
            "content_type": resolved_content_type,
            "size_bytes": source.size_bytes,
            "checksum_sha256": source.checksum_sha256,
        }
        if dataset_id is not None:
            body["dataset_id"] = dataset_id
        response = self._client._request(
            "POST",
            "/data/uploads",
            json=body,
            headers={"Idempotency-Key": key},
        )
        upload_id = response.get("id")
        if upload_id is None:
            raise APIResponseError("Upload response has no id")
        return DataUpload(
            self._client,
            str(upload_id),
            path=source.path,
            source=source,
            data=response,
            idempotency_key=key,
        )

    def get_upload(self, upload_id: str) -> DataUpload:
        validated = resource_id(upload_id, name="upload id")
        response = self._client._request(
            "GET", api_path("data", "uploads", validated)
        )
        return DataUpload(self._client, validated, data=response)

    def resume_upload(self, upload_id: str, *, path: str | Path) -> DataUpload:
        validated = resource_id(upload_id, name="upload id")
        source = UploadSource.from_path(path)
        response = self._client._request(
            "GET", api_path("data", "uploads", validated)
        )
        return DataUpload(
            self._client,
            validated,
            path=source.path,
            source=source,
            data=response,
            require_server_identity=True,
        )

    def delete_upload(self, upload_id: str) -> None:
        self._client._request_empty(
            "DELETE",
            api_path("data", "uploads", resource_id(upload_id, name="upload id")),
        )

    def list_uploads(
        self,
        *,
        status: str | None = None,
        page_size: int = 20,
    ) -> Iterator[DataUpload]:
        for item in self._paginate(
            "/data/uploads",
            {"status": status, "page_size": page_size},
        ):
            yield DataUpload(self._client, str(item["id"]), data=item)

    def list_datasets(
        self,
        *,
        format: str | None = None,
        embodiment: str | None = None,
        page_size: int = 20,
    ) -> Iterator[Dataset]:
        for item in self._paginate(
            "/data/datasets",
            {"format": format, "embodiment": embodiment, "page_size": page_size},
        ):
            yield Dataset(item)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        dataset_id: str | None = None,
        job_type: str | None = None,
        page_size: int = 20,
    ) -> Iterator[DataJob]:
        for item in self._paginate(
            "/data/jobs",
            {
                "status": status,
                "dataset_id": dataset_id,
                "job_type": job_type,
                "page_size": page_size,
            },
        ):
            yield DataJob(self._client, str(item["id"]), data=item)

    def review(
        self,
        review_output_id: str,
        *,
        status: ReviewStatus,
        notes: str | None = None,
        annotations: dict[str, Any] | None = None,
        decisions: list[dict[str, Any]] | None = None,
        expected_revision: str | None = None,
    ) -> ReviewOutput:
        body: dict[str, Any] = {"status": status, "decisions": decisions or []}
        if notes is not None:
            body["notes"] = notes
        if annotations is not None:
            body["annotations"] = annotations
        headers = (
            {"If-Match": resource_id(expected_revision, name="review revision id")}
            if expected_revision is not None
            else None
        )
        return ReviewOutput(
            self._client._request(
                "PATCH",
                api_path(
                    "data",
                    "review-outputs",
                    resource_id(review_output_id, name="review output id"),
                ),
                json=body,
                headers=headers,
            )
        )

    def export(self, review_output_id: str, *, format: ExportFormat) -> DataExport:
        return DataExport(
            self._client._request(
                "POST",
                api_path(
                    "data",
                    "review-outputs",
                    resource_id(review_output_id, name="review output id"),
                    "exports",
                ),
                json={"format": format},
            )
        )

    def download_export(self, export_id: str, *, timeout: float | None = None) -> bytes:
        """Download an approved export through the org-scoped Data API."""
        return self._client._request_bytes(
            "GET",
            api_path("data", "exports", resource_id(export_id, name="export id"), "content"),
            timeout=timeout,
        )

    def download_export_to(
        self,
        export_id: str,
        destination: str | Path | BinaryIO,
        *,
        timeout: float | None = None,
    ) -> Path | None:
        return self._client._stream_to(
            api_path("data", "exports", resource_id(export_id, name="export id"), "content"),
            destination,
            timeout=timeout,
        )

    def delete_export(self, export_id: str) -> None:
        self._client._request_empty(
            "DELETE",
            api_path("data", "exports", resource_id(export_id, name="export id")),
        )

    def list_artifacts(
        self,
        job_id: str,
        *,
        page_size: int = 20,
    ) -> Iterator[DataArtifact]:
        for item in self._paginate(
            api_path("data", "jobs", resource_id(job_id, name="job id"), "artifacts"),
            {"page_size": page_size},
        ):
            yield DataArtifact(self._client, item)

    def artifact(self, artifact_id: str, **metadata: Any) -> DataArtifact:
        return DataArtifact(self._client, {"id": artifact_id, **metadata})

    def download_artifact(
        self,
        artifact_id: str,
        destination: str | Path | BinaryIO,
        *,
        byte_range: str | None = None,
        timeout: float | None = None,
    ) -> Path | None:
        return self.artifact(artifact_id).download_to(
            destination,
            byte_range=byte_range,
            timeout=timeout,
        )

    def head_artifact(self, artifact_id: str) -> dict[str, str]:
        return self.artifact(artifact_id).head()

    def delete_job_artifacts(self, job_id: str) -> None:
        self._client._request_empty(
            "DELETE",
            api_path("data", "jobs", resource_id(job_id, name="job id"), "artifacts"),
        )

    def _paginate(
        self,
        path: str,
        params: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        page_size = params.get("page_size", 20)
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        request_params = {key: value for key, value in params.items() if value is not None}
        seen: set[str] = set()
        seen_tokens: set[str] = set()
        while True:
            response = self._client._request("GET", path, params=request_params)
            data = response.get("data")
            if not isinstance(data, list):
                raise APIResponseError("Paginated response has no data list")
            for item in data:
                if not isinstance(item, dict):
                    raise APIResponseError("Paginated response contains a non-object item")
                raw_id = item.get("id")
                if not isinstance(raw_id, str) or not raw_id:
                    raise APIResponseError("Paginated resource has no valid id")
                item_id = resource_id(raw_id)
                if item_id in seen:
                    continue
                seen.add(item_id)
                yield item
            token = response.get("next_page_token")
            if token is None or token == "":
                return
            if not isinstance(token, str):
                raise APIResponseError(
                    "Paginated response has a non-string next_page_token"
                )
            if token in seen_tokens:
                raise APIResponseError("Paginated response repeated next_page_token")
            seen_tokens.add(token)
            request_params["page_token"] = token
