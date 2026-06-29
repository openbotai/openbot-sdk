import os

import pytest
import respx

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
