"""Call the Hosted OpenBot Data API 0.0.2 client workflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

import openbot_sdk


def run_data_workflow(
    client: openbot_sdk.Client,
    *,
    video: str | Path,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    provenance: dict[str, Any] | None = None,
    taxonomy: Sequence[str] = ("reach", "grasp", "place"),
    delete_raw_after_job: bool = False,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    """Upload a video and stop at the mandatory human-review boundary."""
    video_path = Path(video)
    upload = client.data.create_upload(
        path=video_path,
        dataset_id=dataset_id,
        idempotency_key=f"demo-{video_path.name}",
    )
    upload.upload()
    upload.wait_until_ready(poll_interval=poll_interval)
    if dataset_id is None:
        dataset = client.data.register_dataset(
            name=dataset_name or video_path.stem,
            format="video/mp4",
            upload_id=upload.id,
            size_bytes=video_path.stat().st_size,
            metadata={"preflight": provenance} if provenance is not None else None,
            idempotency_key=f"demo-dataset-{upload.id}",
        )
        dataset_id = dataset.id
    job = client.data.subtask_job(
        dataset_id=dataset_id,
        upload_id=upload.id,
        video_key="observation.images.top",
        taxonomy=list(taxonomy),
        idempotency_key=f"demo-job-{upload.id}",
        metadata={"preflight": provenance} if provenance is not None else None,
    )
    result = job.wait(poll_interval=poll_interval)
    summary: dict[str, Any] = {
        "upload_id": upload.id,
        "dataset_id": dataset_id,
        "job_id": job.id,
        "review_output_id": result.review_output_id,
    }
    if delete_raw_after_job:
        upload.delete()
    return summary


def load_preflight_provenance(
    manifest_path: str | Path,
    audit_path: str | Path,
) -> dict[str, Any]:
    """Load only portable OpenBot Data provenance fields, never local paths."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "openbot.dataset_manifest.v1":
        raise ValueError("Unsupported OpenBot Data manifest schema")
    if audit.get("schema_version") != "openbot.dataset_audit.v1":
        raise ValueError("Unsupported OpenBot Data audit schema")
    return {
        "manifest_schema_version": manifest["schema_version"],
        "dataset_fingerprint": manifest.get("dataset_fingerprint"),
        "tool_version": manifest.get("tool_version"),
        "audit_schema_version": audit["schema_version"],
        "audit_summary": audit.get("summary", {}),
    }


def export_approved_review_output(
    client: openbot_sdk.Client,
    *,
    review_output_id: str,
    output: str | Path,
    delete_export: bool = False,
) -> dict[str, Any]:
    """Export a review output that a human already approved in the review UI."""
    export = client.data.export(review_output_id, format="lerobot_sidecar")
    export_id = str(export["id"])
    downloaded = client.data.download_export_to(export_id, output)
    summary = {
        "review_output_id": review_output_id,
        "export_id": export_id,
        "output": str(downloaded) if downloaded is not None else None,
    }
    if delete_export:
        client.data.delete_export(export_id)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call the Hosted OpenBot Data API 0.0.2 upload and review flow."
    )
    parser.add_argument("video", nargs="?", help="Local robot-video file")
    parser.add_argument("--dataset-id", help="Existing private dataset ID; omit to register one")
    parser.add_argument("--dataset-name", help="Name for a newly registered dataset")
    parser.add_argument("--preflight-manifest", help="OpenBot Data manifest JSON")
    parser.add_argument("--preflight-audit", help="OpenBot Data audit JSON")
    parser.add_argument("--out", default="./subtasks.json", help="Export destination")
    parser.add_argument(
        "--review-output-id",
        help="Export an existing review output that is already approved",
    )
    parser.add_argument(
        "--delete-export",
        action="store_true",
        help="Delete the downloaded export resource after a successful download",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENBOT_BASE_URL", "https://api.openbot.ai/v1"),
    )
    args = parser.parse_args()
    with openbot_sdk.Client(base_url=args.base_url) as client:
        if args.review_output_id is not None:
            summary = export_approved_review_output(
                client,
                review_output_id=args.review_output_id,
                output=args.out,
                delete_export=args.delete_export,
            )
        else:
            if args.video is None:
                parser.error("video is required for a new ingest")
            if (args.preflight_manifest is None) != (args.preflight_audit is None):
                parser.error("--preflight-manifest and --preflight-audit must be used together")
            if args.delete_export:
                parser.error("--delete-export requires --review-output-id")
            provenance = (
                load_preflight_provenance(args.preflight_manifest, args.preflight_audit)
                if args.preflight_manifest is not None
                else None
            )
            summary = run_data_workflow(
                client,
                video=args.video,
                dataset_id=args.dataset_id,
                dataset_name=args.dataset_name,
                provenance=provenance,
            )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.review_output_id is None:
        print(
            "Review the job evidence, then approve the returned review_output_id "
            "in the review UI. Rerun with --review-output-id only after approval."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
