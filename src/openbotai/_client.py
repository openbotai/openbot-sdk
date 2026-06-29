"""OpenBot.ai Python client."""

from __future__ import annotations

import os
from typing import Any, cast

import httpx

from openbotai._bench import BenchResource
from openbotai._errors import APIError, AuthenticationError

DEFAULT_BASE_URL = "https://api.openbot.ai/v1"


class Client:
    """
    Client for the OpenBot.ai API.

    Args:
        api_key: OpenBot.ai API key. Falls back to the ``OPENBOT_API_KEY``
            environment variable if not provided.
        base_url: Base URL for the OpenBot.ai API.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENBOT_API_KEY")
        if not self.api_key:
            raise AuthenticationError(
                "API key is required. Provide it via the api_key argument "
                "or set the OPENBOT_API_KEY environment variable."
            )

        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": f"openbotai-python/{self._version()}",
            },
            timeout=60.0,
        )
        self.bench = BenchResource(self)

    def _version(self) -> str:
        from openbotai._version import __version__

        return __version__

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request and return the JSON response."""
        request_headers = {**headers} if headers else None
        response = self._http.request(
            method, path, json=json, params=params, headers=request_headers
        )
        if response.status_code >= 400:
            raise APIError(
                f"API request failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )
        return cast(dict[str, Any], response.json())

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
