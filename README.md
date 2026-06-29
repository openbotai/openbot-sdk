# openbot-sdk

> Python SDK for [OpenBot.ai](https://openbot.ai) — robot policy evaluation, robot data curation, and synthetic training data.

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

```bash
pip install openbot-sdk
```

Requires Python 3.9+.

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

### Handle webhooks

```python
from openbot_sdk import verify_signature

payload = request.body
signature = request.headers["X-OpenBot-Signature"]
secret = "whsec_..."

verify_signature(payload, signature, secret)
```

### Poll with custom settings

```python
result = run.wait(poll_interval=10.0, timeout=7200.0)
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
ruff check src tests
mypy src
python -m build
```

## Status

openbot-sdk is in early alpha. The initial release supports Bench rollout submission and polling.
Data curation and synthetic data APIs will follow as the OpenBot.ai platform expands.

## License

MIT
