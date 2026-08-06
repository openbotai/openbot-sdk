"""Immutable local-file identity and bounded upload streams."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx

from openbot_sdk._errors import DataUploadError


@dataclass(frozen=True)
class UploadSource:
    """A local file pinned to the identity used to create an upload resource."""

    path: Path
    size_bytes: int
    checksum_sha256: str
    mtime_ns: int
    inode: int

    @classmethod
    def from_path(cls, path: str | Path) -> UploadSource:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        before = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        after = source.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
        ):
            raise DataUploadError("Upload file changed while its checksum was calculated")
        return cls(
            path=source,
            size_bytes=after.st_size,
            checksum_sha256=digest.hexdigest(),
            mtime_ns=after.st_mtime_ns,
            inode=after.st_ino,
        )

    def assert_unchanged(self) -> None:
        try:
            current = self.path.stat()
        except OSError as exc:
            raise DataUploadError("Upload file is no longer available") from exc
        if (
            current.st_size != self.size_bytes
            or current.st_mtime_ns != self.mtime_ns
            or current.st_ino != self.inode
        ):
            raise DataUploadError("Upload file changed after the upload resource was created")

    def stream(self, offset: int, size: int) -> FileSliceStream:
        if offset < 0 or size < 0 or offset + size > self.size_bytes:
            raise DataUploadError("Upload slice is outside the pinned local file")
        return FileSliceStream(self, offset, size)


class FileSliceStream(httpx.SyncByteStream):
    """Seekable, bounded stream that never buffers an entire upload part."""

    def __init__(self, source: UploadSource, offset: int, size: int) -> None:
        self._source = source
        self._offset = offset
        self._size = size

    def __iter__(self) -> Iterator[bytes]:
        self._source.assert_unchanged()
        remaining = self._size
        with self._source.path.open("rb") as file:
            file.seek(self._offset)
            while remaining:
                chunk = file.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise DataUploadError("Upload file ended before the requested slice")
                remaining -= len(chunk)
                yield chunk
        self._source.assert_unchanged()
