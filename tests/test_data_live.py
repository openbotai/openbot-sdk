"""Opt-in production smoke for the Hosted Data API 0.0.2 release gate."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

import openbot_sdk


def load_demo_module() -> Any:
    example_path = (
        Path(__file__).resolve().parents[1] / "examples" / "data_v002_workflow.py"
    )
    spec = importlib.util.spec_from_file_location("openbot_sdk_live_data_demo", example_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("OPENBOT_RUN_LIVE_DATA_SMOKE") != "1",
    reason="set OPENBOT_RUN_LIVE_DATA_SMOKE=1 to run the mutating Hosted API smoke",
)
def test_production_upload_job_stops_at_review_smoke() -> None:
    required = {
        "OPENBOT_API_KEY": os.environ.get("OPENBOT_API_KEY"),
        "OPENBOT_LIVE_DATASET_ID": os.environ.get("OPENBOT_LIVE_DATASET_ID"),
        "OPENBOT_LIVE_VIDEO": os.environ.get("OPENBOT_LIVE_VIDEO"),
    }
    missing = [name for name, value in required.items() if not value]
    assert not missing, f"missing live smoke configuration: {', '.join(missing)}"
    video = Path(str(required["OPENBOT_LIVE_VIDEO"]))
    assert video.is_file(), f"live smoke video was not found: {video}"
    base_url = os.environ.get("OPENBOT_BASE_URL", "https://api.openbot.ai/v1")
    demo = load_demo_module()

    with openbot_sdk.Client(
        api_key=str(required["OPENBOT_API_KEY"]),
        base_url=base_url,
    ) as client:
        summary = demo.run_data_workflow(
            client,
            video=video,
            dataset_id=str(required["OPENBOT_LIVE_DATASET_ID"]),
            delete_raw_after_job=True,
            poll_interval=2,
        )

    assert summary["review_output_id"]


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("OPENBOT_RUN_LIVE_DATA_SMOKE") != "1",
    reason="set OPENBOT_RUN_LIVE_DATA_SMOKE=1 to run the mutating Hosted API smoke",
)
def test_production_export_requires_preapproved_review_smoke(tmp_path: Path) -> None:
    required = {
        "OPENBOT_API_KEY": os.environ.get("OPENBOT_API_KEY"),
        "OPENBOT_LIVE_APPROVED_REVIEW_OUTPUT_ID": os.environ.get(
            "OPENBOT_LIVE_APPROVED_REVIEW_OUTPUT_ID"
        ),
    }
    missing = [name for name, value in required.items() if not value]
    assert not missing, (
        "approve a dedicated smoke fixture in the review UI, then configure: "
        + ", ".join(missing)
    )
    output = tmp_path / "live-subtasks.json"
    base_url = os.environ.get("OPENBOT_BASE_URL", "https://api.openbot.ai/v1")
    demo = load_demo_module()

    with openbot_sdk.Client(
        api_key=str(required["OPENBOT_API_KEY"]),
        base_url=base_url,
    ) as client:
        summary = demo.export_approved_review_output(
            client,
            review_output_id=str(required["OPENBOT_LIVE_APPROVED_REVIEW_OUTPUT_ID"]),
            output=output,
            delete_export=True,
        )

    assert summary["export_id"]
    assert output.is_file() and output.stat().st_size > 0
