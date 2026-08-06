import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response

import openbot_sdk


@pytest.fixture
def mock_api() -> respx.MockRouter:
    with respx.mock(base_url="https://api.openbot.ai/v1") as router:
        yield router


def test_single_upload_never_forwards_openbot_authorization(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"robot-video")
    create = mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_123",
            "status": "pending_upload",
            "mode": "single",
            "upload": {
                "method": "PUT",
                "url": "https://r2.example.test/upload?signature=secret",
                "headers": {"Content-Type": "video/mp4", "If-None-Match": "*"},
            },
        },
    )
    put = mock_api.put("https://r2.example.test/upload?signature=secret").respond(200)
    complete = mock_api.post("/data/uploads/upload_123/complete")
    complete.side_effect = [
        Response(503),
        Response(
            202,
            json={"id": "upload_123", "status": "verifying", "mode": "single"},
        ),
    ]
    ready = mock_api.get("/data/uploads/upload_123").respond(
        200,
        json={"id": "upload_123", "status": "ready", "retention_until": 1234},
    )
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    upload = client.data.create_upload(path=source, idempotency_key="episode-123")
    upload.upload().wait_until_ready(poll_interval=0, timeout=1)

    create_body = json.loads(create.calls[0].request.read())
    assert create_body["checksum_sha256"] == hashlib.sha256(b"robot-video").hexdigest()
    assert create.calls[0].request.headers["Authorization"] == "Bearer test-key"
    assert "Authorization" not in put.calls[0].request.headers
    assert put.calls[0].request.read() == b"robot-video"
    assert json.loads(complete.calls[0].request.read()) == {"parts": []}
    assert complete.call_count == 2
    assert upload.status == "ready"
    assert upload.retention_until == 1234
    assert ready.called
    client.close()


def test_multipart_upload_resumes_completed_parts_and_retries_failed_part(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"abcdefghijkl")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_multi",
            "status": "pending_upload",
            "mode": "multipart",
            "part_size_bytes": 4,
            "part_count": 3,
            "completed_parts": [{"part_number": 1, "etag": "etag-1"}],
        },
    )
    signer = mock_api.post("/data/uploads/upload_multi/parts").respond(
        200,
        json={
            "parts": [
                {"part_number": 2, "url": "https://r2.example.test/part-2"},
                {"part_number": 3, "url": "https://r2.example.test/part-3"},
            ]
        },
    )
    part_two = mock_api.put("https://r2.example.test/part-2")
    part_two.side_effect = [
        Response(503),
        Response(200, headers={"ETag": "etag-2"}),
    ]
    part_three = mock_api.put("https://r2.example.test/part-3").respond(
        200, headers={"ETag": "etag-3"}
    )
    complete = mock_api.post("/data/uploads/upload_multi/complete").respond(
        202,
        json={"id": "upload_multi", "status": "verifying", "mode": "multipart"},
    )
    client = openbot_sdk.Client(api_key="test-key", max_retries=1, retry_backoff=0)

    upload = client.data.create_upload(path=source)
    upload.upload(part_concurrency=2)

    signed_body = json.loads(signer.calls[0].request.read())
    assert signed_body == {"part_numbers": [2, 3]}
    assert part_two.call_count == 2
    assert part_two.calls[-1].request.read() == b"efgh"
    assert part_three.calls[0].request.read() == b"ijkl"
    assert "Authorization" not in part_two.calls[-1].request.headers
    complete_body = json.loads(complete.calls[0].request.read())
    assert complete_body["parts"] == [
        {"part_number": 1, "etag": "etag-1"},
        {"part_number": 2, "etag": "etag-2"},
        {"part_number": 3, "etag": "etag-3"},
    ]
    client.close()


