# openbot-sdk

`openbot-sdk` is the thin Python client for the
[OpenBot.ai platform API](https://openbot.ai/api/docs).

It handles API-key authentication, HTTP requests, timeouts, bounded retries,
and typed errors. It does not process robot data and is not tied to a Hosted
Data product.

## Install

`openbot-sdk` is not published to PyPI yet (package publishing is a later
Platform milestone). Install it from source:

```bash
pip install "git+https://github.com/openbotai/openbot-sdk.git"
```

Requires Python 3.9+.

## Authentication

```bash
export OPENBOT_API_KEY="ob_..."
```

```python
from openbot_sdk import Client

client = Client()  # reads OPENBOT_API_KEY
status = client.request("GET", "/status")
print(status)
```

You can also pass the key explicitly:

```python
client = Client(api_key="ob_...")
```

## Call platform APIs

Use `request` for JSON APIs and `request_bytes` for byte responses:

```python
payload = client.request(
    "POST",
    "/some-resource",
    json={"name": "example"},
    headers={"Idempotency-Key": "request-123"},
)

content = client.request_bytes("GET", "/some-artifact")
```

Only call routes published in the current OpenBot OpenAPI document. As the
platform adds real APIs, the SDK may add small convenience wrappers for those
same contracts.

The SDK intentionally has no Bench, Synth, or Hosted Data resource wrapper.
Convenience wrappers correspond to operations in the checked OpenAPI contract;
`request(...)` remains the forward-compatible escape hatch.

## Errors, retries, and security

```python
from openbot_sdk import APIError, NetworkError

try:
    payload = client.request("GET", "/status")
except APIError as exc:
    print(exc.status_code)
except NetworkError as exc:
    print(exc)
```

The client retries idempotent methods on transport errors, `429`, and
transient `5xx` responses. Mutations carrying an `Idempotency-Key` are retried
with the same key only where that is safe: transport errors, `429`, `503`
(for example `settlement_pending`), `504`, and `409 invocation_in_progress`.
A `502` is returned immediately, because the gateway burns the key when the
upstream fails; retry that call with a new key. For `POST /v1/invoke/:slug`,
create the client with `timeout` (seconds) larger than the API's
`x-openbot-timeout-ms`, so a slow upstream is not mistaken for a network failure.
Plain HTTP base URLs are rejected by default; enable them only for explicit
local testing.

## Development

```bash
pip install -e ".[dev]"
python scripts/check_version.py
python scripts/check_openapi_contract.py /path/to/openapi.json
pytest -v
ruff check src tests
mypy src
python -m build
```

`VERSION` is the package version source of truth. Release tags use `v<version>`.

## Package boundaries

- `openbot-sdk`: OpenBot platform API client.
- `openbot-data`: local robot/ego data processing library.
- OpenBot platform: server-side API implementation and infrastructure.

## License

MIT
