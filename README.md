# openbot-sdk

> Thin Python client for the [OpenBot.ai](https://openbot.ai) platform API.

[Library documentation](docs/README.md) · [API reference](docs/api-reference.md) ·
[Hosted API documentation](https://openbot.ai/api/docs) · [Source repository](https://github.com/openbotai/openbot-sdk)

The SDK handles authentication, safe HTTP retries, platform-issued file
transfers, polling, and streaming downloads. OpenBot's servers own evaluation,
data processing, review state, storage, authorization, and retention.

```python
import openbot_sdk

client = openbot_sdk.Client()  # reads OPENBOT_API_KEY

run = client.bench.rollout(
    policy="openvla-7b",
    embodiment="franka_panda",
    task="open_drawer → pick_mug → pour → handover",
    rollouts=200,
    seeds=10,
    sim="isaac_sim",
    real_hw=True,
)

result = run.wait()
print(result.task_success)          # 0.73
print(result.subtask["handover"])   # 0.60
print(result.sim_to_real_gap)       # -0.29
print(result.intervention_rate)     # 0.14
```

## Install

`0.0.2` is currently a source candidate and is not published on PyPI. Install a
checkout while developing against the matching Hosted API:

```bash
pip install -e .
```

Supported and tested on Python 3.9–3.12.

## Runnable Data API client example

The repository includes a `0.0.2` client flow using only public SDK methods. It
calls the Hosted platform; it does not process or annotate video locally:

```bash
pip install -e .
export OPENBOT_API_KEY="ob_live_..."
python examples/data_v002_workflow.py ./episode-0001.mp4 \
  --dataset-id data_123 \
  --out ./subtasks.json
```

The first run uploads and processes the video, then returns the review output ID.
After checking that existing review output in the review UI, approve and download
it without creating another upload:

```bash
python examples/data_v002_workflow.py \
  --review-output-id review_123 \
  --out ./subtasks.json
```

The second command only exports a review output already approved by a human in
the review UI; the demo never changes review status. Add `--delete-export` only
when the downloaded export has been verified and the server copy may be removed.
The demo is exercised against a mocked API during the package test suite; a real
run requires the matching Hosted Data API.

Maintainers can run the mutating production release smoke only after the Hosted
API is deployed:

```bash
export OPENBOT_RUN_LIVE_DATA_SMOKE=1
export OPENBOT_API_KEY="ob_live_..."
export OPENBOT_LIVE_DATASET_ID="data_123"
export OPENBOT_LIVE_VIDEO="./episode-0001.mp4"
pytest -m live tests/test_data_live.py
```

This first smoke uploads and processes a fixture, stops at review, and deletes
the raw upload. Export smoke is separate: approve a dedicated fixture in the UI,
set `OPENBOT_LIVE_APPROVED_REVIEW_OUTPUT_ID`, then run the live suite again. No
test auto-approves model output.

## Authentication

Set the environment variable:

```bash
export OPENBOT_API_KEY="ob_live_..."
```

Or pass it directly:

```python
client = openbot_sdk.Client(api_key="ob_live_...")
```

## Usage

### Evaluate a robot policy

```python
run = client.bench.rollout(
    policy="openvla-7b",
    embodiment="franka_panda",
    task="kitchen_handover",
    rollouts=200,
    seeds=10,
    edge_target="jetson_orin",
)

result = run.wait()
print(result.task_success)
```

### Generate and review a robot-video subtask timeline

```python
job = client.data.subtask_job(
    dataset_id="data_123",
    video_key="observation.images.top",
    video_url="https://public.example/episode.mp4",
    task_hint="place the red block in the bowl",
    taxonomy=["reach", "grasp", "place"],
    idempotency_key="episode-123",
)

result = job.wait()
edited = result.annotations
# Review/edit `edited["timeline"]["segments"]` against the evidence frames.
client.data.review(
    result.review_output_id,
    status="approved",
    annotations=edited,
    expected_revision=result.review_output["revision_id"],
)
export = client.data.export(result.review_output_id, format="lerobot_sidecar")
client.data.download_export_to(export.id, "subtasks.json")
```

### Upload a private robot video

```python
upload = client.data.create_upload(
    path="episode-0001.mp4",
    dataset_id="data_123",
    idempotency_key="episode-0001",
)
upload.upload()
upload.wait_until_ready()

job = client.data.subtask_job(
    dataset_id="data_123",
    upload_id=upload.id,
    video_key="observation.images.top",
    taxonomy=["reach", "grasp", "place"],
)

for active_job in client.data.list_jobs(status="running"):
    print(active_job.id, active_job.stage)
```

These helpers only call the Hosted Data API `0.0.2` contract. Upload mode,
verification, processing, authorization, retention, and deletion semantics are
decided and enforced by the platform. Production availability still requires
the Hosted release manifest and production smoke.

Unreviewed model output is never treated as ground truth. Segment confidence remains `None` unless the configured annotation profile has been independently calibrated.

### Handle webhooks

```python
from openbot_sdk import verify_signature

payload = request.body
signature = request.headers["OpenBot-Signature"]
secret = "whsec_..."

verify_signature(payload, signature, secret)
```

Pass the raw request bytes unchanged. This also supports binary and non-UTF-8 bodies.

### Timeouts and retries

```python
client = openbot_sdk.Client(
    timeout=60,
    download_timeout=600,
    max_retries=2,
    retry_backoff=0.25,
)
content = client.data.download_export("export_123", timeout=900)
```

The client retries idempotent methods and mutations carrying an `Idempotency-Key` on transport errors, `429`, and transient `5xx` responses. Plain HTTP base URLs are rejected by default; use `allow_insecure_http=True` only for explicit local testing.

### Poll with custom settings

```python
result = run.wait(poll_interval=10.0, timeout=7200.0)
```

## Development

```bash
pip install -e ".[dev]"
python scripts/check_version.py
pytest -v
ruff check src tests
mypy src
scripts/test_matrix.sh
python -m build
```

The local matrix script requires [`uv`](https://docs.astral.sh/uv/) and tests
Python 3.9–3.12 without requiring a repository CI workflow.

`VERSION` is the package version source of truth. Before publishing a GitHub
Release, the Hosted release manifest must pass
`python scripts/check_hosted_release.py`. The release workflow then validates
the tag, test matrix, build metadata, Hosted gate, and wheel before publishing
to PyPI.

## Status

The current source version is `0.0.2`, an unreleased thin-client candidate.
Bench and Data API wrappers are implemented, but the self-service Hosted Data
API is still `0.0.1` in production. Machine-generated timelines require explicit
human review before export.

## Roadmap

- `0.0.1`: API authentication, retries, Bench rollout helpers, Data
  register/subtask/poll/review/export/download, and webhook verification.
- [`0.0.2` implemented in SDK source](docs/version-0.0.2.md): thin wrappers for
  platform-issued private upload, resource listing, status/cancellation, and
  authenticated downloads. Production availability remains gated by the Hosted API.

## License

MIT
