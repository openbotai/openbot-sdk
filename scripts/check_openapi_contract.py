#!/usr/bin/env python3
"""Validate an OpenBot OpenAPI file or URL against the SDK contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast
from urllib.request import Request, urlopen

from openbot_sdk._contract import openapi_compatibility_errors
from openbot_sdk._version import __version__


def load(source: str) -> dict[str, Any]:
    if source.startswith(("https://", "http://")):
        # The production edge rejects the default Python-urllib User-Agent with 403.
        request = Request(source, headers={"User-Agent": f"openbot_sdk-python/{__version__}"})
        with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit CLI input
            return cast(dict[str, Any], json.load(response))
    return cast(dict[str, Any], json.loads(Path(source).read_text(encoding="utf-8")))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_openapi_contract.py FILE_OR_URL", file=sys.stderr)
        return 2
    errors = openapi_compatibility_errors(load(sys.argv[1]))
    if errors:
        print("OpenAPI contract is incompatible:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"OpenAPI contract is compatible with openbot-sdk {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
