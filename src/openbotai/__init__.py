"""
OpenBotai — Python SDK for OpenBot.ai.

OpenBotai helps embodied AI and robot learning teams evaluate policies,
curate teleoperation data, and generate synthetic training data through
a simple Python interface.

Example:
    >>> import openbotai
    >>> client = openbotai.Client()
    >>> run = client.bench.rollout(
    ...     policy="openvla-7b",
    ...     embodiment="franka_panda",
    ...     task="pick_mug → pour → handover",
    ... )
    >>> result = run.wait()
    >>> print(result.task_success)
"""

from openbotai._bench import BenchResource
from openbotai._client import Client
from openbotai._errors import (
    APIError,
    AuthenticationError,
    OpenBotError,
    RunError,
    WebhookVerificationError,
)
from openbotai._run import Run, RunResult
from openbotai._version import __version__
from openbotai._webhooks import construct_signature, verify_signature

__all__ = [
    "Client",
    "BenchResource",
    "Run",
    "RunResult",
    "OpenBotError",
    "AuthenticationError",
    "APIError",
    "RunError",
    "WebhookVerificationError",
    "verify_signature",
    "construct_signature",
    "__version__",
]
