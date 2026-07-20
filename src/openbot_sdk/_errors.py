"""OpenBot.ai SDK errors."""

from __future__ import annotations


class OpenBotError(Exception):
    """Base error for all OpenBot.ai SDK errors."""


class AuthenticationError(OpenBotError):
    """Raised when the API key is missing or invalid."""


class APIError(OpenBotError):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RunError(OpenBotError):
    """Raised when a rollout run fails or is cancelled."""


class DataJobError(OpenBotError):
    """Raised when a Data job fails or is cancelled."""


class WebhookVerificationError(OpenBotError):
    """Raised when a webhook signature cannot be verified."""
