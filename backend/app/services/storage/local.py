"""
NAADAMAYA local-disk storage (development and single-server setups).

Files live under STORAGE_LOCAL_DIR (default /data/uploads), OUTSIDE the
application code and never inside a web-served folder. The API never serves
this directory directly: downloads go through an authenticated endpoint that
checks ownership first.

Safety:
  - Every key is validated (check_key) before use.
  - The resolved path must stay inside the storage root, so traversal and
    symlink tricks cannot escape it.
  - Writes go to a temporary file and are moved into place atomically, so a
    crash never leaves a half-written file under a real key.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from app.services.storage.base import (
    StorageBackend,
    StorageError,
    StorageNotFoundError,
    StoredFile,
    check_key,
)

CHUNK_SIZE = 1024 * 1024


class LocalStorage(StorageBackend):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Storage directory is not writable.") from exc

    # ------------------------------------------------------
    # Path safety
    # ------------------------------------------------------
    def _path(self, key: str) -> Path:
        check_key(key)
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise StorageError("Unsafe storage key.")
        return path

    # ------------------------------------------------------
    # Writing
    # ------------------------------------------------------
    def _write_atomic(self, key: str, writer) -> StoredFile:
        path = self._path(key)
        if path.exists():
            # Keys contain a random id, so a collision means a bug.
            raise StorageError("Storage key already exists.")
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                writer(out)
            os.replace(tmp_name, path)
        except Exception as exc:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Could not write file.") from exc

        return StoredFile(key=key, size=path.stat().st_size)

    def put_file(self, key: str, source_path: str, content_type: str | None = None) -> StoredFile:
        def writer(out: BinaryIO) -> None:
            with open(source_path, "rb") as src:
                shutil.copyfileobj(src, out, CHUNK_SIZE)

        stored = self._write_atomic(key, writer)
        return StoredFile(stored.key, stored.size, content_type)

    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredFile:
        stored = self._write_atomic(key, lambda out: shutil.copyfileobj(stream, out, CHUNK_SIZE))
        return StoredFile(stored.key, stored.size, content_type)

    # ------------------------------------------------------
    # Reading
    # ------------------------------------------------------
    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return open(path, "rb")
        except FileNotFoundError as exc:
            raise StorageNotFoundError("File not found.") from exc
        except OSError as exc:
            raise StorageError("Could not read file.") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        path = self._path(key)
        if not path.is_file():
            raise StorageNotFoundError("File not found.")
        return path.stat().st_size

    @contextmanager
    def materialize(self, key: str) -> Iterator[str]:
        """The file is already on disk, so no copy is made."""
        path = self._path(key)
        if not path.is_file():
            raise StorageNotFoundError("File not found.")
        yield str(path)

    # ------------------------------------------------------
    # Deleting
    # ------------------------------------------------------
    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Could not delete file.") from exc

    def delete_prefix(self, prefix: str) -> int:
        check_key(prefix.rstrip("/") or "x")
        target = self._path(prefix.rstrip("/"))
        if target == self.root or not target.exists():
            return 0
        count = sum(1 for p in target.rglob("*") if p.is_file()) if target.is_dir() else 1
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            raise StorageError("Could not delete files.") from exc
        return count

    # ------------------------------------------------------
    # Links
    # ------------------------------------------------------
    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str | None:
        """Local disk has no safe public link. The API streams the file instead."""
        return None
