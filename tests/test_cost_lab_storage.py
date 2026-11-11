from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from apps.cost_lab_api.storage import FilesystemCostLabStorage, S3CostLabStorage


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakePaginator:
    def __init__(self, client: FakeS3Client) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803, ANN201
        keys = [{"Key": key} for key in self.client.objects if key.startswith(Prefix)]
        return ({"Contents": keys},)


class FakeS3Client:
    exceptions = SimpleNamespace(ClientError=FakeClientError)

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Key: str, Body: bytes, **_: object) -> None:  # noqa: N803
        self.objects[Key] = Body

    def get_object(self, *, Key: str, **_: object) -> dict[str, BytesIO]:  # noqa: N803
        if Key not in self.objects:
            raise FakeClientError("NoSuchKey")
        return {"Body": BytesIO(self.objects[Key])}

    def delete_object(self, *, Key: str, **_: object) -> None:  # noqa: N803
        self.objects.pop(Key, None)

    def get_paginator(self, operation: str) -> FakePaginator:
        assert operation == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(self, *, Delete: dict[str, list[dict[str, str]]], **_: object) -> dict:
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)
        return {}


def test_filesystem_cost_lab_storage_round_trip_and_prefix_delete(tmp_path) -> None:
    storage = FilesystemCostLabStorage(tmp_path)
    storage.put("datasets/asset/original.jpg", b"image", "image/jpeg")

    assert storage.get("datasets/asset/original.jpg") == b"image"
    storage.delete_prefix("datasets/asset")
    assert storage.get("datasets/asset/original.jpg") is None


def test_s3_cost_lab_storage_uses_private_prefix() -> None:
    client = FakeS3Client()
    storage = S3CostLabStorage("cost-lab-private", client=client)
    storage.put("benchmarks/run/result.jpg", b"result", "image/jpeg")

    assert client.objects == {"cost-lab/benchmarks/run/result.jpg": b"result"}
    assert storage.get("benchmarks/run/result.jpg") == b"result"
    storage.delete_prefix("benchmarks/run")
    assert storage.get("benchmarks/run/result.jpg") is None
