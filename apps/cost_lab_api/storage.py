from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Protocol


class CostLabStorage(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or not key or ".." in path.parts:
        raise ValueError("Invalid Cost Lab storage key")
    return str(path)


class FilesystemCostLabStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        target = self._path(key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o600)

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, key: str) -> None:
        target = self._path(key)
        target.unlink(missing_ok=True)
        self._remove_empty_parents(target.parent)

    def delete_prefix(self, prefix: str) -> None:
        import shutil

        target = self._path(prefix)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()

    def _path(self, key: str) -> Path:
        target = (self.root / _safe_key(key)).resolve()
        if self.root not in target.parents:
            raise ValueError("Invalid Cost Lab storage key")
        return target

    def _remove_empty_parents(self, directory: Path) -> None:
        while directory != self.root:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent


class S3CostLabStorage:
    prefix = "cost-lab/"

    def __init__(
        self, bucket: str, *, region: str | None = None, client: Any | None = None
    ) -> None:
        if not bucket:
            raise ValueError("Cost Lab S3 bucket name is required")
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self.bucket = bucket
        self.client = client

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def get(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        except self.client.exceptions.ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        body = response["Body"]
        try:
            return bytes(body.read())
        finally:
            body.close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))

    def delete_prefix(self, prefix: str) -> None:
        full_prefix = self._key(prefix).rstrip("/") + "/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", ())]
            for offset in range(0, len(keys), 1000):
                response = self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": keys[offset : offset + 1000]},
                )
                if response.get("Errors"):
                    raise OSError("S3 did not delete every Cost Lab object")

    def _key(self, key: str) -> str:
        return self.prefix + _safe_key(key)