def test_multipart_retry_only_resends_parts_that_did_not_finish(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"abcdefgh")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_retry",
            "status": "pending_upload",
            "mode": "multipart",
            "part_size_bytes": 4,
            "part_count": 2,
        },
    )
    signer = mock_api.post("/data/uploads/upload_retry/parts")
    signer.side_effect = [
        Response(
            200,
            json={
                "parts": [
                    {"part_number": 1, "url": "https://r2.example.test/retry-1"},
                    {"part_number": 2, "url": "https://r2.example.test/retry-2"},
                ]
            },
        ),
        Response(
            200,
            json={
                "parts": [
                    {"part_number": 2, "url": "https://r2.example.test/retry-2"},
                ]
            },
        ),
    ]
    first = mock_api.put("https://r2.example.test/retry-1").respond(
        200, headers={"ETag": "etag-1"}
    )
    second = mock_api.put("https://r2.example.test/retry-2")
    second.side_effect = [
        Response(503),
        Response(200, headers={"ETag": "etag-2"}),
    ]
    complete = mock_api.post("/data/uploads/upload_retry/complete").respond(
        202,
        json={"id": "upload_retry", "status": "verifying", "mode": "multipart"},
    )
    client = openbot_sdk.Client(api_key="test-key", max_retries=0)
    upload = client.data.create_upload(path=source)

    with pytest.raises(openbot_sdk.DataUploadError):
        upload.upload(part_concurrency=2)
    upload.upload(part_concurrency=1)

    assert json.loads(signer.calls[0].request.read()) == {"part_numbers": [1, 2]}
    assert json.loads(signer.calls[1].request.read()) == {"part_numbers": [2]}
    assert first.call_count == 1
    assert second.call_count == 2
    assert json.loads(complete.calls[0].request.read()) == {
        "parts": [
            {"part_number": 1, "etag": "etag-1"},
            {"part_number": 2, "etag": "etag-2"},
        ]
    }
    client.close()


def test_upload_rejection_and_timeout_are_explicit(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"bad")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_bad",
            "status": "pending_upload",
            "mode": "single",
            "upload": {"url": "https://r2.example.test/bad", "method": "PUT"},
        },
    )
    mock_api.put("https://r2.example.test/bad").respond(200)
    mock_api.post("/data/uploads/upload_bad/complete").respond(
        202, json={"id": "upload_bad", "status": "verifying", "mode": "single"}
    )
    mock_api.get("/data/uploads/upload_bad").respond(
        200,
        json={
            "id": "upload_bad",
            "status": "rejected",
            "error": {"code": "checksum_mismatch", "message": "Checksum mismatch"},
        },
    )
    client = openbot_sdk.Client(api_key="test-key")
    upload = client.data.create_upload(path=source).upload()

    with pytest.raises(openbot_sdk.DataUploadError, match="Checksum mismatch"):
        upload.wait_until_ready(poll_interval=0, timeout=1)
    with pytest.raises(TimeoutError):
        openbot_sdk.DataUpload(client, "upload_wait").wait_until_ready(timeout=0)
    client.close()


def test_pagination_preserves_filters_and_deduplicates_resources(
    mock_api: respx.MockRouter,
) -> None:
    route = mock_api.get("/data/jobs")
    route.side_effect = [
        Response(
            200,
            json={
                "data": [{"id": "job_2", "status": "running"}],
                "next_page_token": "opaque-next",
            },
        ),
        Response(
            200,
            json={
                "data": [
                    {"id": "job_2", "status": "running"},
                    {"id": "job_1", "status": "running"},
                ],
                "next_page_token": None,
            },
        ),
    ]
    client = openbot_sdk.Client(api_key="test-key")

    jobs = list(client.data.list_jobs(status="running", dataset_id="data_123", page_size=1))

    assert [job.id for job in jobs] == ["job_2", "job_1"]
    assert route.calls[0].request.url.params["status"] == "running"
    assert route.calls[1].request.url.params["dataset_id"] == "data_123"
    assert route.calls[1].request.url.params["page_token"] == "opaque-next"
    client.close()


def test_pagination_rejects_repeated_page_token(mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/data/jobs")
    route.side_effect = [
        Response(200, json={"data": [{"id": "job_1"}], "next_page_token": "same"}),
        Response(200, json={"data": [{"id": "job_1"}], "next_page_token": "same"}),
    ]
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError, match="repeated next_page_token"):
        list(client.data.list_jobs())

    client.close()


def test_upload_id_job_progress_and_cancel(mock_api: respx.MockRouter) -> None:
    create = mock_api.post("/data/subtask-jobs").respond(
        202,
        json={
            "id": "job_123",
            "status": "running",
            "stage": "processing_video",
            "stage_updated_at": 123,
            "attempt_count": 2,
            "cancel_requested": False,
            "warnings": [{"code": "slow_decode"}],
        },
    )
    cancel = mock_api.post("/data/jobs/job_123/cancel").respond(
        202,
        json={"id": "job_123", "status": "running", "cancel_requested": True},
    )
    client = openbot_sdk.Client(api_key="test-key")

    job = client.data.subtask_job(
        dataset_id="data_123",
        upload_id="upload_123",
        video_key="observation.images.top",
        taxonomy=["reach", "grasp"],
    )

    assert json.loads(create.calls[0].request.read())["upload_id"] == "upload_123"
    assert job.stage == "processing_video"
    assert job.stage_updated_at == 123
    assert job.attempt_count == 2
    assert job.warnings == [{"code": "slow_decode"}]
    assert job.cancel().cancel_requested is True
    assert cancel.calls[0].request.headers["Idempotency-Key"] == "cancel-job_123"
    with pytest.raises(ValueError, match="Exactly one"):
        client.data.subtask_job(
            dataset_id="data_123",
            upload_id="upload_123",
            video_url="https://example.test/video.mp4",
            video_key="top",
            taxonomy=[],
        )
    client.close()


