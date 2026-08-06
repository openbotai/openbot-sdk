import hashlib
import importlib.util
import inspect
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

import openbot_sdk
from openbot_sdk._artifact import DataArtifact
from openbot_sdk._data import DataResource
from openbot_sdk._upload import DataUpload
from openbot_sdk._upload_source import UploadSource


def load_demo_module() -> Any:
    example_path = (
        Path(__file__).resolve().parents[1] / "examples" / "data_v002_workflow.py"
    )
    spec = importlib.util.spec_from_file_location("openbot_sdk_data_demo", example_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mock_api() -> respx.MockRouter:
    with respx.mock(base_url="https://api.openbot.ai/v1") as router:
        yield router


def test_resume_existing_multipart_upload_transfers_only_missing_parts(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"abcdefghij")
    mock_api.get("/data/uploads/upload_resume").respond(
        200,
        json={
            "id": "upload_resume",
            "status": "pending_upload",
            "mode": "multipart",
            "part_size_bytes": 4,
            "part_count": 3,
            "size_bytes": 10,
            "checksum_sha256": hashlib.sha256(b"abcdefghij").hexdigest(),
            "completed_parts": [{"part_number": 1, "etag": "etag-1"}],
        },
    )
    signer = mock_api.post("/data/uploads/upload_resume/parts").respond(
        200,
        json={
            "parts": [
                {"part_number": 2, "url": "https://r2.example.test/resume-2"},
                {"part_number": 3, "url": "https://r2.example.test/resume-3"},
            ]
        },
    )
    second = mock_api.put("https://r2.example.test/resume-2").respond(
        200, headers={"ETag": "etag-2"}
    )
    third = mock_api.put("https://r2.example.test/resume-3").respond(
        200, headers={"ETag": "etag-3"}
    )
    complete = mock_api.post("/data/uploads/upload_resume/complete").respond(
        202,
        json={"id": "upload_resume", "status": "verifying", "mode": "multipart"},
    )
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    upload = client.data.resume_upload("upload_resume", path=source).upload(part_concurrency=1)

    assert json.loads(signer.calls[0].request.read()) == {"part_numbers": [2, 3]}
    assert second.calls[0].request.read() == b"efgh"
    assert third.calls[0].request.read() == b"ij"
    assert "Authorization" not in second.calls[0].request.headers
    assert json.loads(complete.calls[0].request.read())["parts"] == [
        {"part_number": 1, "etag": "etag-1"},
        {"part_number": 2, "etag": "etag-2"},
        {"part_number": 3, "etag": "etag-3"},
    ]
    assert upload.status == "verifying"
    client.close()


def test_resume_rejects_different_local_file_identity(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"changed!")
    mock_api.get("/data/uploads/upload_resume").respond(
        200,
        json={
            "id": "upload_resume",
            "status": "pending_upload",
            "mode": "multipart",
            "part_size_bytes": 4,
            "part_count": 2,
            "size_bytes": len(b"original"),
            "checksum_sha256": hashlib.sha256(b"original").hexdigest(),
            "completed_parts": [],
        },
    )
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.DataUploadError, match="checksum"):
        client.data.resume_upload("upload_resume", path=source).upload()

    client.close()


def test_upload_source_streams_bounded_chunks_and_detects_mutation(tmp_path: Path) -> None:
    source_path = tmp_path / "large.mp4"
    source_path.write_bytes(b"x" * (2 * 1024 * 1024 + 17))
    source = UploadSource.from_path(source_path)

    chunks = list(source.stream(0, source.size_bytes))

    assert len(chunks) == 3
    assert max(map(len, chunks)) <= 1024 * 1024
    source_path.write_bytes(b"changed")
    with pytest.raises(openbot_sdk.DataUploadError, match="changed"):
        list(source.stream(0, source.size_bytes))


def test_upload_validates_local_and_server_transfer_contract(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"12345")
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.DataUploadError, match="local path"):
        DataUpload(client, "missing", data={"mode": "single"}).upload()
    with pytest.raises(openbot_sdk.DataUploadError, match="not found"):
        DataUpload(
            client,
            "missing",
            path=tmp_path / "missing.mp4",
            data={"mode": "single"},
        ).upload()
    with pytest.raises(ValueError, match="part_concurrency"):
        DataUpload(client, "bad-concurrency", path=source, data={"mode": "single"}).upload(
            part_concurrency=0
        )
    with pytest.raises(openbot_sdk.APIResponseError, match="Unsupported upload mode"):
        DataUpload(client, "bad-mode", path=source, data={"mode": "future"}).upload()
    with pytest.raises(openbot_sdk.APIResponseError, match="invalid part metadata"):
        DataUpload(
            client,
            "bad-metadata",
            path=source,
            data={"mode": "multipart", "part_size_bytes": 0, "part_count": 0},
        ).upload()
    with pytest.raises(openbot_sdk.APIResponseError, match="part count"):
        DataUpload(
            client,
            "bad-count",
            path=source,
            data={"mode": "multipart", "part_size_bytes": 4, "part_count": 1},
        ).upload()
    client.close()


