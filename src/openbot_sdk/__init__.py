"""
openbot-sdk — Python SDK for OpenBot.ai.

openbot-sdk is a thin authenticated client for the OpenBot platform API.

Example:
    >>> import openbot_sdk
    >>> client = openbot_sdk.Client()
    >>> status = client.request("GET", "/status")
    >>> print(status)
"""

from openbot_sdk._client import Client
from openbot_sdk._errors import (
    APIError,
    APIResponseError,
    AuthenticationError,
    ClientClosedError,
    NetworkError,
    OpenBotError,
)
from openbot_sdk._version import __version__

__all__ = [
    "Client",
    "OpenBotError",
    "AuthenticationError",
    "ClientClosedError",
    "APIError",
    "APIResponseError",
    "NetworkError",
    "__version__",
]
