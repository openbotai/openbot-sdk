# Changelog

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