@pytest.mark.parametrize(
    ("parts", "response_headers", "message"),
    [
        ([{"part_number": 2, "url": "https://r2.example.test/wrong"}], {}, "unexpected"),
        ([{"part_number": 1, "url": "https://r2.example.test/no-etag"}], {}, "no ETag"),
    ],
)
def test_multipart_rejects_bad_signer_contract(
    mock_api: respx.MockRouter,
    tmp_path: Path,
    parts: list[dict[str, Any]],
    response_headers: dict[str, str],
    message: str,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"data")
    mock_api.post("/data/uploads/upload_bad/parts").respond(200, json={"parts": parts})
    if parts[0]["part_number"] == 1:
        mock_api.put(str(parts[0]["url"])).respond(200, headers=response_headers)
    client = openbot_sdk.Client(api_key="test-key")
    upload = DataUpload(
        client,
        "upload_bad",
        path=source,
        data={
            "mode": "multipart",
            "part_size_bytes": 4,
            "part_count": 1,
        },
    )

    with pytest.raises(openbot_sdk.APIResponseError, match=message):
        upload.upload(part_concurrency=1)
    client.close()


def test_all_listing_helpers_preserve_filters_and_resource_types(
    mock_api: respx.MockRouter,
) -> None:
    uploads_route = mock_api.get("/data/uploads").respond(
        200,
        json={
            "data": [{"id": "upload_1", "status": "ready", "future_field": "kept"}],
            "next_page_token": None,
        },
    )
    datasets_route = mock_api.get("/data/datasets").respond(
        200,
        json={"data": [{"id": "data_1", "format": "lerobot"}], "next_page_token": None},
    )
    jobs_route = mock_api.get("/data/jobs").respond(
        200,
        json={"data": [{"id": "job_1", "status": "queued"}], "next_page_token": None},
    )
    client = openbot_sdk.Client(api_key="test-key")

    uploads = list(client.data.list_uploads(status="ready", page_size=10))
    datasets = list(
        client.data.list_datasets(format="lerobot", embodiment="franka", page_size=11)
    )
    jobs = list(
        client.data.list_jobs(
            status="queued",
            dataset_id="data_1",
            job_type="subtask",
            page_size=12,
        )
    )

    assert isinstance(uploads[0], DataUpload)
    assert uploads[0]["future_field"] == "kept"
    assert datasets[0].id == "data_1"
    assert datasets[0].format == "lerobot"
    assert jobs[0].id == "job_1"
    assert uploads_route.calls[0].request.url.params["status"] == "ready"
    assert datasets_route.calls[0].request.url.params["embodiment"] == "franka"
    assert jobs_route.calls[0].request.url.params["job_type"] == "subtask"
    client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"items": [], "next_page_token": None},
        {"data": ["not-an-object"], "next_page_token": None},
        {"data": [{"id": None}], "next_page_token": None},
        {"data": [{"id": "upload_1"}], "next_page_token": 123},
    ],
)
def test_pagination_rejects_malformed_payloads(
    mock_api: respx.MockRouter,
    payload: dict[str, Any],
) -> None:
    mock_api.get("/data/uploads").respond(200, json=payload)
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError):
        list(client.data.list_uploads())
    with pytest.raises(ValueError, match="page_size"):
        list(client.data.list_uploads(page_size=101))
    with pytest.raises(ValueError, match="page_size"):
        list(client.data.list_uploads(page_size=True))
    client.close()


def test_export_exposes_platform_retention_metadata() -> None:
    export = openbot_sdk.DataExport(
        {
            "id": "export_1",
            "status": "ready",
            "format": "jsonl",
            "retention_until": 1234,
            "future_field": "kept",
        }
    )

    assert export.retention_until == 1234
    assert export["future_field"] == "kept"


