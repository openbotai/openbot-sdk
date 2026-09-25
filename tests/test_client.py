import os

import pytest
import respx
from httpx import ConnectError, Request, Response

import openbot_sdk
from openbot_sdk import AuthenticationError


@pytest.fixture
def mock_api() -> respx.MockRouter:
    with respx.mock(base_url="https://api.openbot.ai/v1") as router:
        yield router


def test_client_requires_api_key() -> None:
    os.environ.pop("OPENBOT_API_KEY", None)
    with pytest.raises(AuthenticationError):
        openbot_sdk.Client()


def test_client_accepts_api_key_argument() -> None:
    client = openbot_sdk.Client(api_key="test-key")
    assert client.api_key == "test-key"
    client.close()


def test_client_uses_environment_variable() -> None:
    os.environ["OPENBOT_API_KEY"] = "env-key"
    client = openbot_sdk.Client()
    assert client.api_key == "env-key"
    client.close()
    os.environ.pop("OPENBOT_API_KEY", None)


def test_client_request_success(mock_api: respx.MockRouter) -> None:
    mock_api.get("/me").respond(200, json={"key_id": "key_123", "scopes": ["api:invoke"]})

    client = openbot_sdk.Client(api_key="test-key")
    data = client.request("GET", "/me")

    assert data["key_id"] == "key_123"
    client.close()


def test_client_exposes_only_platform_resources() -> None:
    client = openbot_sdk.Client(api_key="test-key")
    assert not hasattr(client, "bench")
    assert not hasattr(client, "synth")
    assert not hasattr(client, "data")
    client.close()


def test_client_request_raises_api_error(mock_api: respx.MockRouter) -> None:
    mock_api.get("/unknown").respond(404, text="Not found")

    client = openbot_sdk.Client(api_key="test-key")
    with pytest.raises(openbot_sdk.APIError) as exc_info:
        client._request("GET", "/unknown")

    assert exc_info.value.status_code == 404
    client.close()


def test_client_exposes_structured_api_error(mock_api: respx.MockRouter) -> None:
    mock_api.get("/status").respond(
        409,
        json={
            "error": {
                "code": "conflict",
                "message": "The request conflicts with current state",
                "retryable": False,
            }
        },
    )
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIError) as exc_info:
        client.request("GET", "/status")

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "conflict"
    assert exc_info.value.retryable is False
    client.close()


def test_client_request_bytes(mock_api: respx.MockRouter) -> None:
    mock_api.get("/artifact").respond(200, content=b"artifact-bytes")
    client = openbot_sdk.Client(api_key="test-key")

    assert client.request_bytes("GET", "/artifact") == b"artifact-bytes"
    client.close()


def test_closed_client_rejects_requests() -> None:
    client = openbot_sdk.Client(api_key="test-key")
    client.close()

    with pytest.raises(openbot_sdk.ClientClosedError):
        client.request("GET", "/status")


def test_client_rejects_insecure_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        openbot_sdk.Client(api_key="test-key", base_url="http://api.example.test/v1")


def test_client_allows_explicit_local_http_for_testing() -> None:
    client = openbot_sdk.Client(
        api_key="test-key",
        base_url="http://127.0.0.1:8787/v1",
        allow_insecure_http=True,
    )
    client.close()


def test_client_wraps_network_errors(mock_api: respx.MockRouter) -> None:
    mock_api.get("/me").mock(
        side_effect=ConnectError("offline", request=Request("GET", "https://api.openbot.ai"))
    )
    client = openbot_sdk.Client(api_key="test-key", max_retries=0)

    with pytest.raises(openbot_sdk.NetworkError, match="offline"):
        client._request("GET", "/me")
    client.close()


def test_client_rejects_invalid_success_payload(mock_api: respx.MockRouter) -> None:
    mock_api.get("/me").respond(200, text="not-json")
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError, match="non-JSON"):
        client._request("GET", "/me")
    client.close()


def test_client_retries_idempotent_request(mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/me")
    route.side_effect = [
        Response(503, text="busy"),
        Response(200, json={"key_id": "key_123", "scopes": ["api:invoke"]}),
    ]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    data = client._request("GET", "/me")

    assert data["key_id"] == "key_123"
    assert route.call_count == 2
    client.close()


def test_keyed_mutation_does_not_retry_a_burned_key_after_502(
    mock_api: respx.MockRouter,
) -> None:
    route = mock_api.post("/invoke/judge")
    route.side_effect = [
        Response(502, json={"error": {"code": "upstream_error", "message": "HTTP 500"}}),
        Response(409, json={"error": {"code": "upstream_error", "message": "failed"}}),
    ]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    with pytest.raises(openbot_sdk.APIError) as exc_info:
        client.request("POST", "/invoke/judge", json={}, headers={"Idempotency-Key": "key-00001"})

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "upstream_error"
    assert route.call_count == 1
    client.close()


def test_keyed_mutation_waits_for_an_in_progress_invocation(
    mock_api: respx.MockRouter,
) -> None:
    route = mock_api.post("/invoke/judge")
    route.side_effect = [
        ConnectError("reset"),
        Response(409, json={"error": {"code": "invocation_in_progress", "message": "busy"}}),
        Response(200, json={"verdict": "accept"}),
    ]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    data = client.request(
        "POST", "/invoke/judge", json={}, headers={"Idempotency-Key": "key-00001"}
    )

    assert data == {"verdict": "accept"}
    assert route.call_count == 3
    assert {call.request.headers["Idempotency-Key"] for call in route.calls} == {"key-00001"}
    client.close()


def test_keyed_mutation_retries_settlement_pending(mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/invoke/judge")
    route.side_effect = [
        Response(503, json={"error": {"code": "settlement_pending", "message": "retry"}}),
        Response(200, json={"verdict": "accept"}),
    ]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    data = client.request(
        "POST", "/invoke/judge", json={}, headers={"Idempotency-Key": "key-00001"}
    )

    assert data == {"verdict": "accept"}
    assert route.call_count == 2
    client.close()


def test_keyed_mutation_does_not_retry_other_conflicts(mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/invoke/judge")
    route.respond(409, json={"error": {"code": "idempotency_key_conflict", "message": "x"}})
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    with pytest.raises(openbot_sdk.APIError) as exc_info:
        client.request("POST", "/invoke/judge", json={}, headers={"Idempotency-Key": "key-00001"})

    assert exc_info.value.code == "idempotency_key_conflict"
    assert route.call_count == 1
    client.close()


def test_idempotent_request_still_retries_502(mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/me")
    route.side_effect = [Response(502, text="bad gateway"), Response(200, json={"ok": True})]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    assert client.request("GET", "/me") == {"ok": True}
    assert route.call_count == 2
    client.close()
