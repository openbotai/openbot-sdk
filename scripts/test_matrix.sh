#!/usr/bin/env bash
set -euo pipefail

for version in 3.9 3.10 3.11 3.12; do
  echo "Testing openbot-sdk on Python ${version}"
  uv run --isolated --python "${version}" --extra dev pytest -q
done

echo "Running static checks against the Python 3.9 compatibility target"
uv run --isolated --python 3.9 --extra dev ruff check .
uv run --isolated --python 3.9 --extra dev mypy src
