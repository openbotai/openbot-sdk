import pytest
import respx
from httpx import Response

import openbotai


@pytest.fixture
def mock_api() -> respx.MockRouter:
    with respx.mock(base_url="https://api.openbot.ai/v1") as router:
        yield router


def test_bench_rollout_queues_run(mock_api: respx.MockRouter) -> None:
    mock_api.post("/bench/rollouts").respond(
        200,
        json={
            "id": "run_8c91a4",
            "status": "queued",
            "result_url": "https://api.openbot.ai/v1/bench/runs/run_8c91a4",
        },
    )

    client = openbotai.Client(api_key="test-key")
    run = client.bench.rollout(
        policy="openvla-7b",
        embodiment="franka_panda",
        task="kitchen_handover",
        rollouts=200,
        seeds=10,
    )

    assert run.id == "run_8c91a4"
    assert run.status == "queued"
    client.close()


def test_bench_rollout_includes_idempotency_key(mock_api: respx.MockRouter) -> None:
    request = mock_api.post("/bench/rollouts").respond(
        200,
        json={"id": "run_abc", "status": "queued"},
    )

    client = openbotai.Client(api_key="test-key")
    client.bench.rollout(
        policy="openvla-7b",
        embodiment="franka_panda",
        task="kitchen_handover",
        idempotency_key="my-key",
    )

    assert request.calls[0].request.headers["Idempotency-Key"] == "my-key"
    client.close()


def test_run_wait_polls_until_success(mock_api: respx.MockRouter) -> None:
    get_route = mock_api.get("/bench/runs/run_8c91a4")
    get_route.side_effect = [
        Response(200, json={"id": "run_8c91a4", "status": "running"}),
        Response(
            200,
            json={
                "id": "run_8c91a4",
                "status": "success",
                "result": {
                    "task_success": 0.73,
                    "intervention_rate": 0.14,
                    "sim_to_real_gap": -0.29,
                    "subtask": {"handover": 0.60},
                },
            },
        ),
    ]

    client = openbotai.Client(api_key="test-key")
    run = openbotai.Run(client, "run_8c91a4")
    result = run.wait(poll_interval=0.01, timeout=1.0)

    assert result.task_success == pytest.approx(0.73)
    assert result.intervention_rate == pytest.approx(0.14)
    assert result.sim_to_real_gap == pytest.approx(-0.29)
    assert result.subtask["handover"] == pytest.approx(0.60)
    client.close()


def test_run_wait_raises_on_failure(mock_api: respx.MockRouter) -> None:
    mock_api.get("/bench/runs/run_8c91a4").respond(
        200,
        json={"id": "run_8c91a4", "status": "failed"},
    )

    client = openbotai.Client(api_key="test-key")
    run = openbotai.Run(client, "run_8c91a4")

    with pytest.raises(openbotai.RunError):
        run.wait(poll_interval=0.01, timeout=1.0)

    client.close()
