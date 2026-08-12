"""Compatibility checks for the 0.2.0 candidate SDK surface."""

from __future__ import annotations

from typing import Any


def openapi_compatibility_errors(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return ["OpenAPI paths must be an object"]
    me = paths.get("/v1/me")
    if not isinstance(me, dict) or "get" not in me:
        errors.append("GET /v1/me is required for API-key context probing")
    required_ego_paths = {
        "/v1/ego/semantic-annotations": "post",
        "/v1/ego/semantic-annotations/{id}": "get",
        "/v1/ego/semantic-annotations/{id}/cancel": "post",
        "/v1/ego/semantic-annotations/{id}/result": "get",
    }
    for path, method in required_ego_paths.items():
        operation = paths.get(path)
        if not isinstance(operation, dict) or method not in operation:
            errors.append(f"{method.upper()} {path} is required for Ego annotation")
    forbidden = ("/v1/bench", "/v1/synth", "/v1/data/")
    for path in paths:
        removed = isinstance(path, str) and any(
            path == prefix or path.startswith(prefix) for prefix in forbidden
        )
        if removed:
            errors.append(f"removed product path is still published: {path}")
    schemes = spec.get("components", {}).get("securitySchemes", {})
    if not isinstance(schemes, dict) or not any(
        isinstance(value, dict)
        and value.get("type") == "http"
        and value.get("scheme") == "bearer"
        for value in schemes.values()
    ):
        errors.append("a Bearer security scheme is required")
    return errors
