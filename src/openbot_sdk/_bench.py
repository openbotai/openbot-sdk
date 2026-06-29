"""Bench resource for policy evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openbot_sdk._run import Run

if TYPE_CHECKING:
    from openbot_sdk._client import Client


class BenchResource:
    """Evaluate robot policies on real or simulated embodiments."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def rollout(
        self,
        *,
        policy: str,
        embodiment: str,
        task: str,
        rollouts: int = 200,
        seeds: int = 10,
        sim: str | None = None,
        real_hw: bool = False,
        edge_target: str | None = None,
        webhook: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Run:
        """
        Queue a policy evaluation rollout.

        Args:
            policy: Policy checkpoint or model name (e.g. ``openvla-7b``).
            embodiment: Robot embodiment (e.g. ``franka_panda``).
            task: Task description or subtask chain.
            rollouts: Number of rollouts to run.
            seeds: Number of random seeds.
            sim: Simulator to use (e.g. ``isaac_sim``).
            real_hw: Whether to run on real hardware.
            edge_target: Edge deployment target (e.g. ``jetson_orin``).
            webhook: URL to call when the run completes.
            idempotency_key: Optional idempotency key.
            metadata: Optional key-value metadata.

        Returns:
            Run handle for polling or webhook handling.
        """
        body: dict[str, Any] = {
            "policy": policy,
            "embodiment": embodiment,
            "task": task,
            "rollouts": rollouts,
            "seeds": seeds,
            "real_hw": real_hw,
        }
        if sim is not None:
            body["sim"] = sim
        if edge_target is not None:
            body["edge_target"] = edge_target
        if webhook is not None:
            body["webhook"] = webhook
        if metadata is not None:
            body["metadata"] = metadata

        headers: dict[str, str] | None = None
        if idempotency_key is not None:
            headers = {"Idempotency-Key": idempotency_key}

        response = self._client._request(
            "POST",
            "/bench/rollouts",
            json=body,
            headers=headers,
        )
        return Run(self._client, response["id"], data=response)

    def get(self, run_id: str) -> Run:
        """Fetch an existing rollout run by ID."""
        return Run(self._client, run_id).refresh()
