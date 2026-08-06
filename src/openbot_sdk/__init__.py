"""
openbot-sdk — Python SDK for OpenBot.ai.

openbot-sdk is a thin authenticated client for the OpenBot platform API.

Example:
    >>> import openbot_sdk
    >>> client = openbot_sdk.Client()
    >>> status = client.request("GET", "/status")
    >>> print(status)
"""

from openbot_sdk._bench import BenchResource
from openbot_sdk._client import Client
from openbot_sdk._errors import (
    APIError,
    APIResponseError,
    AuthenticationError,
    ClientClosedError,
    NetworkError,
    OpenBotError,
    RunError,
    WebhookVerificationError,
)
from openbot_sdk._run import Run, RunResult
from openbot_sdk._version import __version__
from openbot_sdk._webhooks import construct_signature, verify_signature

__all__ = [
    "Client",
    "BenchResource",
    "Run",
    "RunResult",
    "OpenBotError",
    "AuthenticationError",
    "ClientClosedError",
    "APIError",
    "APIResponseError",
    "NetworkError",
    "RunError",
    "WebhookVerificationError",
    "verify_signature",
    "construct_signature",
    "__version__",
]
