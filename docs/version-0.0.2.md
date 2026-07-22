# OpenBot SDK 0.0.2 — Self-service Data Ingest Client

> Status: Planned
> Current package: `0.0.1`
> Target package: `0.0.2`
> Required server contract: OpenBot Data API `0.0.2`

This document is the release contract for the Python SDK. It describes planned
work, not functionality available in the current package. The SDK must not claim
these capabilities are live until the corresponding hosted endpoints pass their
production release gates.

## Goal

`0.0.2` should let a developer complete one private, self-service workflow from
Python without manually constructing HTTP requests:

```text
local MP4
  -> direct single/multipart upload
  -> server verification
  -> dataset + subtask job
  -> poll honest stage or cancel
  -> download authenticated artifacts/export
  -> delete raw upload and derived artifacts
```

The SDK remains a client. R2 credentials, authorization decisions, job state,
retention enforcement, and processor behavior remain server responsibilities.

## Current `0.0.1` baseline

The current package already provides:

- API-key authentication and HTTPS enforcement;
- bounded retries for idempotent requests;
- Bench rollout creation, polling, and result wrappers;
- Data dataset registration and subtask job creation/polling;
- review, approved export creation, and authenticated export download;
- webhook signature verification;
- typed SDK exceptions for authentication, API, network, run, and Data failures.

These capabilities remain supported in `0.0.2`.

## Required `0.0.2` functionality

### 1. Upload resource and direct transfer

Add a typed `DataUpload` resource and the following workflow:

```python
upload = client.data.create_upload(
    path="episode-0001.mp4",
    dataset_id="data_123",
    idempotency_key="episode-0001",
)
upload.upload()
upload.wait_until_ready()
```

The SDK must:

- derive filename, size, content type, and SHA-256 from the local file;
- use single PUT at or below the server threshold and multipart above it;
- sign only the requested multipart part numbers and collect ETags;
- retry failed parts without retransmitting successful parts;
- support resuming an existing pending multipart upload;
- complete the upload and poll until `ready` or a terminal rejection;
- never attach the OpenBot API `Authorization` header to presigned R2 URLs;
- avoid logging presigned URLs, signatures, or local file contents.

The server independently validates every declared value; SDK checksum and media
metadata are convenience inputs, not trust boundaries.

### 2. Dataset, upload, and job listing

Add typed, lazy pagination helpers for:

- `list_uploads(...)`;
- `list_datasets(...)`;
- `list_jobs(...)`.

They must preserve opaque `next_page_token` values, apply filters consistently,
and never fabricate a total count. Iteration stops when the server returns no
next token.

### 3. Private-upload job creation and honest progress

Extend `subtask_job(...)` with `upload_id`, mutually exclusive with `video_url`.
Extend `DataJob` with:

- `stage`, `stage_updated_at`, and `attempt_count`;
- `cancel_requested`, structured warnings, and stable error details;
- `cancel()` with idempotent handling of already-cancelled jobs;
- terminal handling for `done`, `failed`, and `cancelled` without fake progress
  percentages.

```python
job = client.data.subtask_job(
    dataset_id="data_123",
    upload_id=upload.id,
    video_key="observation.images.top",
    taxonomy=["reach", "grasp", "place"],
)

for active_job in client.data.list_jobs(status="running"):
    print(active_job.id, active_job.stage)

job.cancel()
```

### 4. Authenticated artifact lifecycle

Add helpers to:

- list a job's evidence/result artifacts;
- stream an artifact to a file-like object or destination path;
- support authenticated HEAD and single-range download requests;
- delete job artifacts, exports, and raw uploads;
- expose `retention_until` and distinguish deleted (`410`) resources.

Large content must stream to disk rather than being loaded entirely into memory.
Resource identifiers come from the API; callers cannot supply an arbitrary R2
object key or URL path.

### 5. Stable resources and errors

Add typed wrappers for upload, paginated result, artifact, progress, and API error
payloads while retaining access to forward-compatible unknown fields. `APIError`
must expose the server's stable error code, safe message, HTTP status, and
retryability without including secrets or raw provider errors.

## Release acceptance criteria

The version is complete only when:

- mocked tests cover single upload, multipart boundaries, failed-part retry,
  resume, checksum mismatch, timeout, and complete retry;
- tests prove OpenBot authorization is never forwarded to a presigned R2 URL;
- pagination has no duplicate SDK yields and preserves filters/tokens;
- queued and running cancellation behavior matches the server contract;
- artifact downloads stream and support interrupted-download cleanup;
- all new public methods include type hints and runnable examples;
- Python 3.9–3.12 tests, Ruff, Mypy, package build, and Twine checks pass;
- a production smoke completes upload -> job -> review -> authenticated download
  -> delete against the released Data API `0.0.2`.

The SDK package must not be released as `0.0.2` before the matching hosted API is
deployed and the production smoke passes.

## Explicit non-goals

- Implementing server upload, authorization, retention, or Queue logic;
- asynchronous Python client support;
- visual timeline review UI;
- LeRobot/Hugging Face batch ingestion or local dataset parsing;
- webhook delivery, automatic callbacks, or a real Bench runner;
- payment, credit purchase, or paid entitlement helpers;
- claiming a production SLA during the `0.0.x` free beta.
