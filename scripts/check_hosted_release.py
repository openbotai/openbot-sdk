#!/usr/bin/env python3
"""Verify that the Hosted Data API advertises the SDK release gate."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise RuntimeError(f"Invalid semantic version: {value}") from exc


def load_release(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "openbot-sdk-release-check/0.0.2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Hosted release endpoint returned HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Hosted release endpoint could not be reached") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Hosted release endpoint returned a non-object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="https://api.openbot.ai/v1/release",
        help="Hosted release metadata endpoint",
    )
    parser.add_argument(
        "--version-file",
        default="VERSION",
        help="SDK VERSION file",
    )
    args = parser.parse_args()

    package_version = Path(args.version_file).read_text(encoding="utf-8").strip()
    release = load_release(args.url)
    products = release.get("products")
    compatibility = release.get("compatibility")
    smoke = release.get("production_smoke")
    if not isinstance(products, dict) or products.get("data") != "0.0.2":
        raise RuntimeError("Hosted Data product 0.0.2 is not live")
    if not isinstance(compatibility, dict):
        raise RuntimeError("Hosted release metadata has no compatibility block")
    minimum = compatibility.get("openbot_sdk_min")
    if not isinstance(minimum, str) or parse_version(package_version) < parse_version(minimum):
        raise RuntimeError("SDK version does not satisfy the Hosted minimum")
    openapi_hash = release.get("openapi_sha256")
    if (
        not isinstance(openapi_hash, str)
        or len(openapi_hash) != 64
        or any(character not in "0123456789abcdef" for character in openapi_hash)
    ):
        raise RuntimeError("Hosted release metadata has no valid OpenAPI SHA-256")
    if not isinstance(smoke, dict) or smoke.get("passed") is not True:
        raise RuntimeError("Hosted production smoke has not passed")
    print(
        json.dumps(
            {
                "data_product": products["data"],
                "openapi_sha256": openapi_hash,
                "sdk_version": package_version,
                "smoke": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"hosted release check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
