import time

import pytest

import openbotai
from openbotai._webhooks import construct_signature, verify_signature


def test_verify_signature_success() -> None:
    payload = b'{"event":"bench.rollout.completed"}'
    secret = "whsec_test"
    signature = construct_signature(payload, secret)

    verify_signature(payload, signature, secret)


def test_verify_signature_rejects_invalid_secret() -> None:
    payload = b'{"event":"bench.rollout.completed"}'
    signature = construct_signature(payload, "whsec_test")

    with pytest.raises(openbotai.WebhookVerificationError):
        verify_signature(payload, signature, "wrong-secret")


def test_verify_signature_rejects_missing_signature() -> None:
    with pytest.raises(openbotai.WebhookVerificationError):
        verify_signature(b"payload", "", "secret")


def test_verify_signature_rejects_malformed_signature() -> None:
    with pytest.raises(openbotai.WebhookVerificationError):
        verify_signature(b"payload", "v1=abc", "secret")


def test_verify_signature_rejects_expired_timestamp() -> None:
    payload = b'{"event":"bench.rollout.completed"}'
    secret = "whsec_test"
    old_timestamp = int(time.time()) - 1000
    signature = construct_signature(payload, secret, timestamp=old_timestamp)

    with pytest.raises(openbotai.WebhookVerificationError):
        verify_signature(payload, signature, secret, tolerance_seconds=300)