def test_authenticated_artifact_stream_head_range_and_delete(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    listing = mock_api.get("/data/jobs/job_123/artifacts").respond(
        200,
        json={
            "data": [
                {
                    "id": "artifact_123",
                    "kind": "evidence",
                    "content_type": "video/mp4",
                    "size_bytes": 4,
                    "retention_until": 999,
                }
            ],
            "next_page_token": None,
        },
    )
    head = mock_api.head("/data/artifacts/artifact_123/content").respond(
        200, headers={"Content-Length": "4", "Content-Type": "video/mp4"}
    )
    content = mock_api.get("/data/artifacts/artifact_123/content").respond(
        206, content=b"data"
    )
    delete = mock_api.delete("/data/jobs/job_123/artifacts").respond(204)
    client = openbot_sdk.Client(api_key="test-key")

    artifact = list(client.data.list_artifacts("job_123"))[0]
    target = tmp_path / "artifact.mp4"
    result = artifact.download_to(target, byte_range="bytes=0-3")
    headers = artifact.head()
    client.data.delete_job_artifacts("job_123")

    assert listing.called
    assert artifact.kind == "evidence"
    assert artifact.retention_until == 999
    assert result == target
    assert target.read_bytes() == b"data"
    assert content.calls[0].request.headers["Range"] == "bytes=0-3"
    assert content.calls[0].request.headers["Authorization"] == "Bearer test-key"
    assert headers["content-length"] == "4"
    assert head.called and delete.called
    client.close()


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):  # type: ignore[no-untyped-def]
        yield b"partial"
        raise httpx.ReadError("connection lost")


def test_interrupted_artifact_download_removes_partial_file(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    mock_api.get("/data/artifacts/artifact_broken/content").mock(
        return_value=Response(200, stream=BrokenStream())
    )
    client = openbot_sdk.Client(api_key="test-key")
    target = tmp_path / "broken.bin"

    with pytest.raises(openbot_sdk.NetworkError, match="connection lost"):
        client.data.download_artifact("artifact_broken", target)

    assert not target.exists()
    assert not (tmp_path / "broken.bin.part").exists()
    client.close()


@pytest.mark.parametrize(
    ("operation", "malicious_id"),
    [
        ("upload", "../exports/export_1"),
        ("review", "../datasets/data_1"),
        ("artifact", "../../datasets/data_1"),
    ],
)
def test_resource_ids_cannot_rewrite_authenticated_paths(
    operation: str,
    malicious_id: str,
) -> None:
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError, match="path-safe"):
        if operation == "upload":
            client.data.delete_upload(malicious_id)
        elif operation == "review":
            client.data.review(malicious_id, status="rejected")
        else:
            client.data.download_artifact(malicious_id, Path("unused"))

    client.close()


@pytest.mark.parametrize(
    "upload_instruction",
    [
        {"url": "http://r2.example.test/object", "method": "PUT"},
        {"url": "https://r2.example.test/object", "method": "POST"},
        {
            "url": "https://r2.example.test/object",
            "method": "PUT",
            "headers": {"Authorization": "Bearer must-not-leak"},
        },
    ],
)
def test_presigned_upload_rejects_insecure_url_and_sensitive_headers(
    mock_api: respx.MockRouter,
    tmp_path: Path,
    upload_instruction: dict[str, object],
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_unsafe",
            "status": "pending_upload",
            "mode": "single",
            "size_bytes": 5,
            "checksum_sha256": hashlib.sha256(b"video").hexdigest(),
            "upload": upload_instruction,
        },
    )
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError):
        client.data.create_upload(path=source).upload()

    client.close()


def test_presigned_redirect_is_not_treated_as_upload_success(
    mock_api: respx.MockRouter,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video")
    mock_api.post("/data/uploads").respond(
        201,
        json={
            "id": "upload_redirect",
            "status": "pending_upload",
            "mode": "single",
            "upload": {
                "url": "https://r2.example.test/object",
                "method": "PUT",
            },
        },
    )
    put = mock_api.put("https://r2.example.test/object").respond(
        307,
        headers={"Location": "https://other.example.test/object"},
    )
    client = openbot_sdk.Client(api_key="test-key", max_retries=0)

    with pytest.raises(openbot_sdk.DataUploadError, match="status 307"):
        client.data.create_upload(path=source).upload()

    assert put.called
    client.close()
