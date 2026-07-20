import json

import pytest
import respx
from httpx import Response

import openbot_sdk


@pytest.fixture
def mock_api() -> respx.MockRouter:
    with respx.mock(base_url="https://api.openbot.ai/v1") as router:
        yield router


def test_subtask_job_queues_with_real_processor_contract(mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/data/subtask-jobs").respond(
        202,
        json={
            "id": "djob_123",
            "status": "queued",
            "result_url": "https://api.openbot.ai/v1/data/jobs/djob_123",
            "review_output": None,
        },
    )
    client = openbot_sdk.Client(api_key="test-key")

    job = client.data.subtask_job(
        dataset_id="data_123",
        video_key="observation.images.top",
        video_url="https://signed.example/episode.mp4",
        task_hint="place the block in the bowl",
        taxonomy=["reach", "grasp", "place"],
        sample_fps=2,
        max_frames=24,
        idempotency_key="episode-123",
    )

    assert job.id == "djob_123"
    assert job.status == "queued"
    request = route.calls[0].request
    assert request.headers["Idempotency-Key"] == "episode-123"
    body = json.loads(request.read().decode())
    assert body["segmentation"]["max_frames"] == 24
    assert body["labeling"]["taxonomy"] == ["reach", "grasp", "place"]
    client.close()


def test_data_job_wait_returns_reviewable_timeline(mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/data/jobs/djob_123")
    route.side_effect = [
        Response(200, json={"id": "djob_123", "status": "running"}),
        Response(
            200,
            json={
                "id": "djob_123",
                "status": "done",
                "artifact_url": "https://cdn.openbot.ai/result.json",
                "review_output": {
                    "id": "review_123",
                    "status": "needs_review",
                    "annotations": {
                        "timeline": {
                            "duration_seconds": 4,
                            "segments": [{"id": "segment_001", "confidence": None}],
                        }
                    },
                },
            },
        ),
    ]
    client = openbot_sdk.Client(api_key="test-key")

    result = openbot_sdk.DataJob(client, "djob_123").wait(poll_interval=0.01, timeout=1)

    assert result.review_output_id == "review_123"
    assert result.timeline["segments"][0]["confidence"] is None
    assert result.artifact_url == "https://cdn.openbot.ai/result.json"
    client.close()


def test_data_review_and_export(mock_api: respx.MockRouter) -> None:
    review_route = mock_api.patch("/data/review-outputs/review_123").respond(
        200,
        json={"id": "review_123", "status": "approved", "annotations": {"timeline": {}}},
    )
    export_route = mock_api.post("/data/review-outputs/review_123/exports").respond(
        201,
        json={
            "id": "export_123",
            "status": "ready",
            "format": "lerobot_sidecar",
            "artifact_url": "https://api.openbot.ai/v1/data/exports/export_123/content",
        },
    )
    download_route = mock_api.get("/data/exports/export_123/content").respond(
        200,
        content=b'{"schema_version":"openbot.lerobot.subtasks.v1"}',
        headers={"content-type": "application/json"},
    )
    client = openbot_sdk.Client(api_key="test-key")

    review = client.data.review(
        "review_123",
        status="approved",
        notes="verified",
        annotations={"timeline": {"duration_seconds": 1, "segments": [{"id": "seg"}]}},
        decisions=[{"segment_id": "seg", "action": "approve"}],
    )
    exported = client.data.export("review_123", format="lerobot_sidecar")
    content = client.data.download_export(exported["id"])

    assert review["status"] == "approved"
    assert exported["id"] == "export_123"
    assert b"openbot.lerobot.subtasks.v1" in content
    assert review_route.called
    assert export_route.called
    assert download_route.calls[0].request.headers["authorization"] == "Bearer test-key"
    client.close()


def test_data_job_wait_raises_on_failure(mock_api: respx.MockRouter) -> None:
    mock_api.get("/data/jobs/djob_failed").respond(
        200,
        json={"id": "djob_failed", "status": "failed", "error_message": "decode failed"},
    )
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.DataJobError, match="decode failed"):
        openbot_sdk.DataJob(client, "djob_failed").wait(poll_interval=0.01, timeout=1)

    client.close()
