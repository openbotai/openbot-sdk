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
