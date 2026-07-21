"""Webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time

from openbot_sdk._errors import WebhookVerificationError

DEFAULT_TOLERANCE_SECONDS = 300  # 5 minutes


def verify_signature(
    payload: bytes,
    signature: str,
    secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> None:
    """
    Verify an OpenBot.ai webhook signature.

    Signatures are expected in the format::

        t=<timestamp>,v1=<hex_signature>

    Args:
        payload: Raw request body bytes.
        signature: Signature header value.
        secret: Webhook signing secret.
        tolerance_seconds: Maximum allowed age of the timestamp.

    Raises:
        WebhookVerificationError: if the signature is missing, malformed,
            expired, or invalid.
    """
    if not signature:
        raise WebhookVerificationError("Signature header is empty")

    parts: dict[str, str] = {}
    for item in signature.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key.strip()] = value.strip()

    timestamp_str = parts.get("t")
    expected_sig = parts.get("v1")
    if not timestamp_str or not expected_sig:
        raise WebhookVerificationError("Signature header is malformed")

    try:
        timestamp = int(timestamp_str)
    except ValueError as exc:
        raise WebhookVerificationError("Invalid timestamp") from exc

    now = int(time.time())
    if abs(now - timestamp) > tolerance_seconds:
        raise WebhookVerificationError("Webhook timestamp is outside tolerance")

    signed_payload = str(timestamp).encode("ascii") + b"." + payload
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, expected_sig):
        raise WebhookVerificationError("Webhook signature mismatch")


def construct_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """
    Construct a webhook signature for testing.

    Args:
        payload: Raw request body bytes.
        secret: Webhook signing secret.
        timestamp: Unix timestamp; defaults to now.

    Returns:
        Signature header value.
    """
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = str(timestamp).encode("ascii") + b"." + payload
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"
