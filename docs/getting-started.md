# Getting started

> `0.0.2` is an unreleased SDK source candidate. Its upload/list/cancel/artifact
> methods require the matching Hosted Data API and are not production-live while
> the platform release manifest still reports Data `0.0.1`.

## Install

After a public release:

```bash
python -m pip install openbot-sdk
```

The current `0.0.2` source candidate is not yet on PyPI. For a checkout:

```bash
python -m pip install -e .
```

Python 3.9–3.12 is the supported release matrix.

The SDK is a network client. It does not run FFmpeg, parse datasets, generate
annotations, or enforce platform authorization and retention locally.

Maintainers can run that matrix locally with `scripts/test_matrix.sh`; it uses
`uv` isolated environments and does not depend on hosted CI.

## Authenticate

Use an environment variable so API keys do not enter source code:

```bash
export OPENBOT_API_KEY="ob_live_..."
```

```python
import openbot_sdk

client = openbot_sdk.Client()
```

The default base URL is `https://api.openbot.ai/v1`. Plain HTTP is rejected
unless `allow_insecure_http=True` is explicitly set for a local test service.

## Run the Data workflow demo

```bash
python examples/data_v002_workflow.py ./episode-0001.mp4 \
  --dataset-id data_123 \
  --out ./subtasks.json
```

This creates a private upload, transfers the file directly to the server-selected
single or multipart target, waits for verification, and creates a subtask job.
It stops with a `review_output_id`.

After a human checks the evidence and annotations:

```bash
python examples/data_v002_workflow.py \
  --review-output-id review_123 \
  --out ./subtasks.json
```

This second command operates on an existing review output that a human already
approved in the review UI. It does not change review status, upload, or process
the video again. `--delete-export` deletes the server export after a successful
download. It is intentionally opt-in.

## Use the Python API

```python
import openbot_sdk

with openbot_sdk.Client() as client:
    upload = client.data.create_upload(
        path="./episode-0001.mp4",
        dataset_id="data_123",
        idempotency_key="episode-0001",
    )
    upload.upload(part_concurrency=4)
    upload.wait_until_ready(poll_interval=2, timeout=600)

    job = client.data.subtask_job(
        dataset_id="data_123",
        upload_id=upload.id,
        video_key="observation.images.top",
        taxonomy=["reach", "grasp", "place"],
        idempotency_key=f"timeline-{upload.id}",
    )
    result = job.wait(poll_interval=5, timeout=3600)
```

`upload_id` and `video_url` are mutually exclusive. Upload status terminates at
`ready`, `rejected`, `expired`, `aborted`, or `deleted`. Job status terminates at
`done`, `failed`, or `cancelled`.

## Resume and list

```python
upload = client.data.resume_upload("upload_123", path="./episode-0001.mp4")
upload.upload()

for item in client.data.list_uploads(status="ready"):
    print(item.id, item.retention_until)

for dataset in client.data.list_datasets(format="lerobot"):
    print(dataset["id"])

for job in client.data.list_jobs(status="running", dataset_id="data_123"):
    print(job.id, job.stage, job.attempt_count)
```

Listings are lazy iterators. The SDK preserves opaque page tokens, reapplies
filters, removes duplicate IDs across pages, and does not invent a total count.
`page_size` must be between 1 and 100.

## Cancel and inspect progress

```python
job = client.data.get_job("job_123")
print(job.status, job.stage, job.stage_updated_at, job.warnings)
job.cancel()
```

Cancellation uses a stable idempotency key. Progress is expressed as server
stages, not fabricated percentages.

## Review, export, and artifacts

```python
client.data.review(
    result.review_output_id,
    status="approved",
    annotations=result.annotations,
    expected_revision=result.review_output["revision_id"],
)
export = client.data.export(result.review_output_id, format="lerobot_sidecar")
client.data.download_export_to(export["id"], "./subtasks.json")

for artifact in client.data.list_artifacts(job.id):
    print(artifact.id, artifact.kind, artifact.retention_until)
    artifact.download_to(f"./artifacts/{artifact.id}")
```

Authenticated downloads stream to disk. A destination path is written through a
`.part` file and atomically replaced after success; interrupted downloads remove
the partial file. `byte_range="bytes=0-1023"` requests one HTTP range. `head()`
returns response headers without downloading the body.

## Handle errors

```python
import openbot_sdk

try:
    upload.wait_until_ready()
except openbot_sdk.DataUploadError as error:
    print(error)
except openbot_sdk.APIError as error:
    print(error.status_code, error.code, error.retryable, str(error))
```

`APIError` contains only the server's safe message, stable code, HTTP status, and
retryability. Presigned upload requests use a separate HTTP client and never
inherit the OpenBot `Authorization` header.

See the [API reference](api-reference.md) for every public method.
