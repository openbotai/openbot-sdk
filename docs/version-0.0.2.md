# OpenBot SDK 0.0.2 — Thin Hosted Data API Client

> Status: Implemented in SDK source; Hosted API production gate pending
> Previous package: `0.0.1`
> Current source version: `0.0.2`
> Required server contract: OpenBot Data API `0.0.2`

This document is the release contract for the Python SDK. `openbot-sdk` is a
thin client for the OpenBot platform: it sends authenticated requests, transfers
bytes to platform-issued upload targets, polls resources, and streams downloads.
It does not implement Hosted Data business logic locally.

## Verified release state — 2026-08-06

| Surface | Verified state |
|---|---|
| SDK source | `VERSION=0.0.2`; Python 3.9–3.12 each pass 65 tests with 2 opt-in live tests skipped |
| Static/package checks | Ruff, Mypy, version consistency, wheel, sdist, Twine, wheel import, and `py.typed` pass |
| PyPI | `openbot-sdk` is not published; the official project JSON endpoint returns `404` |
| Hosted Data | Production manifest reports Data `0.0.1`, `openapi_sha256=null`, and `production_smoke.passed=false` |
| Release decision | Source implementation complete; do not tag or publish `0.0.2` yet |

Package source state, PyPI publication, and Hosted Data product state are three
separate facts. None may be inferred from another.

## Goal

Let a Python developer call the platform without manually constructing HTTP
requests or handling presigned multipart transfer details:

```python
upload = client.data.create_upload(
    path="episode-0001.mp4",
    dataset_id="data_123",
    idempotency_key="episode-0001",
)
upload.upload()
upload.wait_until_ready()

job = client.data.subtask_job(
    dataset_id="data_123",
    upload_id=upload.id,
    video_key="observation.images.top",
    taxonomy=["reach", "grasp", "place"],
)
result = job.wait()
```

The server owns authorization, upload limits and mode selection, verification,
job state transitions, processing, review, retention, and deletion policy.

## Responsibility boundary

| SDK responsibility | Platform responsibility |
|---|---|
| Attach API authentication to OpenBot API requests | Authenticate, authorize, and enforce organization scope |
| Serialize documented request fields and expose response resources | Validate every field and execute business rules |
| Calculate local file size and SHA-256 for the request | Independently verify uploaded bytes and media metadata |
| Transfer bytes to server-issued single/multipart targets | Select upload mode, part size/count, sign URLs, and own R2 credentials |
| Retry safe requests/parts and resume server-reported completed parts | Make mutations idempotent and reconcile incomplete uploads |
| Poll the status and stage returned by the API | Run Queue workers and decide valid state transitions |
| Stream authenticated content to a caller-owned destination | Enforce artifact/export access, retention, and tombstones |

The SDK never runs FFmpeg, parses robot datasets, creates annotations, makes
review decisions, enforces retention, or embeds R2 credentials.

## Current `0.0.1` baseline

The existing client provides:

- API-key authentication and HTTPS enforcement;
- bounded retries for idempotent requests;
- Bench rollout creation, polling, and result wrappers;
- Data dataset registration and subtask job creation/polling;
- review, approved export creation, and authenticated export download;
- webhook signature verification;
- typed SDK exceptions for authentication, API, network, run, and Data failures.

These capabilities remain compatible in `0.0.2`.

## Required `0.0.2` client functionality

### 1. Direct upload transport

`create_upload(...)` derives the local filename, byte size, MIME type, and
SHA-256, then calls the platform upload endpoint. `DataUpload.upload()` follows
the transfer instructions returned by that endpoint:

- send one `PUT` for single uploads;
- request only missing part URLs for multipart uploads;
- stream bounded file slices instead of loading the file into memory;
- collect ETags and send them to the platform completion endpoint;
- retry failed requests without retransmitting completed parts;
- resume an existing upload only when the local file matches server metadata;
- poll until the platform reports `ready` or a terminal rejection.

