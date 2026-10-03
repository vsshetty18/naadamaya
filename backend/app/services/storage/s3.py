"""
NAADAMAYA S3-compatible storage (production).

Works with AWS S3, Cloudflare R2 and any other S3-compatible service:
  - AWS S3:        leave S3_ENDPOINT_URL empty, set S3_REGION (e.g. "ap-south-1")
  - Cloudflare R2: set S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
                   and S3_REGION=auto

The bucket must be PRIVATE. Files are never public: downloads use short-lived
signed URLs (SIGNED_URL_EXPIRE_SECONDS), created only after the API has
checked that the requesting user owns the file.

Every key is validated (check_key) before use, exactly like local storage.
"""

from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.services.storage.base import (
    StorageBackend,
    StorageError,
    StorageNotFoundError,
    StoredFile,
    check_key,
)

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def _is_not_found(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code", "")) in _NOT_FOUND_CODES


class S3Storage(StorageBackend):
    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        endpoint_url: str = "",
    ) -> None:
        if not bucket or not access_key or not secret_key:
            raise StorageError("S3 storage is not configured (bucket and credentials are required).")

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )

    # ------------------------------------------------------
    # Writing
    # ------------------------------------------------------
    def _extra(self, content_type: str | None) -> dict:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        return extra

    def _ensure_new(self, key: str) -> None:
        if self.exists(key):
            raise StorageError("Storage key already exists.")

    def put_file(self, key: str, source_path: str, content_type: str | None = None) -> StoredFile:
        check_key(key)
        self._ensure_new(key)
        try:
            self.client.upload_file(
                source_path, self.bucket, key, ExtraArgs=self._extra(content_type) or None
            )
            size = self.size(key)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("Could not upload file.") from exc
        return StoredFile(key=key, size=size, content_type=content_type)

    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredFile:
        check_key(key)
        self._ensure_new(key)
        try:
            self.client.upload_fileobj(
                stream, self.bucket, key, ExtraArgs=self._extra(content_type) or None
            )
            size = self.size(key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not upload file.") from exc
        return StoredFile(key=key, size=size, content_type=content_type)

    # ------------------------------------------------------
    # Reading
    # ------------------------------------------------------
    def open(self, key: str) -> BinaryIO:
        check_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise StorageNotFoundError("File not found.") from exc
            raise StorageError("Could not read file.") from exc
        except BotoCoreError as exc:
            raise StorageError("Could not read file.") from exc
        return response["Body"]

    def exists(self, key: str) -> bool:
        check_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise StorageError("Could not check file.") from exc
        except BotoCoreError as exc:
            raise StorageError("Could not check file.") from exc

    def size(self, key: str) -> int:
        check_key(key)
        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if _is_not_found(exc):
                raise StorageNotFoundError("File not found.") from exc
            raise StorageError("Could not read file size.") from exc
        except BotoCoreError as exc:
            raise StorageError("Could not read file size.") from exc

    # ------------------------------------------------------
    # Deleting
    # ------------------------------------------------------
    def delete(self, key: str) -> None:
        check_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)  # missing keys are not an error
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not delete file.") from exc

    def delete_prefix(self, prefix: str) -> int:
        clean = prefix if prefix.endswith("/") else prefix + "/"
        check_key(clean.rstrip("/"))
        deleted = 0
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=clean):
                objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if not objects:
                    continue
                self.client.delete_objects(
                    Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
                )
                deleted += len(objects)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not delete files.") from exc
        return deleted

    # ------------------------------------------------------
    # Links
    # ------------------------------------------------------
    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str | None:
        check_key(key)
        params: dict = {"Bucket": self.bucket, "Key": key}
        if filename:
            safe = "".join(c for c in filename if c.isalnum() or c in " ._-")[:120] or "audio"
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        try:
            return self.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not create download link.") from exc
