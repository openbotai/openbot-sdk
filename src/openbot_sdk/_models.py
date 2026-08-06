"""Validated, forward-compatible API resource models."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from openbot_sdk._errors import APIResponseError
from openbot_sdk._paths import resource_id


@dataclass(frozen=True)
class APIModel(Mapping[str, Any]):
    """Immutable mapping model that preserves unknown server fields."""

    _raw: Mapping[str, Any]

    def __init__(self, raw: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_raw", MappingProxyType(dict(raw)))

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    @property
    def raw(self) -> Mapping[str, Any]:
        return self._raw

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)

    @classmethod
    def _required_string(cls, raw: Mapping[str, Any], key: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value:
            raise APIResponseError(f"API response has no valid {key}")
        return value


@dataclass(frozen=True, init=False)
class Dataset(APIModel):
    """Registered Data dataset."""

    @property
    def id(self) -> str:
        return resource_id(self._required_string(self._raw, "id"), name="dataset id")

    @property
    def name(self) -> str | None:
        value = self._raw.get("name")
        return str(value) if value is not None else None

    @property
    def format(self) -> str | None:
        value = self._raw.get("format")
        return str(value) if value is not None else None


@dataclass(frozen=True, init=False)
class ReviewOutput(APIModel):
    """Human-review state returned by the Data API."""

    @property
    def id(self) -> str:
        return resource_id(
            self._required_string(self._raw, "id"),
            name="review output id",
        )

    @property
    def status(self) -> str:
        return self._required_string(self._raw, "status")

    @property
    def revision_id(self) -> str | None:
        value = self._raw.get("revision_id")
        return str(value) if value is not None else None


@dataclass(frozen=True, init=False)
class DataExport(APIModel):
    """Approved export resource."""

    @property
    def id(self) -> str:
        return resource_id(self._required_string(self._raw, "id"), name="export id")

    @property
    def status(self) -> str:
        return self._required_string(self._raw, "status")

    @property
    def format(self) -> str:
        return self._required_string(self._raw, "format")

    @property
    def retention_until(self) -> int | None:
        value = self._raw.get("retention_until")
        return int(value) if value is not None else None
