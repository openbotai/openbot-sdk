"""OpenBot.ai Python client."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, cast
from urllib.parse import urlparse

import httpx

from openbot_sdk._errors import (
    APIError,
    APIResponseError,
    AuthenticationError,
    ClientClosedError,
    NetworkError,
)

DEFAULT_BASE_URL = "https://api.openbot.ai/v1"
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
# A mutation's Idempotency-Key is bound to its first outcome. The gateway burns
# the key when the upstream fails (502), so a same-key retry would only turn the
# real error into a 409; 502 is therefore never retried for mutations.
KEYED_MUTATION_RETRYABLE_STATUS_CODES = frozenset({429, 503, 504})
# The first call with this key is still running; waiting and replaying the same
# key eventually returns the stored result without a second charge.
IN_PROGRESS_ERROR_CODES = frozenset({"invocation_in_progress"})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})


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
        timeout: float = 60.0,
        download_timeout: float = 300.0,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        allow_insecure_http: bool = False,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENBOT_API_KEY")
        if not self.api_key:
            raise AuthenticationError(
                "API key is required. Provide it via the api_key argument "
                "or set the OPENBOT_API_KEY environment variable."
            )

        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed_url.scheme != "https" and not allow_insecure_http:
            raise ValueError(
                "base_url must use HTTPS; pass allow_insecure_http=True only for local testing"
            )
        if timeout <= 0 or download_timeout <= 0:
            raise ValueError("timeouts must be greater than zero")
        if max_retries < 0 or retry_backoff < 0:
            raise ValueError("retry settings cannot be negative")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._sleep = sleeper
        self._clock = clock
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": f"openbot_sdk-python/{self._version()}",
            },
            timeout=self.timeout,
        )
        self._closed = False

    def _version(self) -> str:
        from openbot_sdk._version import __version__

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
        self._ensure_open()
        request_headers = {**headers} if headers else None
        response = self._send_with_retries(
            method,
            path,
            json=json,
            params=params,
            headers=request_headers,
            timeout=self.timeout,
        )
        self._raise_for_error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise APIResponseError("API returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise APIResponseError("API returned JSON with an unexpected top-level type")
        return cast(dict[str, Any], payload)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Call any OpenBot platform JSON API endpoint with this client's API key."""
        return self._request(
            method,
            path,
            json=json,
            params=params,
            headers=headers,
        )

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Make an authenticated request and return the raw response body."""
        self._ensure_open()
        request_timeout = self.download_timeout if timeout is None else timeout
        if request_timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        response = self._send_with_retries(method, path, timeout=request_timeout)
        self._raise_for_error(response)
        return response.content

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Call an OpenBot platform endpoint and return its authenticated byte response."""
        return self._request_bytes(method, path, timeout=timeout)

    def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
    ) -> httpx.Response:
        normalized_method = method.upper()
        idempotent_method = normalized_method in IDEMPOTENT_METHODS
        keyed_mutation = not idempotent_method and bool(
            headers and headers.get("Idempotency-Key")
        )
        can_retry = idempotent_method or keyed_mutation
        attempts = self.max_retries + 1 if can_retry else 1

        for attempt in range(attempts):
            try:
                response = self._http.request(
                    normalized_method,
                    path,
                    json=json,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
            except httpx.RequestError as exc:
                if attempt + 1 >= attempts:
                    raise NetworkError(f"API request failed: {exc}") from exc
                self._sleep_before_retry(attempt, None)
                continue

            retryable = (
                self._keyed_mutation_should_retry(response)
                if keyed_mutation
                else response.status_code in RETRYABLE_STATUS_CODES
            )
            if not retryable or attempt + 1 >= attempts:
                return response
            self._sleep_before_retry(attempt, response.headers.get("Retry-After"))

        raise NetworkError("API request failed after retries")

    def _keyed_mutation_should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in KEYED_MUTATION_RETRYABLE_STATUS_CODES:
            return True
        return response.status_code == 409 and self._error_code(response) in IN_PROGRESS_ERROR_CODES

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
            return code if isinstance(code, str) else None
        return None

    def _sleep_before_retry(self, attempt: int, retry_after: str | None) -> None:
        delay = self.retry_backoff * (2**attempt)
        if retry_after is not None:
            try:
                delay = min(float(retry_after), 60.0)
            except ValueError:
                pass
        if delay > 0:
            self._sleep(delay)

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        message = f"API request failed ({response.status_code})"
        code: str | None = None
        retryable: bool | None = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error = payload["error"]
            if isinstance(error.get("message"), str):
                message = error["message"]
            if isinstance(error.get("code"), str):
                code = error["code"]
            if isinstance(error.get("retryable"), bool):
                retryable = error["retryable"]
        elif response.text:
            message = f"{message}: {response.text}"
        raise APIError(
            message,
            status_code=response.status_code,
            code=code,
            retryable=retryable,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClientClosedError("Client is closed")

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if not self._closed:
            self._http.close()
            self._closed = True

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
