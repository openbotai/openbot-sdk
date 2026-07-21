# Changelog

## 0.1.0

### Added
- Initial alpha release.
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
