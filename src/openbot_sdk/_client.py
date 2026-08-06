"""OpenBot.ai Python client."""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, cast
from urllib.parse import urlparse

import httpx

from openbot_sdk._bench import BenchResource
from openbot_sdk._data import DataResource
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
FORBIDDEN_EXTERNAL_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "host"}
)
ALLOWED_EXTERNAL_HEADERS = frozenset(
    {"content-type", "content-md5", "content-length", "if-none-match"}
)


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
        retry_jitter: float = 0.1,
        allow_insecure_http: bool = False,
        allow_insecure_uploads: bool = False,
        transport: httpx.BaseTransport | None = None,
        external_transport: httpx.BaseTransport | None = None,
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
        if max_retries < 0 or retry_backoff < 0 or retry_jitter < 0:
            raise ValueError("retry settings cannot be negative")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.retry_jitter = retry_jitter
        self.allow_insecure_uploads = allow_insecure_uploads
        self._sleep = sleeper
        self._clock = clock
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": f"openbot_sdk-python/{self._version()}",
            },
            timeout=self.timeout,
            transport=transport,
        )
        self._external_http = httpx.Client(
            headers={},
            follow_redirects=False,
            timeout=self.download_timeout,
            transport=external_transport,
        )
        self._closed = False
        self.bench = BenchResource(self)
        self.data = DataResource(self)

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

    def _request_empty(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._ensure_open()
        response = self._send_with_retries(
            method,
            path,
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_error(response)

    def _request_headers(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        self._ensure_open()
        response = self._send_with_retries(
            method,
            path,
            headers=headers,
            timeout=self.download_timeout,
        )
        self._raise_for_error(response)
        return dict(response.headers)

    def _stream_to(
        self,
        path: str,
        destination: str | Path | BinaryIO,
        *,
        byte_range: str | None = None,
        timeout: float | None = None,
    ) -> Path | None:
        self._ensure_open()
        request_timeout = self.download_timeout if timeout is None else timeout
        if request_timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        headers = {"Range": byte_range} if byte_range is not None else None
        if hasattr(destination, "write"):
            output = cast(BinaryIO, destination)
            stream_response = self._open_stream_with_retries(
                path,
                headers=headers,
                timeout=request_timeout,
            )
            try:
                self._validate_range_response(stream_response, byte_range)
                for chunk in stream_response.iter_bytes():
                    output.write(chunk)
            except httpx.RequestError as exc:
                raise NetworkError(f"Artifact download failed: {exc}") from exc
            finally:
                stream_response.close()
            return None

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            temporary.unlink(missing_ok=True)
            response: httpx.Response | None = None
            try:
                response = self._open_stream_once(
                    path,
                    headers=headers,
                    timeout=request_timeout,
                )
                if response.status_code in RETRYABLE_STATUS_CODES:
                    response.read()
                    raise NetworkError(
                        f"Artifact download failed with status {response.status_code}"
                    )
                self._raise_for_error(response)
                self._validate_range_response(response, byte_range)
                with temporary.open("wb") as output_file:
                    for chunk in response.iter_bytes():
                        output_file.write(chunk)
                temporary.replace(target)
                return target
            except (httpx.RequestError, NetworkError) as exc:
                last_error = (
                    exc
                    if isinstance(exc, NetworkError)
                    else NetworkError(f"Artifact download failed: {exc}")
                )
                temporary.unlink(missing_ok=True)
                if attempt + 1 >= attempts:
                    raise last_error from exc
                retry_after = (
                    response.headers.get("Retry-After") if response is not None else None
                )
                self._sleep_before_retry(attempt, retry_after)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            finally:
                if response is not None:
                    response.close()
        raise NetworkError(f"Artifact download failed after retries: {last_error}")

    def _open_stream_once(
        self,
        path: str,
        *,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> httpx.Response:
        request = self._http.build_request("GET", path, headers=headers, timeout=timeout)
        return self._http.send(request, stream=True)

    def _open_stream_with_retries(
        self,
        path: str,
        *,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = self._open_stream_once(path, headers=headers, timeout=timeout)
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise NetworkError(f"Artifact download failed: {exc}") from exc
                self._sleep_before_retry(attempt, None)
                continue
            if (
                response.status_code not in RETRYABLE_STATUS_CODES
                or attempt >= self.max_retries
            ):
                if response.status_code >= 400:
                    response.read()
                try:
                    self._raise_for_error(response)
                except Exception:
                    response.close()
                    raise
                return response
            response.close()
            self._sleep_before_retry(attempt, response.headers.get("Retry-After"))
        raise NetworkError("Artifact download failed after retries")

    @staticmethod
    def _validate_range_response(
        response: httpx.Response,
        byte_range: str | None,
    ) -> None:
        if byte_range is not None and response.status_code != 206:
            raise APIResponseError(
                "API did not honor the requested artifact byte range"
            )

    def _external_request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: Any = None,
    ) -> httpx.Response:
        """Send a presigned request without forwarding OpenBot authorization."""
        self._ensure_open()
        parsed_url = urlparse(url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.fragment
        ):
            raise APIResponseError("Presigned upload URL is not a safe absolute URL")
        if parsed_url.scheme != "https" and not self.allow_insecure_uploads:
            raise APIResponseError("Presigned upload URL must use HTTPS")
        normalized_headers: dict[str, str] = {}
        for key, value in (headers or {}).items():
            normalized_key = key.lower()
            if normalized_key in FORBIDDEN_EXTERNAL_HEADERS:
                raise APIResponseError(
                    f"Presigned upload header {key!r} is not permitted"
                )
            if (
                normalized_key not in ALLOWED_EXTERNAL_HEADERS
                and not normalized_key.startswith("x-amz-")
            ):
                raise APIResponseError(
                    f"Presigned upload header {key!r} is not supported"
                )
            normalized_headers[str(key)] = str(value)
        try:
            return self._external_http.request(
                method,
                url,
                headers=normalized_headers,
                content=content,
            )
        except httpx.RequestError as exc:
            raise NetworkError(f"Presigned upload request failed: {exc}") from exc

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code: str | None = None
        message: str | None = None
        retryable: bool | None = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error", payload)
            if isinstance(error, dict):
                raw_code = error.get("code")
                raw_message = error.get("message")
                raw_retryable = error.get("retryable")
                code = raw_code if isinstance(raw_code, str) else None
                message = raw_message if isinstance(raw_message, str) else None
                retryable = raw_retryable if isinstance(raw_retryable, bool) else None
        safe_message = message or f"API request failed with status {response.status_code}"
        raise APIError(
            safe_message,
            status_code=response.status_code,
            code=code,
            retryable=retryable,
        )

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
        if delay > 0 and self.retry_jitter > 0:
            delay += random.random() * self.retry_jitter
        if delay > 0:
            self._sleep(delay)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._closed:
            return
        self._http.close()
        self._external_http.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClientClosedError("OpenBot client is closed")

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
