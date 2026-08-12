from openbot_sdk._contract import openapi_compatibility_errors


def test_neutral_sdk_accepts_api_context_contract() -> None:
    spec = {
        "paths": {"/v1/me": {"get": {}}},
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "http", "scheme": "bearer"},
            }
        },
    }
    assert openapi_compatibility_errors(spec) == []


def test_neutral_sdk_rejects_removed_product_paths() -> None:
    spec = {
        "paths": {
            "/v1/me": {"get": {}},
            "/v1/bench/rollouts": {"post": {}},
            "/v1/synth/jobs": {"post": {}},
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "http", "scheme": "bearer"},
            }
        },
    }
    assert openapi_compatibility_errors(spec) == [
        "removed product path is still published: /v1/bench/rollouts",
        "removed product path is still published: /v1/synth/jobs",
    ]
