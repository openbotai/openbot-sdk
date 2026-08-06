"""
openbot-sdk — Python SDK for OpenBot.ai.

openbot-sdk helps embodied AI and robot learning teams evaluate policies,
curate teleoperation data, and generate synthetic training data through
a simple Python interface.

Example:
    >>> import openbot_sdk
    >>> client = openbot_sdk.Client()
    >>> run = client.bench.rollout(
    ...     policy="openvla-7b",
    ...     embodiment="franka_panda",
    ...     task="pick_mug → pour → handover",
    ... )
    >>> result = run.wait()
    >>> print(result.task_success)
"""

from openbot_sdk._artifact import DataArtifact
from openbot_sdk._bench import BenchResource
from openbot_sdk._client import Client
from openbot_sdk._data import DataResource, ExportFormat, ReviewStatus
from openbot_sdk._data_job import DataJob, DataJobResult
from openbot_sdk._errors import (
    APIError,
    APIResponseError,
    AuthenticationError,
    ClientClosedError,
    DataJobError,
    DataUploadError,
    NetworkError,
    OpenBotError,
    RunError,
    WebhookVerificationError,
)
from openbot_sdk._models import DataExport, Dataset, ReviewOutput
from openbot_sdk._run import Run, RunResult
from openbot_sdk._upload import DataUpload
from openbot_sdk._version import __version__
from openbot_sdk._webhooks import construct_signature, verify_signature

__all__ = [
    "Client",
    "BenchResource",
    "DataResource",
    "DataJob",
    "DataJobResult",
    "DataUpload",
    "DataArtifact",
    "Dataset",
    "ReviewOutput",
    "DataExport",
    "ReviewStatus",
    "ExportFormat",
    "Run",
    "RunResult",
    "OpenBotError",
    "AuthenticationError",
    "APIError",
    "APIResponseError",
    "NetworkError",
    "ClientClosedError",
    "RunError",
    "DataJobError",
    "DataUploadError",
    "WebhookVerificationError",
    "verify_signature",
    "construct_signature",
    "__version__",
]
