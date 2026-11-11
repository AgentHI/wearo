from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.wearo_api.media_runtime import (
    MediaRuntimeError,
    S3PrivateBlobStore,
    private_blob_store_from_env,
)


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakePaginator:
    def __init__(self, client: FakeS3Client) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str) -> tuple[dict[str, object], ...]:  # noqa: N803
        keys = [{"Key": key} for key in self.client.objects if key.startswith(Prefix)]
        return ({"Contents": keys},)


class FakeS3Client:
    exceptions = SimpleNamespace(ClientError=FakeClientError)

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **options: str) -> None:  # noqa: N803
        assert Bucket == "wearo-private"
        assert options["ServerSideEncryption"] == "AES256"
        self.objects[Key] = Body
        self.content_types[Key] = options["ContentType"]

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BytesIO]:  # noqa: N803
        if Key not in self.objects:
            raise FakeClientError("NoSuchKey")
        return {"Body": BytesIO(self.objects[Key])}

    def get_paginator(self, operation: str) -> FakePaginator:
        assert operation == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(
        self, *, Bucket: str, Delete: dict[str, list[dict[str, str]]]
    ) -> dict[str, list[dict[str, str]]]:  # noqa: N803
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)
        return {"Deleted": Delete["Objects"]}


def test_s3_store_round_trip_and_family_deletion() -> None:
    client = FakeS3Client()
    store = S3PrivateBlobStore("wearo-private", client=client)
    key = "private/accounts/account/person-sources/asset"
    store.put(key, b"original")
    store.put(f"{key}.prepared-v1-person", b"prepared")

    assert store.get(key) == b"original"
    store.delete_asset_family(key)
    assert store.get(key) is None
    assert store.get(f"{key}.prepared-v1-person") is None


def test_s3_store_preserves_content_type() -> None:
    client = FakeS3Client()
    store = S3PrivateBlobStore("wearo-private", client=client)
    key = "private/accounts/account/advertisements/asset"

    store.put(key, b"jpeg", "image/jpeg")

    assert client.content_types[key] == "image/jpeg"


def test_s3_store_rejects_non_private_keys() -> None:
    store = S3PrivateBlobStore("wearo-private", client=FakeS3Client())
    with pytest.raises(MediaRuntimeError):
        store.put("public/image", b"image")


def test_s3_environment_requires_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEARO_PRIVATE_STORAGE_BACKEND", "S3")
    monkeypatch.delenv("WEARO_PRIVATE_STORAGE_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="WEARO_PRIVATE_STORAGE_BUCKET"):
        private_blob_store_from_env()


def test_s3_render_preview_deletion() -> None:
    client = FakeS3Client()
    store = S3PrivateBlobStore("wearo-private", client=client)
    job_id = uuid4()
    key = f"private/previews/{job_id.hex}"
    store.put(key, b"preview")
    store.delete_render_preview(job_id)
    assert store.get(key) is None
