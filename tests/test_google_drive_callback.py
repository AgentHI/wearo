from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from fastapi.testclient import TestClient

from apps.api.wearo_api.google_drive import DriveIntegrationError
from apps.api.wearo_api.http_api import ApiContainer, create_app


@dataclass(frozen=True)
class CallbackConfig:
    settings_redirect_uri: str = "https://wearo.example/app/profile"


class RecordingGoogleDrive:
    config = CallbackConfig()

    def __init__(self) -> None:
        self.completed: list[tuple[str, str]] = []
        self.cancelled: list[str] = []

    def complete_connection_callback(self, state: str, code: str) -> None:
        self.completed.append((state, code))

    def cancel_connection_callback(self, state: str) -> None:
        self.cancelled.append(state)


class FailingGoogleDrive(RecordingGoogleDrive):
    def complete_connection_callback(self, state: str, code: str) -> None:
        raise DriveIntegrationError("GOOGLE_OAUTH_INVALID_RESPONSE", "Authorization failed.")


def callback_client(service: RecordingGoogleDrive) -> TestClient:
    unavailable = cast(Any, None)
    return TestClient(
        create_app(
            ApiContainer(
                engine=unavailable,
                otp=unavailable,
                sessions=unavailable,
                media=unavailable,
                consents=unavailable,
                profiles=unavailable,
                quota=unavailable,
                renders=unavailable,
                google_drive=cast(Any, service),
            )
        ),
        base_url="https://wearo.example",
    )


def test_google_drive_callback_completes_without_browser_session_cookie() -> None:
    service = RecordingGoogleDrive()

    with callback_client(service) as client:
        response = client.get(
            "/api/integrations/google-drive/callback",
            params={"state": "s" * 32, "code": "google-code"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "https://wearo.example/app/profile?drive=connected"
    assert service.completed == [("s" * 32, "google-code")]


def test_google_drive_callback_cancels_without_browser_session_cookie() -> None:
    service = RecordingGoogleDrive()

    with callback_client(service) as client:
        response = client.get(
            "/api/integrations/google-drive/callback",
            params={"state": "s" * 32, "error": "access_denied"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "https://wearo.example/app/profile?drive=cancelled"
    assert service.cancelled == ["s" * 32]


def test_google_drive_callback_redirects_connection_errors_to_profile() -> None:
    service = FailingGoogleDrive()

    with callback_client(service) as client:
        response = client.get(
            "/api/integrations/google-drive/callback",
            params={"state": "s" * 32, "code": "google-code"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://wearo.example/app/profile?drive=error&drive_error=GOOGLE_OAUTH_INVALID_RESPONSE"
    )
