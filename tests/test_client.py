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
    mock_api.get("/bench/runs/run_123").respond(200, json={"id": "run_123", "status": "running"})

    client = openbot_sdk.Client(api_key="test-key")
    data = client._request("GET", "/bench/runs/run_123")

    assert data["id"] == "run_123"
    client.close()


def test_client_request_raises_api_error(mock_api: respx.MockRouter) -> None:
    mock_api.get("/bench/runs/run_123").respond(404, text="Not found")

    client = openbot_sdk.Client(api_key="test-key")
    with pytest.raises(openbot_sdk.APIError) as exc_info:
        client._request("GET", "/bench/runs/run_123")

    assert exc_info.value.status_code == 404
    client.close()


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
    mock_api.get("/bench/runs/run_123").mock(
        side_effect=ConnectError("offline", request=Request("GET", "https://api.openbot.ai"))
    )
    client = openbot_sdk.Client(api_key="test-key", max_retries=0)

    with pytest.raises(openbot_sdk.NetworkError, match="offline"):
        client._request("GET", "/bench/runs/run_123")
    client.close()


def test_client_rejects_invalid_success_payload(mock_api: respx.MockRouter) -> None:
    mock_api.get("/bench/runs/run_123").respond(200, text="not-json")
    client = openbot_sdk.Client(api_key="test-key")

    with pytest.raises(openbot_sdk.APIResponseError, match="non-JSON"):
        client._request("GET", "/bench/runs/run_123")
    client.close()


def test_client_retries_idempotent_request(mock_api: respx.MockRouter) -> None:
    route = mock_api.get("/bench/runs/run_123")
    route.side_effect = [
        Response(503, text="busy"),
        Response(200, json={"id": "run_123", "status": "running"}),
    ]
    client = openbot_sdk.Client(api_key="test-key", retry_backoff=0)

    data = client._request("GET", "/bench/runs/run_123")

    assert data["id"] == "run_123"
    assert route.call_count == 2
    client.close()