def test_upload_job_export_and_artifact_deletion_lifecycle(
    mock_api: respx.MockRouter,
) -> None:
    upload_delete = mock_api.delete("/data/uploads/upload_1").respond(204)
    export_delete = mock_api.delete("/data/exports/export_1").respond(204)
    artifact_delete = mock_api.delete("/data/jobs/job_1/artifacts").respond(204)
    upload_get = mock_api.get("/data/uploads/upload_1").respond(
        200,
        json={"id": "upload_1", "status": "ready", "mode": "single"},
    )
    job_get = mock_api.get("/data/jobs/job_1").respond(
        200,
        json={"id": "job_1", "status": "queued"},
    )
    client = openbot_sdk.Client(api_key="test-key")

    upload = client.data.get_upload("upload_1")
    job = client.data.get_job("job_1")
    upload.delete()
    client.data.delete_upload("upload_1")
    client.data.delete_export("export_1")
    client.data.delete_job_artifacts("job_1")

    assert upload_get.called and job_get.called
    assert upload.status == "deleted"
    assert job.status == "queued"
    assert upload_delete.call_count == 2
    assert export_delete.called and artifact_delete.called
    client.close()


def test_queued_running_and_already_cancelled_jobs_are_idempotent(
    mock_api: respx.MockRouter,
) -> None:
    cancel = mock_api.post("/data/jobs/job_1/cancel")
    cancel.side_effect = [
        Response(202, json={"id": "job_1", "status": "queued", "cancel_requested": True}),
        Response(202, json={"id": "job_1", "status": "running", "cancel_requested": True}),
        Response(200, json={"id": "job_1", "status": "cancelled", "cancel_requested": True}),
    ]
    client = openbot_sdk.Client(api_key="test-key")

    queued = openbot_sdk.DataJob(client, "job_1", data={"status": "queued"}).cancel()
    running = openbot_sdk.DataJob(client, "job_1", data={"status": "running"}).cancel()
    cancelled = openbot_sdk.DataJob(client, "job_1", data={"status": "cancelled"}).cancel()

    assert queued.cancel_requested and running.cancel_requested and cancelled.cancel_requested
    assert cancelled.status == "cancelled"
    assert cancel.call_count == 3
    assert all(
        call.request.headers["Idempotency-Key"] == "cancel-job_1" for call in cancel.calls
    )
    client.close()


def test_job_terminal_cancelled_and_timeout_are_explicit(
    mock_api: respx.MockRouter,
) -> None:
    mock_api.get("/data/jobs/job_cancelled").respond(
        200,
        json={
            "id": "job_cancelled",
            "status": "cancelled",
            "error": {"code": "cancelled_by_user", "message": "Cancelled by user"},
        },
    )
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.DataJobError, match="Cancelled by user"):
        openbot_sdk.DataJob(client, "job_cancelled").wait(poll_interval=0, timeout=1)
    with pytest.raises(TimeoutError):
        openbot_sdk.DataJob(client, "job_timeout").wait(timeout=0)
    client.close()


def test_artifact_file_like_stream_unknown_fields_and_deleted_resource(
    mock_api: respx.MockRouter,
) -> None:
    content = mock_api.get("/data/artifacts/artifact_1/content")
    content.side_effect = [
        Response(200, content=b"streamed"),
        Response(
            410,
            json={
                "error": {
                    "code": "artifact_deleted",
                    "message": "Artifact was deleted",
                    "retryable": False,
                }
            },
        ),
    ]
    client = openbot_sdk.Client(api_key="test-key")
    artifact = client.data.artifact(
        "artifact_1",
        kind="evidence",
        retention_until=123,
        future_field={"kept": True},
    )
    destination = io.BytesIO()

    assert artifact.download_to(destination) is None
    assert destination.getvalue() == b"streamed"
    assert artifact.get("future_field") == {"kept": True}
    with pytest.raises(openbot_sdk.APIError) as error:
        artifact.download_to(io.BytesIO())
    assert error.value.status_code == 410
    assert error.value.code == "artifact_deleted"
    assert error.value.retryable is False
    client.close()


def test_new_public_methods_have_parameter_and_return_annotations() -> None:
    methods = [
        DataResource.create_upload,
        DataResource.get_upload,
        DataResource.resume_upload,
        DataResource.delete_upload,
        DataResource.list_uploads,
        DataResource.list_datasets,
        DataResource.list_jobs,
        DataResource.list_artifacts,
        DataResource.download_artifact,
        DataResource.head_artifact,
        DataResource.delete_job_artifacts,
        DataUpload.refresh,
        DataUpload.upload,
        DataUpload.wait_until_ready,
        DataUpload.delete,
        DataArtifact.head,
        DataArtifact.download_to,
    ]

    for method in methods:
        signature = inspect.signature(method)
        assert signature.return_annotation is not inspect.Signature.empty, method.__qualname__
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for name, parameter in signature.parameters.items()
            if name != "self"
        ), method.__qualname__


