"""Safe construction of authenticated API paths."""

from __future__ import annotations

import re

from openbot_sdk._errors import APIResponseError

_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,255}$")


def resource_id(value: object, *, name: str = "resource id") -> str:
    """Validate one opaque path segment before it reaches URL normalization."""
    normalized = str(value)
    if (
        normalized in {"", ".", ".."}
        or not _PATH_SEGMENT.fullmatch(normalized)
        or "/" in normalized
        or "\\" in normalized
    ):
        raise APIResponseError(f"{name} has an invalid path-safe format")
    return normalized


def api_path(*segments: object) -> str:
    """Build a path from literal or validated opaque segments."""
    return "/" + "/".join(resource_id(segment, name="API path segment") for segment in segments)
