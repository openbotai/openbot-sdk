from openbot_sdk._contract import openapi_compatibility_errors


def required_paths() -> dict[str, dict[str, object]]:
    return {
        "/v1/me": {"get": {}},
        "/v1/ego/semantic-annotations": {"post": {}},
        "/v1/ego/semantic-annotations/{id}": {"get": {}},
        "/v1/ego/semantic-annotations/{id}/cancel": {"post": {}},
        "/v1/ego/semantic-annotations/{id}/result": {"get": {}},
    }


def test_neutral_sdk_accepts_api_context_contract() -> None:
    spec = {
        "paths": required_paths(),
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
            **required_paths(),
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


def test_sdk_rejects_an_openapi_without_the_ego_result_route() -> None:
    paths = required_paths()
    del paths["/v1/ego/semantic-annotations/{id}/result"]
    errors = openapi_compatibility_errors({
        "paths": paths,
        "components": {"securitySchemes": {"Bearer": {"type": "http", "scheme": "bearer"}}},
    })
    assert errors == [
        "GET /v1/ego/semantic-annotations/{id}/result is required for Ego annotation"
    ]