def test_runnable_demo_executes_complete_mocked_public_workflow(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"robot-video")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_demo",
            "status": "pending_upload",
            "mode": "single",
            "upload": {"method": "PUT", "url": "https://r2.example.test/demo"},
        },
    )
    mock_api.put("https://r2.example.test/demo").respond(200)
    mock_api.post("/data/uploads/upload_demo/complete").respond(
        202,
        json={"id": "upload_demo", "status": "verifying", "mode": "single"},
    )
    mock_api.get("/data/uploads/upload_demo").respond(
        200,
        json={"id": "upload_demo", "status": "ready", "mode": "single"},
    )
    register = mock_api.post("/data/datasets").respond(
        202,
        json={"id": "data_demo", "status": "registered"},
    )
    mock_api.post("/data/subtask-jobs").respond(
        202,
        json={"id": "job_demo", "status": "queued", "stage": "queued"},
    )
    mock_api.get("/data/jobs/job_demo").respond(
        200,
        json={
            "id": "job_demo",
            "status": "done",
            "review_output": {
                "id": "review_demo",
                "annotations": {"timeline": {"segments": []}},
            },
        },
    )
    upload_delete = mock_api.delete("/data/uploads/upload_demo").respond(204)
    client = openbot_sdk.Client(api_key="test-key")

    demo = load_demo_module()
    manifest = tmp_path / "manifest.json"
    audit = tmp_path / "audit.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "openbot.dataset_manifest.v1",
                "dataset_fingerprint": "fingerprint-demo",
                "tool_version": "0.0.2",
                "videos": [{"path_base": "dataset", "path": "episode.mp4"}],
            }
        )
    )
    audit.write_text(
        json.dumps(
            {
                "schema_version": "openbot.dataset_audit.v1",
                "summary": {"error": 0, "warning": 0, "info": 0},
                "findings": [],
            }
        )
    )
    provenance = demo.load_preflight_provenance(manifest, audit)
    summary = demo.run_data_workflow(
        client,
        video=video,
        dataset_name="Demo dataset",
        provenance=provenance,
        delete_raw_after_job=True,
        poll_interval=0,
    )

    assert summary == {
        "upload_id": "upload_demo",
        "dataset_id": "data_demo",
        "job_id": "job_demo",
        "review_output_id": "review_demo",
    }
    assert not any(
        call.request.method == "PATCH"
        and "/data/review-outputs/" in call.request.url.path
        for call in mock_api.calls
    )
    register_body = json.loads(register.calls[0].request.read())
    assert register_body["upload_id"] == "upload_demo"
    assert register_body["metadata"]["preflight"] == {
        "manifest_schema_version": "openbot.dataset_manifest.v1",
        "dataset_fingerprint": "fingerprint-demo",
        "tool_version": "0.0.2",
        "audit_schema_version": "openbot.dataset_audit.v1",
        "audit_summary": {"error": 0, "warning": 0, "info": 0},
    }
    assert "episode.mp4" not in json.dumps(register_body["metadata"])
    assert upload_delete.called
    client.close()


def test_runnable_demo_exports_an_already_approved_review_without_reingest(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    export = mock_api.post("/data/review-outputs/review_existing/exports").respond(
        201, json={"id": "export_existing"}
    )
    download = mock_api.get("/data/exports/export_existing/content").respond(
        200, content=b'{"segments":[]}'
    )
    delete = mock_api.delete("/data/exports/export_existing").respond(204)
    client = openbot_sdk.Client(api_key="test-key")
    output = tmp_path / "existing.json"
    demo = load_demo_module()

    summary = demo.export_approved_review_output(
        client,
        review_output_id="review_existing",
        output=output,
        delete_export=True,
    )

    assert summary["review_output_id"] == "review_existing"
    assert output.read_bytes() == b'{"segments":[]}'
    assert export.called and download.called and delete.called
    assert not any(call.request.method == "PATCH" for call in mock_api.calls)
    assert not any(call.request.url.path.endswith("/data/uploads") for call in mock_api.calls)
    client.close()


def test_documentation_navigation_has_no_broken_local_links() -> None:
    repository = Path(__file__).resolve().parents[1]
    documents = [repository / "README.md", *sorted((repository / "docs").rglob("*.md"))]

    for document in documents:
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
            path = target.split("#", 1)[0]
            if not path or path.startswith(("http://", "https://", "mailto:")):
                continue
            assert (document.parent / path).resolve().exists(), (
                f"{document.relative_to(repository)} links to missing {target}"
            )
