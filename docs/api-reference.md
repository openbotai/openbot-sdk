# API reference

All names below are importable from `openbot_sdk` unless noted otherwise.

This library is a thin client. Methods below call the Hosted OpenBot API; they
do not implement processing, review state, authorization, or retention locally.

`0.0.2` is implemented in source but not published. Data `0.0.2` methods remain
unavailable on production until the Hosted release gate passes.

## `Client`

```python
Client(
    api_key: str | None = None,
    base_url: str = "https://api.openbot.ai/v1",
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
)
```

`api_key` falls back to `OPENBOT_API_KEY`. `client.bench` exposes Bench methods
and `client.data` exposes Data methods. The client is a context manager and also
provides `close()`.

Idempotent HTTP methods and mutations with an `Idempotency-Key` retry transport
errors plus `429`, `502`, `503`, and `504`. Presigned uploads never forward the
OpenBot authorization header.

## Bench API

### `client.bench.rollout(...) -> Run`

Required keyword arguments are `policy`, `embodiment`, and `task`. Optional
arguments are `rollouts=200`, `seeds=10`, `sim`, `real_hw=False`,
`edge_target`, `webhook`, `idempotency_key`, and `metadata`.

`Run.refresh()` fetches current state. `Run.wait(poll_interval=5,
timeout=3600)` returns `RunResult` or raises `RunError`/`TimeoutError`.
`client.bench.get(run_id)` fetches an existing run.

## Data registration and jobs

### `client.data.register_dataset(...) -> Dataset`

Required: `name`, `format`, and at least one source supplied through `source` or
`upload_id`. Optional metadata includes `embodiment`, `description`,
`size_bytes`, `episode_count`, `version_tag`, `metadata`, and
`idempotency_key`.

### `client.data.subtask_job(...) -> DataJob`

Required: `dataset_id`, `video_key`, `taxonomy`, and exactly one of `video_url`
or `upload_id`. Optional controls are `task_hint`, `sample_fps`, `max_frames`,
`contact_sheet_columns`, `prompt_version`, `idempotency_key`, and `metadata`.

### Job lookup and listing

```python
client.data.get_job(job_id: str) -> DataJob
client.data.list_jobs(
    status: str | None = None,
    dataset_id: str | None = None,
    job_type: str | None = None,
    page_size: int = 20,
) -> Iterator[DataJob]
```

`DataJob` properties: `id`, `status`, `stage`, `stage_updated_at`,
`attempt_count`, `cancel_requested`, `warnings`, `error`, and `result_url`.

```python
job.refresh() -> DataJob
job.cancel() -> DataJob
job.wait(poll_interval=5.0, timeout=3600.0) -> DataJobResult
```

`DataJobResult` exposes `review_output`, `review_output_id`, `annotations`,
`timeline`, and `artifact_url`. `DataJob` and `DataJobResult` also support
`resource[key]` and `resource.get(key)` for forward-compatible response fields.

## Upload API

```python
client.data.create_upload(
    path: str | Path,
    dataset_id: str | None = None,
    content_type: str | None = None,
    idempotency_key: str | None = None,
) -> DataUpload

client.data.get_upload(upload_id: str) -> DataUpload
client.data.resume_upload(upload_id: str, path: str | Path) -> DataUpload
client.data.delete_upload(upload_id: str) -> None
client.data.list_uploads(
    status: str | None = None,
    page_size: int = 20,
) -> Iterator[DataUpload]
```

`create_upload` derives the filename, byte size, MIME type, and SHA-256 digest.
The server response selects single or multipart mode.

`DataUpload` properties: `id`, `status`, `mode`, `retention_until`, and `media`.

```python
upload.upload(part_concurrency: int = 4) -> DataUpload
upload.wait_until_ready(
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> DataUpload
upload.refresh() -> DataUpload
upload.delete() -> None
```

Multipart resume reuses server-reported completed part numbers and ETags, signs
only missing parts, and retries failed parts. `DataUpload` supports
`upload[key]` and `upload.get(key)` for unknown response fields.

## Dataset listing

```python
client.data.list_datasets(
    format: str | None = None,
    embodiment: str | None = None,
    page_size: int = 20,
) -> Iterator[Dataset]
```

Pagination is lazy. Tokens are opaque and filters remain present on every page.

## Review and export

```python
client.data.review(
    review_output_id: str,
    status: Literal[
        "needs_review",
        "approved",
        "changes_requested",
        "rejected",
    ],
    notes: str | None = None,
    annotations: dict | None = None,
    decisions: list[dict] | None = None,
    expected_revision: str | None = None,
) -> ReviewOutput

client.data.export(
    review_output_id: str,
    format: Literal["jsonl", "lerobot_sidecar", "rlds_metadata"],
) -> DataExport

client.data.download_export(export_id: str, timeout: float | None = None) -> bytes
client.data.download_export_to(
    export_id: str,
    destination: str | Path | BinaryIO,
    timeout: float | None = None,
) -> Path | None
client.data.delete_export(export_id: str) -> None
```

`DataExport` exposes `id`, `status`, `format`, and `retention_until`, plus raw
mapping access for forward-compatible response fields.

Only explicitly reviewed output should be approved and exported.
`expected_revision` is sent as `If-Match`; stale edits raise `APIError` with
HTTP `412` instead of overwriting a newer review revision.

## Artifact API

```python
client.data.list_artifacts(
    job_id: str,
    page_size: int = 20,
) -> Iterator[DataArtifact]
client.data.artifact(artifact_id: str, **metadata) -> DataArtifact
client.data.download_artifact(
    artifact_id: str,
    destination: str | Path | BinaryIO,
    byte_range: str | None = None,
    timeout: float | None = None,
) -> Path | None
client.data.head_artifact(artifact_id: str) -> dict[str, str]
client.data.delete_job_artifacts(job_id: str) -> None
```

`DataArtifact` properties: `id`, `kind`, `content_type`, `size_bytes`, and
`retention_until`.

```python
artifact.head() -> dict[str, str]
artifact.download_to(
    destination: str | Path | BinaryIO,
    byte_range: str | None = None,
    timeout: float | None = None,
) -> Path | None
```

`DataArtifact` supports `artifact[key]` and `artifact.get(key)` for unknown
response fields. Deleted resources are surfaced as `APIError` with HTTP status
`410` and the server's stable error code.

## Webhooks

```python
verify_signature(
    payload: bytes,
    signature: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> None
```

Always pass the raw request bytes. Invalid, malformed, or expired signatures
raise `WebhookVerificationError`.

`construct_signature(payload, secret, timestamp=None)` exists for tests.

## Exceptions

All SDK exceptions inherit `OpenBotError`.

| Exception | Meaning |
|---|---|
| `AuthenticationError` | API key is absent |
| `ClientClosedError` | A closed client was used |
| `APIError` | Non-success response; exposes `status_code`, `code`, `retryable` |
| `APIResponseError` | Success response violates the expected contract |
| `NetworkError` | Transport failure after allowed retries |
| `RunError` | Bench run reached a failed/cancelled state |
| `DataJobError` | Data job reached a failed/cancelled state |
| `DataUploadError` | Upload transfer or verification failed |
| `WebhookVerificationError` | Webhook signature is invalid |

Timeouts from polling helpers raise Python's built-in `TimeoutError`.