The client must never forward the OpenBot `Authorization` header to a presigned
target. Presigned targets must use HTTPS, must not redirect, and may only receive
the transfer headers supplied by the platform. The SDK does not choose upload
limits, part sizes, verification rules, or retention policy.

### 2. Platform resource calls

Expose thin, typed helpers for the documented endpoints:

- get/list/delete uploads;
- register and list datasets;
- create/get/list/cancel Data jobs;
- submit review decisions and create/download/delete approved exports;
- list/head/download/delete job artifacts.

`subtask_job(...)` accepts exactly one platform source reference: `upload_id` or
`video_url`. Dynamic resource IDs are validated before URL construction. The SDK
does not reproduce server authorization or state-machine rules.

### 3. Lazy listing and honest status

Upload, dataset, job, and artifact listings are lazy iterators. They:

- preserve the server's opaque string `next_page_token` exactly;
- reapply the same filters on every request;
- suppress duplicate resource IDs across pages;
- reject malformed resources or repeated tokens;
- do not fabricate an exact total count.

`DataJob` exposes the status, stage, timestamps, attempt count, warnings, and
error details returned by the platform. It does not calculate percentages or
predict completion time.

### 4. Authenticated streaming downloads

Artifact and export content remains behind the OpenBot API. The SDK supports:

- authenticated `HEAD` for artifact metadata;
- single-range artifact downloads;
- file-like destinations;
- path destinations written through a temporary `.part` file and atomically
  replaced only after success;
- explicit raw-upload, artifact, and export deletion calls.

HTTP `410` remains a structured `APIError` from the platform. Resource wrappers
expose documented fields such as `retention_until` and retain unknown response
fields through mapping access for forward compatibility.

### 5. Package contract

- all public methods have Python type hints;
- the wheel contains `py.typed`;
- `VERSION` is the single package version source;
- Python 3.9–3.12 are supported;
- `APIError` exposes the platform's safe message, stable code, HTTP status, and
  retryability without including raw response bodies in exception messages.

## Source acceptance criteria

The SDK source is complete only when:

- mocked tests cover single upload, multipart boundaries, failed-part retry,
  resume, local identity mismatch, timeout, and completion retry;
- tests prove OpenBot authorization is never forwarded to a presigned target;
- pagination preserves filters/tokens and never yields a duplicate ID;
- queued, running, and already-cancelled responses are handled consistently;
- artifact/export downloads stream and interrupted path downloads clean up;
- every public method has type hints and the example workflow runs under mocks;
- Python 3.9–3.12 tests, Ruff, Mypy, package build, Twine, and wheel `py.typed`
  checks pass.

Source acceptance proves the SDK client, not production availability.

## Hosted release gate

The package must not be released as `0.0.2` until the Hosted Data API advertises
Data `0.0.2`, publishes a valid OpenAPI hash, and records a passing production
smoke. The external smoke must cover private upload, job processing, human
review boundary, authenticated download, and deletion.

`scripts/check_hosted_release.py` enforces this gate in the release workflow.
The live tests are opt-in and must never be reported as passed when skipped.

## Acceptance coverage

- `tests/test_data_v002.py`: transport, retry, pagination, cancellation, secure
  presigned requests, and streaming downloads;
- `tests/test_data_v002_acceptance.py`: resume, malformed contracts, lifecycle
  helpers, `410` handling, type hints, docs, and runnable examples;
- `tests/test_data_live.py`: opt-in mutating Hosted API smoke;
- `examples/data_v002_workflow.py`: public upload/job and approved-export usage.

## Explicit non-goals

- implementing upload authorization, R2 signing, Queue, processing, or retention;
- running FFmpeg or validating video contents in the SDK;
- parsing LeRobot/HDF5 datasets or duplicating `openbot-data`;
- generating annotations, approving review output, or fabricating job progress;
- asynchronous Python client support in `0.0.2`;
- visual review UI, payment, credits, or entitlement logic;
- claiming production availability before the Hosted release gate passes.
