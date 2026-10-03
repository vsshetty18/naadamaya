"""
NAADAMAYA storage interface.

The rest of the app talks ONLY to this interface, never to the disk or to S3
directly. Local disk (development) and S3-compatible storage (AWS S3,
Cloudflare R2, and similar) both implement it, so moving to production
storage is a configuration change, not a code change. Google Cloud Storage or
Azure Blob can be added later as one more subclass.

Files are addressed by a storage KEY such as
    users/<user_id>/recordings/<recording_id>/<file_id>-original.m4a
Keys come from utils/file_utils.py. They are never user-supplied and never
raw filesystem paths. Every implementation must call `check_key()` before
touching anything.

The analysis worker needs a real file on disk (FFmpeg and librosa read files).
`materialize()` gives it one: the local backend returns the file in place, and
the S3 backend downloads to a temporary file and deletes it afterwards.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import os
import tempfile
from typing import BinaryIO

from app.utils.file_utils import validate_storage_key


class StorageError(Exception):
    """Something went wrong in the storage layer. Details go to the logs only."""


class StorageNotFoundError(StorageError):
    """The key does not exist."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    content_type: str | None = None


class StorageBackend(ABC):
    """Implemented by LocalStorage and S3Storage."""

    # ------------------------------------------------------
    # Required operations
    # ------------------------------------------------------
    @abstractmethod
    def put_file(self, key: str, source_path: str, content_type: str | None = None) -> StoredFile:
        """Stores the file at `source_path` under `key`. Overwrites nothing silently:
        keys contain a random id, so a collision means a bug and raises StorageError."""

    @abstractmethod
    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredFile:
        """Stores data read from a binary stream (for example an upload)."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Opens the stored file for reading. Raises StorageNotFoundError."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int:
        """Size in bytes. Raises StorageNotFoundError."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Deletes one file. Missing files are ignored (deleting twice is fine)."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Deletes everything under a prefix, e.g. 'users/<id>/' for account
        deletion. Returns how many files were removed."""

    @abstractmethod
    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str | None:
        """
        A short-lived direct download URL, or None when the backend cannot make
        one (local disk). When None, the API streams the file through an
        authenticated endpoint after checking ownership.
        """

    # ------------------------------------------------------
    # Provided for free
    # ------------------------------------------------------
    @contextmanager
    def materialize(self, key: str) -> Iterator[str]:
        """
        Yields a real local file path for `key` (used by FFmpeg and librosa).
        The default implementation copies to a temporary file and removes it
        afterwards. LocalStorage overrides this to avoid the copy.
        """
        check_key(key)
        suffix = os.path.splitext(key)[1]
        fd, path = tempfile.mkstemp(prefix="naadamaya-", suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as out, self.open(key) as src:
                while chunk := src.read(1024 * 1024):
                    out.write(chunk)
            yield path
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def check_key(key: str) -> str:
    """Rejects unsafe keys (traversal, absolute paths). Raises StorageError."""
    try:
        return validate_storage_key(key)
    except ValueError as exc:
        raise StorageError("Unsafe storage key.") from exc
