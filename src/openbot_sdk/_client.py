"""OpenBot.ai Python client."""

from __future__ import annotations

import os
import re
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
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$")
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


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

    def create_ego_semantic_annotation(
        self,
        *,
        source_url: str,
        source_sha256: str,
        duration_seconds: int,
        idempotency_key: str,
        context: str | None = None,
        labels: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create a feature-gated asynchronous Ego Semantic Annotation job."""
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
            raise ValueError("idempotency_key must contain 8-200 safe characters")
        if not SHA256_PATTERN.fullmatch(source_sha256):
            raise ValueError("source_sha256 must be 64 hexadecimal characters")
        if not isinstance(duration_seconds, int) or not 1 <= duration_seconds <= 7200:
            raise ValueError("duration_seconds must be an integer between 1 and 7200")
        parsed_source = urlparse(source_url)
        if parsed_source.scheme != "https" or not parsed_source.netloc:
            raise ValueError("source_url must be an absolute HTTPS URL")
        payload: dict[str, Any] = {
            "source": {
                "type": "video_url",
                "url": source_url,
                "sha256": source_sha256.lower(),
                "duration_seconds": duration_seconds,
            }
        }
        if context is not None:
            payload["context"] = context
        if labels is not None:
            payload["labels"] = labels
        return self._request(
            "POST",
            "/ego/semantic-annotations",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )

    def get_ego_semantic_annotation(self, job_id: str) -> dict[str, Any]:
        """Read a tenant-scoped Ego Semantic Annotation job."""
        return self._request("GET", f"/ego/semantic-annotations/{job_id}")

    def cancel_ego_semantic_annotation(self, job_id: str) -> dict[str, Any]:
        """Idempotently request cancellation of an annotation job."""
        return self._request("POST", f"/ego/semantic-annotations/{job_id}/cancel")

    def get_ego_semantic_annotation_result(self, job_id: str) -> dict[str, Any]:
        """Read the validated JSON result for a completed annotation job."""
        return self._request("GET", f"/ego/semantic-annotations/{job_id}/result")

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
        can_retry = normalized_method in IDEMPOTENT_METHODS or bool(
            headers and headers.get("Idempotency-Key")
        )
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

            if response.status_code not in RETRYABLE_STATUS_CODES or attempt + 1 >= attempts:
                return response
            self._sleep_before_retry(attempt, response.headers.get("Retry-After"))

        raise NetworkError("API request failed after retries")

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
