import importlib.util
import json
from io import BytesIO
from pathlib import Path
from typing import Any


def load_release_checker() -> Any:
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_hosted_release.py"
    spec = importlib.util.spec_from_file_location("openbot_sdk_release_check", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_check_uses_an_explicit_json_user_agent(monkeypatch: Any) -> None:
    checker = load_release_checker()
    observed: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> BytesIO:
        observed["request"] = request
        observed["timeout"] = timeout
        return BytesIO(json.dumps({"products": {"data": "0.0.2"}}).encode())

    monkeypatch.setattr(checker.urllib.request, "urlopen", fake_urlopen)

    release = checker.load_release("https://api.openbot.ai/v1/release")

    assert release["products"]["data"] == "0.0.2"
    assert observed["timeout"] == 20
    assert observed["request"].get_header("Accept") == "application/json"
    assert observed["request"].get_header("User-agent") == (
        "openbot-sdk-release-check/0.0.2"
    )


def test_release_check_reports_http_status_without_response_body(monkeypatch: Any) -> None:
    checker = load_release_checker()

    def fake_urlopen(request: Any, timeout: float) -> BytesIO:
        del request, timeout
        raise checker.urllib.error.HTTPError(
            "https://api.openbot.ai/v1/release",
            403,
            "Forbidden provider detail",
            {},
            None,
        )

    monkeypatch.setattr(checker.urllib.request, "urlopen", fake_urlopen)

    try:
        checker.load_release("https://api.openbot.ai/v1/release")
    except RuntimeError as error:
        assert str(error) == "Hosted release endpoint returned HTTP 403"
    else:
        raise AssertionError("expected hosted release check to fail")
