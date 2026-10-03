"""
NAADAMAYA storage factory.

The rest of the app does:

    from app.services.storage.storage_service import get_storage
    storage = get_storage()
    storage.put_file(key, path)

and never needs to know whether files live on local disk or in S3/R2.
The backend is chosen once from STORAGE_PROVIDER and reused.

It also holds two small helpers used by several API routes:
  - build_download_url(): a signed link when the backend supports one,
    otherwise None (the route then streams the file after an ownership check).
  - delete_quietly(): cleanup that never raises, for use in error paths.
"""

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.services.storage.base import StorageBackend, StorageError
from app.services.storage.local import LocalStorage
from app.services.storage.s3 import S3Storage

log = get_logger("naadamaya.storage")


@lru_cache
def get_storage() -> StorageBackend:
    """Returns the configured storage backend (created once per process)."""
    provider = settings.storage_provider.lower()

    if provider == "local":
        return LocalStorage(settings.storage_local_dir)

    if provider == "s3":
        return S3Storage(
            bucket=settings.storage_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
        )

    # config.py already rejects unknown values; this is a final guard.
    raise StorageError(f"Unknown STORAGE_PROVIDER '{provider}'.")


def build_download_url(key: str | None, filename: str | None = None) -> str | None:
    """
    A short-lived direct link for `key`, or None when the key is empty or the
    backend cannot sign links (local disk). Call this ONLY after checking that
    the signed-in user owns the file.
    """
    if not key:
        return None
    try:
        return get_storage().signed_url(
            key, expires_in=settings.signed_url_expire_seconds, filename=filename
        )
    except StorageError:
        log.warning("could not create a download link")
        return None


def delete_quietly(*keys: str | None) -> None:
    """Best-effort cleanup for error paths. Never raises."""
    storage = get_storage()
    for key in keys:
        if not key:
            continue
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001 - cleanup must not hide the original error
            log.warning("could not delete a stored file during cleanup")
