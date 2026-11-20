from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from apps.api.wearo_api.google_drive import (
    RESUMABLE_THRESHOLD,
    CredentialCipher,
    DriveAuthorizationRevoked,
    GoogleDriveClient,
    GoogleDriveConfig,
)


@dataclass
class FakeResponse:
    status_code: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""

    def json(self) -> dict[str, Any]:
        return self.body


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _call(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._call("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._call("POST", url, kwargs)

    def put(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._call("PUT", url, kwargs)


def config() -> GoogleDriveConfig:
    return GoogleDriveConfig(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
        redirect_uri="https://wearo.example/api/integrations/google-drive/callback",
        encryption_key=b"k" * 32,
        settings_redirect_uri="https://wearo.example/app/profile",
    )


def test_credential_cipher_authenticates_context_and_ciphertext() -> None:
    cipher = CredentialCipher(b"a" * 32)
    encrypted = cipher.encrypt("refresh-secret", context="refresh-token:account-a")

    assert b"refresh-secret" not in encrypted
    assert cipher.decrypt(encrypted, context="refresh-token:account-a") == "refresh-secret"
    with pytest.raises(ValueError, match="Stored credential is invalid"):
        cipher.decrypt(encrypted, context="refresh-token:account-b")


def test_config_requires_a_32_byte_external_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEARO_GOOGLE_DRIVE_CLIENT_ID", "client")
    monkeypatch.setenv("WEARO_GOOGLE_DRIVE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("WEARO_GOOGLE_DRIVE_REDIRECT_URI", "https://wearo.example/callback")
    monkeypatch.setenv(
        "WEARO_GOOGLE_DRIVE_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("="),
    )

    loaded = GoogleDriveConfig.from_env()

    assert loaded is not None
    assert loaded.encryption_key == b"x" * 32


def test_refresh_marks_invalid_grant_as_reconnect_required() -> None:
    transport = FakeTransport([FakeResponse(400, {"error": "invalid_grant"})])

    with pytest.raises(DriveAuthorizationRevoked):
        GoogleDriveClient(config(), transport).refresh("revoked-refresh-token")


def test_small_upload_uses_multipart_and_job_id_for_reconciliation() -> None:
    transport = FakeTransport([FakeResponse(200, {"id": "drive-file-1"})])
    client = GoogleDriveClient(config(), transport)
    job_id = uuid4()

    result = client.upload(
        access_token="access-token",  # noqa: S106
        job_id=job_id,
        folder_id="folder-1",
        filename="try-on.webp",
        content=b"webp-image",
        mime_type="image/webp",
    )

    assert result == "drive-file-1"
    _, url, call = transport.calls[0]
    assert "uploadType=multipart" not in url
    assert call["params"]["uploadType"] == "multipart"
    assert str(job_id).encode() in call["data"]
    assert b"image/webp" in call["data"]
    assert call["headers"]["Authorization"] == "Bearer access-token"


def test_resumable_upload_continues_from_confirmed_offset() -> None:
    transport = FakeTransport(
        [
            FakeResponse(308, headers={"Range": "bytes=0-9"}),
            FakeResponse(200, {"id": "drive-file-2"}),
        ]
    )
    client = GoogleDriveClient(config(), transport)
    content = b"z" * (RESUMABLE_THRESHOLD + 1)

    result = client.upload(
        access_token="access-token",  # noqa: S106
        job_id=uuid4(),
        folder_id="folder-1",
        filename="try-on.png",
        content=content,
        mime_type="image/png",
        upload_session="https://upload.example/session-1",
    )

    assert result == "drive-file-2"
    assert transport.calls[0][2]["headers"]["Content-Range"].startswith("bytes */")
    assert transport.calls[1][2]["headers"]["Content-Range"].startswith("bytes 10-")
    assert len(transport.calls[1][2]["data"]) == len(content) - 10
