# Getting started

```bash
pip install openbot-sdk
export OPENBOT_API_KEY="ob_..."
```

```python
from openbot_sdk import Client

with Client() as client:
    status = client.request("GET", "/status")
    print(status)
```

For local API development only:

```python
client = Client(
    api_key="ob_local_test",
    base_url="http://127.0.0.1:8787/v1",
    allow_insecure_http=True,
)
```

The SDK contains no Hosted Data workflow or robot-data processing logic.
