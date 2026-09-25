# Changelog

## 0.3.0

### Removed

- Ego Semantic Annotation create/get/cancel/result wrappers. The operation is
  discontinued, and the OpenAPI compatibility check no longer requires its routes.

### Fixed

- Mutations carrying an `Idempotency-Key` are no longer retried after `502`:
  the gateway burns the key when the upstream fails, so a same-key retry masked
  the real error as `409`. `409 invocation_in_progress` is now retried with the
  same key until the stored result is replayed.
- `scripts/check_openapi_contract.py` sends an SDK User-Agent; the production
  edge rejected the default Python-urllib agent with `403`, which would have
  failed the release workflow.

## 0.2.0

### Added

- Ego Semantic Annotation create/get/cancel/result wrappers.
- Mandatory stable idempotency key, source SHA-256, and bounded duration checks.
- OpenAPI compatibility checks for the complete asynchronous operation surface.

### Safety

- The wrapper does not perform inference locally or fabricate fallback results.
- Feature-gate, concurrency, provider, and billing failures remain structured API errors.

## 0.1.0

### Changed

- Removed the unreleased Bench wrapper and run polling types.
- Kept the SDK as a neutral authenticated client for operations published by
  the production OpenAPI contract.
- Removed customer webhook signing helpers until a deployed asynchronous API
  publishes a callback contract.

## 0.0.2

### Added

- Public `Client.request(...)` for authenticated JSON platform API calls.
- Public `Client.request_bytes(...)` for authenticated byte responses.
- Configurable request/download timeouts and bounded retry behavior.
- Typed network and response errors.
- Single-source version and release-tag validation.

### Clarified

- `openbot-sdk` is only a thin client for the OpenBot platform API.
- Robot/ego data processing belongs to `openbot-data`.
- No Hosted Data resources, jobs, uploads, review, or export helpers are part of
  this package.

## 0.0.1

### Added

- Initial API-key client.
- Bench contract wrapper and polling result helper.
- Webhook signature verification.
