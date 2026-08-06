# Changelog

## Unreleased

## 0.0.2 (source candidate; not published)

### Added
- Single-source package versioning with CI and release-tag validation.
- Direct single/multipart private uploads with SHA-256, failed-part retry, and resume support.
- Upload/dataset/job pagination, private-upload job creation, honest stage metadata,
  and cancellation helpers.
- Authenticated artifact listing, HEAD/range download, streaming-to-disk, and deletion.
- Structured API error codes and typed upload/artifact resources.
- Strict validation for platform-issued upload methods, resource IDs, and opaque
  pagination tokens.
- Runnable ingest and existing-review export demos, developer documentation, and
  complete public API reference.
- Mocked acceptance coverage, opt-in production smoke harness, and a local Python
  3.9–3.12 test-matrix command.

### Changed
- Large artifact and export downloads can stream to a destination instead of loading
  the entire response into memory.
- Upload and artifact resources retain forward-compatible response fields through
  `resource[key]` and `resource.get(...)`.

### Fixed
- Streaming `4xx` responses are read before error parsing so deleted artifacts
  surface as structured `APIError` values instead of `httpx.ResponseNotRead`.
- Hosted release checks send an explicit JSON User-Agent so Cloudflare does not
  reject the release gate before its semantic checks run.

## 0.0.1

### Added
- Initial preview release.
- `Client` for authenticating with the OpenBot.ai API.
- `client.bench.rollout(...)` for queuing policy evaluation runs.
- `Run.wait(...)` for polling rollout completion.
- `RunResult` wrapper for task success, intervention rate, sim-to-real gap, and per-subtask metrics.
- Webhook signature verification via `verify_signature`.
- Test helper `construct_signature`.
- Data API helpers for dataset registration, subtask annotation jobs, human review,
  approved exports, and authenticated export downloads.
- Configurable request and download timeouts, bounded retries for idempotent requests,
  and typed network/response errors.

### Fixed
- Webhook verification now signs raw request bytes, including non-UTF-8 payloads.
- API credentials are no longer sent over plain HTTP unless explicitly enabled for
  local development.
