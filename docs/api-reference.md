# Client reference

## `Client`

```python
Client(
    api_key=None,
    base_url="https://api.openbot.ai/v1",
    timeout=60.0,
    download_timeout=300.0,
    max_retries=2,
    retry_backoff=0.25,
    allow_insecure_http=False,
)
```

`api_key` falls back to `OPENBOT_API_KEY`.

## `request`

```python
client.request(method, path, json=None, params=None, headers=None)
```

Returns a JSON object. Non-JSON or non-object responses raise
`APIResponseError`; HTTP failures raise `APIError`.

## `request_bytes`

```python
client.request_bytes(method, path, timeout=None)
```

Returns raw response bytes.

## Ego Semantic Annotation

```python
client.create_ego_semantic_annotation(
    source_url=...,
    source_sha256=...,
    duration_seconds=...,
    idempotency_key=...,
    context=None,
    labels=None,
)
client.get_ego_semantic_annotation(job_id)
client.cancel_ego_semantic_annotation(job_id)
client.get_ego_semantic_annotation_result(job_id)
```

The create call is safe to retry only because it always sends the caller's
`Idempotency-Key`. The current 0.2.0 operation is an internal canary and may
return `operation_unavailable` for workspaces outside the gate.

## Errors

- `AuthenticationError`
- `APIError`
- `APIResponseError`
- `NetworkError`

Endpoint-specific wrappers are checked against the matching OpenBot OpenAPI
operation before release.
