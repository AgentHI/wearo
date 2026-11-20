from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from urllib.parse import urlencode
from uuid import UUID

import requests
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Engine, text

from .media_runtime import MediaRuntimeError

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
IDENTITY_SCOPES = ("openid", "email")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
RESUMABLE_THRESHOLD = 5 * 1024 * 1024


class DriveIntegrationError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class DriveAuthorizationRevoked(DriveIntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "GOOGLE_DRIVE_RECONNECT_REQUIRED",
            "Google Drive authorization has expired. Reconnect Google Drive.",
        )


@dataclass(frozen=True)
class GoogleDriveConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    encryption_key: bytes
    settings_redirect_uri: str

    @classmethod
    def from_env(cls) -> GoogleDriveConfig | None:
        client_id = os.environ.get("WEARO_GOOGLE_DRIVE_CLIENT_ID", "").strip()
        if not client_id:
            return None
        client_secret = os.environ.get("WEARO_GOOGLE_DRIVE_CLIENT_SECRET", "").strip()
        redirect_uri = os.environ.get("WEARO_GOOGLE_DRIVE_REDIRECT_URI", "").strip()
        raw_key = os.environ.get("WEARO_GOOGLE_DRIVE_ENCRYPTION_KEY", "").strip()
        if not client_secret or not redirect_uri or not raw_key:
            raise RuntimeError(
                "Google Drive requires client secret, redirect URI, and encryption key"
            )
        try:
            key = base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
        except ValueError as error:
            raise RuntimeError("WEARO_GOOGLE_DRIVE_ENCRYPTION_KEY is invalid") from error
        if len(key) != 32:
            raise RuntimeError("WEARO_GOOGLE_DRIVE_ENCRYPTION_KEY must decode to 32 bytes")
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            encryption_key=key,
            settings_redirect_uri=os.environ.get(
                "WEARO_GOOGLE_DRIVE_SETTINGS_REDIRECT_URI",
                f"{os.environ.get('WEARO_CONSUMER_ORIGIN', 'http://localhost:5173').rstrip('/')}/app/profile",
            ),
        )


class CredentialCipher:
    """AES-GCM envelope for credentials; the key is supplied only by the environment."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("credential encryption key must contain 32 bytes")
        self._aes = AESGCM(key)

    def encrypt(self, value: str, *, context: str) -> bytes:
        nonce = secrets.token_bytes(12)
        encrypted = bytes(self._aes.encrypt(nonce, value.encode(), context.encode()))
        return b"\x01" + nonce + encrypted

    def decrypt(self, value: bytes, *, context: str) -> str:
        if len(value) < 30 or value[0] != 1:
            raise DriveIntegrationError(
                "CREDENTIAL_DECRYPTION_FAILED", "Stored credential is invalid."
            )
        try:
            plaintext = bytes(self._aes.decrypt(value[1:13], value[13:], context.encode()))
            return plaintext.decode()
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise DriveIntegrationError(
                "CREDENTIAL_DECRYPTION_FAILED", "Stored credential is invalid."
            ) from None


class HttpResponse(Protocol):
    status_code: int
    headers: Any
    content: bytes

    def json(self) -> Any: ...


class HttpTransport(Protocol):
    def get(self, url: str, **kwargs: Any) -> HttpResponse: ...
    def post(self, url: str, **kwargs: Any) -> HttpResponse: ...
    def put(self, url: str, **kwargs: Any) -> HttpResponse: ...


def _json(response: HttpResponse) -> dict[str, Any]:
    try:
        value = response.json()
    except (ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _google_error(response: HttpResponse) -> DriveIntegrationError:
    body = _json(response)
    error = body.get("error", {})
    if isinstance(error, str):
        reason = error
        message = str(body.get("error_description", error))
    else:
        details = error.get("errors", []) if isinstance(error, dict) else []
        reason = str(details[0].get("reason", "")) if details else ""
        message = (
            str(error.get("message", "Google Drive request failed."))
            if isinstance(error, dict)
            else "Google Drive request failed."
        )
    if response.status_code == 401 or reason in {"authError", "invalidCredentials"}:
        return DriveAuthorizationRevoked()
    if reason in {"storageQuotaExceeded", "quotaExceeded"} and response.status_code != 429:
        return DriveIntegrationError(
            "GOOGLE_DRIVE_STORAGE_QUOTA_EXCEEDED", "Google Drive storage quota is full."
        )
    retryable = response.status_code == 429 or response.status_code >= 500
    return DriveIntegrationError(
        "GOOGLE_DRIVE_TRANSIENT" if retryable else "GOOGLE_DRIVE_UPLOAD_FAILED",
        message[:500],
        retryable=retryable,
    )


class GoogleDriveClient:
    def __init__(self, config: GoogleDriveConfig, transport: HttpTransport | None = None) -> None:
        self.config = config
        self.transport: HttpTransport = transport or cast(HttpTransport, requests.Session())

    def exchange_code(self, code: str, verifier: str) -> dict[str, Any]:
        try:
            response = self.transport.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.config.redirect_uri,
                },
                timeout=20,
            )
        except requests.RequestException as error:
            raise DriveIntegrationError(
                "GOOGLE_OAUTH_UNAVAILABLE",
                "Google authorization is temporarily unavailable.",
                retryable=True,
            ) from error
        if response.status_code != 200:
            raise _google_error(response)
        body = _json(response)
        if not body.get("access_token"):
            raise DriveIntegrationError(
                "GOOGLE_OAUTH_INVALID_RESPONSE", "Google authorization failed."
            )
        return body

    def userinfo(self, access_token: str) -> tuple[str, str]:
        response = self._request("get", GOOGLE_USERINFO_URL, access_token)
        body = _json(response)
        if not body.get("sub") or not body.get("email") or body.get("email_verified") is False:
            raise DriveIntegrationError(
                "GOOGLE_IDENTITY_UNAVAILABLE", "Google did not return a verified account email."
            )
        return str(body["sub"]), str(body["email"])

    def refresh(self, refresh_token: str) -> str:
        try:
            response = self.transport.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        except requests.RequestException as error:
            raise DriveIntegrationError(
                "GOOGLE_TOKEN_REFRESH_UNAVAILABLE",
                "Google authorization is temporarily unavailable.",
                retryable=True,
            ) from error
        body = _json(response)
        if response.status_code != 200:
            if body.get("error") in {"invalid_grant", "unauthorized_client"}:
                raise DriveAuthorizationRevoked()
            raise _google_error(response)
        if not body.get("access_token"):
            raise DriveAuthorizationRevoked()
        return str(body["access_token"])

    def ensure_folders(
        self, access_token: str, root_folder_id: str | None, tryons_folder_id: str | None
    ) -> tuple[str, str]:
        root = self._usable_folder(access_token, root_folder_id)
        if root is None:
            root = self._find_folder(access_token, "wearoRoot", "root")
        if root is None:
            root = self._create_folder(access_token, "Wearo.ai", "root", "wearoRoot")
        tryons = self._usable_folder(access_token, tryons_folder_id)
        if tryons is None:
            tryons = self._find_folder(access_token, "wearoTryOns", root)
        if tryons is None:
            tryons = self._create_folder(access_token, "Try-Ons", root, "wearoTryOns")
        return root, tryons

    def reconcile(self, access_token: str, job_id: UUID) -> str | None:
        query = (
            f"trashed = false and appProperties has {{ key='wearoSyncJobId' and value='{job_id}' }}"
        )
        response = self._request(
            "get",
            DRIVE_FILES_URL,
            access_token,
            params={"q": query, "fields": "files(id,createdTime)", "pageSize": 10},
        )
        files = _json(response).get("files", [])
        return str(files[0]["id"]) if files else None

    def upload(
        self,
        *,
        access_token: str,
        job_id: UUID,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
        upload_session: str | None = None,
        save_upload_session: Any = None,
    ) -> str:
        metadata = {
            "name": filename,
            "parents": [folder_id],
            "appProperties": {"wearoSyncJobId": str(job_id)},
        }
        if len(content) <= RESUMABLE_THRESHOLD:
            boundary = f"wearo-{secrets.token_hex(16)}"
            prefix = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata, separators=(',', ':'))}\r\n"
                f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
            ).encode()
            body = prefix + content + f"\r\n--{boundary}--\r\n".encode()
            response = self._request(
                "post",
                DRIVE_UPLOAD_URL,
                access_token,
                params={"uploadType": "multipart", "fields": "id"},
                headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                data=body,
                timeout=90,
            )
        else:
            session_uri = upload_session
            offset = 0
            if session_uri:
                probe = self._resumable_request(
                    "put",
                    session_uri,
                    access_token,
                    headers={"Content-Length": "0", "Content-Range": f"bytes */{len(content)}"},
                    data=b"",
                )
                if probe.status_code in {200, 201}:
                    file_id = _json(probe).get("id")
                    if file_id:
                        return str(file_id)
                elif probe.status_code == 308:
                    uploaded_range = str(probe.headers.get("Range", ""))
                    if "-" in uploaded_range:
                        offset = int(uploaded_range.rsplit("-", 1)[1]) + 1
                elif probe.status_code in {404, 410}:
                    session_uri = None
                else:
                    raise _google_error(probe)
            if not session_uri:
                start = self._request(
                    "post",
                    DRIVE_UPLOAD_URL,
                    access_token,
                    params={"uploadType": "resumable", "fields": "id"},
                    headers={
                        "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": mime_type,
                        "X-Upload-Content-Length": str(len(content)),
                    },
                    data=json.dumps(metadata),
                )
                session_uri = str(start.headers.get("Location", ""))
                if not session_uri:
                    raise DriveIntegrationError(
                        "GOOGLE_DRIVE_INVALID_RESPONSE",
                        "Google Drive did not create an upload session.",
                        retryable=True,
                    )
                if save_upload_session is not None:
                    save_upload_session(session_uri)
            response = self._resumable_request(
                "put",
                session_uri,
                access_token,
                headers={
                    "Content-Type": mime_type,
                    "Content-Length": str(len(content) - offset),
                    "Content-Range": f"bytes {offset}-{len(content) - 1}/{len(content)}",
                },
                data=content[offset:],
                timeout=180,
            )
            if response.status_code == 308:
                raise DriveIntegrationError(
                    "GOOGLE_DRIVE_TRANSIENT",
                    "Google Drive upload is incomplete.",
                    retryable=True,
                )
            if not 200 <= response.status_code < 300:
                raise _google_error(response)
        file_id = _json(response).get("id")
        if not file_id:
            raise DriveIntegrationError(
                "GOOGLE_DRIVE_INVALID_RESPONSE",
                "Google Drive did not confirm the upload.",
                retryable=True,
            )
        return str(file_id)

    def _usable_folder(self, access_token: str, folder_id: str | None) -> str | None:
        if not folder_id:
            return None
        try:
            response = self._request(
                "get",
                f"{DRIVE_FILES_URL}/{folder_id}",
                access_token,
                params={"fields": "id,mimeType,trashed"},
                allow_not_found=True,
            )
        except DriveIntegrationError:
            return None
        if response.status_code == 404:
            return None
        body = _json(response)
        return (
            folder_id if body.get("mimeType") == FOLDER_MIME and not body.get("trashed") else None
        )

    def _find_folder(self, access_token: str, marker: str, parent: str) -> str | None:
        query = (
            f"mimeType = '{FOLDER_MIME}' and trashed = false and '{parent}' in parents "
            f"and appProperties has {{ key='wearoFolder' and value='{marker}' }}"
        )
        response = self._request(
            "get",
            DRIVE_FILES_URL,
            access_token,
            params={"q": query, "fields": "files(id)", "pageSize": 10},
        )
        files = _json(response).get("files", [])
        return str(files[0]["id"]) if files else None

    def _create_folder(self, access_token: str, name: str, parent: str, marker: str) -> str:
        response = self._request(
            "post",
            DRIVE_FILES_URL,
            access_token,
            params={"fields": "id"},
            json={
                "name": name,
                "mimeType": FOLDER_MIME,
                "parents": [parent],
                "appProperties": {"wearoFolder": marker},
            },
        )
        folder_id = _json(response).get("id")
        if not folder_id:
            raise DriveIntegrationError(
                "GOOGLE_DRIVE_INVALID_RESPONSE", "Google Drive folder creation failed."
            )
        return str(folder_id)

    def _request(
        self,
        method: str,
        url: str,
        access_token: str,
        *,
        allow_not_found: bool = False,
        **kwargs: Any,
    ) -> HttpResponse:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {access_token}"
        kwargs.setdefault("timeout", 30)
        try:
            if method == "get":
                response = self.transport.get(url, headers=headers, **kwargs)
            elif method == "post":
                response = self.transport.post(url, headers=headers, **kwargs)
            elif method == "put":
                response = self.transport.put(url, headers=headers, **kwargs)
            else:
                raise ValueError("unsupported HTTP method")
        except requests.RequestException as error:
            raise DriveIntegrationError(
                "GOOGLE_DRIVE_TRANSIENT", "Google Drive is temporarily unavailable.", retryable=True
            ) from error
        if 200 <= response.status_code < 300 or (allow_not_found and response.status_code == 404):
            return response
        raise _google_error(response)

    def _resumable_request(
        self,
        method: str,
        url: str,
        access_token: str,
        *,
        headers: dict[str, str],
        data: bytes,
        timeout: int = 30,
    ) -> HttpResponse:
        request_headers = {**headers, "Authorization": f"Bearer {access_token}"}
        try:
            if method != "put":
                raise ValueError("unsupported resumable HTTP method")
            return self.transport.put(url, headers=request_headers, data=data, timeout=timeout)
        except requests.RequestException as error:
            raise DriveIntegrationError(
                "GOOGLE_DRIVE_TRANSIENT",
                "Google Drive is temporarily unavailable.",
                retryable=True,
            ) from error


@dataclass(frozen=True)
class ClaimedDriveJob:
    job_id: UUID
    connection_id: UUID
    account_id: UUID
    render_job_id: UUID
    result_asset_id: UUID
    attempt_count: int
    encrypted_refresh_token: bytes
    tryons_folder_id: str
    encrypted_upload_session: bytes | None


class GoogleDriveService:
    def __init__(
        self,
        engine: Engine,
        config: GoogleDriveConfig,
        *,
        client: GoogleDriveClient | None = None,
    ) -> None:
        self.engine = engine
        self.config = config
        self.cipher = CredentialCipher(config.encryption_key)
        self.client = client or GoogleDriveClient(config)

    def begin_connection(self, account_id: UUID, session_token: str) -> str:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state_hash = hashlib.sha256(state.encode()).digest()
        session_hash = hashlib.sha256(session_token.encode()).digest()
        expires = datetime.now(UTC) + timedelta(minutes=10)
        encrypted_verifier = self.cipher.encrypt(verifier, context=f"oauth-verifier:{account_id}")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO user_drive_connections
                       (account_id, status, auto_sync_enabled, oauth_state_hash,
                        encrypted_code_verifier, oauth_session_hash, oauth_state_expires_at)
                       VALUES (:account, 'CONNECTING', false, :state, :verifier, :session, :expires)
                       ON CONFLICT (account_id) DO UPDATE SET
                         status='CONNECTING', oauth_state_hash=EXCLUDED.oauth_state_hash,
                         encrypted_code_verifier=EXCLUDED.encrypted_code_verifier,
                         oauth_session_hash=EXCLUDED.oauth_session_hash,
                         oauth_state_expires_at=EXCLUDED.oauth_state_expires_at,
                         updated_at=now()"""
                ),
                {
                    "account": account_id,
                    "state": state_hash,
                    "verifier": encrypted_verifier,
                    "session": session_hash,
                    "expires": expires,
                },
            )
        parameters = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join((*IDENTITY_SCOPES, DRIVE_SCOPE)),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(parameters)}"

    def complete_connection(
        self, account_id: UUID, session_token: str, state: str, code: str
    ) -> dict[str, object]:
        return self._complete_connection(
            state,
            code,
            account_id=account_id,
            session_token=session_token,
        )

    def complete_connection_callback(self, state: str, code: str) -> dict[str, object]:
        """Complete Google's return using the short-lived, one-time OAuth state.

        Browser privacy controls may omit Wearo's session cookie on the cross-site
        return from Google. The initiating endpoint is authenticated, while this
        callback is bound to the account by the unique state record and PKCE
        verifier created for that authenticated request.
        """
        return self._complete_connection(state, code)

    def _complete_connection(
        self,
        state: str,
        code: str,
        *,
        account_id: UUID | None = None,
        session_token: str | None = None,
    ) -> dict[str, object]:
        state_hash = hashlib.sha256(state.encode()).digest()
        if account_id is not None and session_token is not None:
            attempt_query = text(
                """SELECT connection_id, account_id, encrypted_code_verifier,
                          encrypted_refresh_token, google_subject, status,
                          root_folder_id, tryons_folder_id
                   FROM user_drive_connections
                   WHERE oauth_state_hash=:state
                     AND oauth_state_expires_at > now()
                     AND status='CONNECTING'
                     AND account_id=:account
                     AND oauth_session_hash=:session
                   FOR UPDATE"""
            )
            parameters: dict[str, object] = {
                "state": state_hash,
                "account": account_id,
                "session": hashlib.sha256(session_token.encode()).digest(),
            }
        else:
            attempt_query = text(
                """SELECT connection_id, account_id, encrypted_code_verifier,
                          encrypted_refresh_token, google_subject, status,
                          root_folder_id, tryons_folder_id
                   FROM user_drive_connections
                   WHERE oauth_state_hash=:state
                     AND oauth_state_expires_at > now()
                     AND status='CONNECTING'
                   FOR UPDATE"""
            )
            parameters = {"state": state_hash}
        with self.engine.begin() as connection:
            row = connection.execute(attempt_query, parameters).mappings().one_or_none()
            if row is None:
                raise DriveIntegrationError(
                    "INVALID_OAUTH_STATE", "Google connection request is invalid or expired."
                )
            resolved_account_id = cast(UUID, row["account_id"])
            connection.execute(
                text(
                    """UPDATE user_drive_connections SET oauth_state_hash=NULL,
                         encrypted_code_verifier=NULL, oauth_session_hash=NULL,
                         oauth_state_expires_at=NULL, updated_at=now()
                       WHERE connection_id=:connection"""
                ),
                {"connection": row["connection_id"]},
            )
        try:
            verifier = self.cipher.decrypt(
                bytes(row["encrypted_code_verifier"]),
                context=f"oauth-verifier:{resolved_account_id}",
            )
            tokens = self.client.exchange_code(code, verifier)
            access_token = str(tokens["access_token"])
            subject, email = self.client.userinfo(access_token)
            prior_subject = row["google_subject"]
            if prior_subject and row["status"] != "DISCONNECTED" and prior_subject != subject:
                raise DriveIntegrationError(
                    "GOOGLE_ACCOUNT_MISMATCH",
                    "Reconnect the same Google account or disconnect it first.",
                )
            refresh_token = tokens.get("refresh_token")
            encrypted_refresh = (
                self.cipher.encrypt(
                    str(refresh_token), context=f"refresh-token:{resolved_account_id}"
                )
                if refresh_token
                else row["encrypted_refresh_token"]
            )
            if encrypted_refresh is None:
                raise DriveIntegrationError(
                    "GOOGLE_REFRESH_TOKEN_MISSING",
                    "Google did not grant offline access. Try connecting again.",
                )
            root_folder, tryons_folder = self.client.ensure_folders(
                access_token, row["root_folder_id"], row["tryons_folder_id"]
            )
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """UPDATE user_drive_connections SET google_subject=:subject,
                             google_email=:email, encrypted_refresh_token=:refresh,
                             root_folder_id=:root, tryons_folder_id=:tryons,
                             status='CONNECTED', last_error_code=NULL, updated_at=now()
                           WHERE connection_id=:connection"""
                    ),
                    {
                        "subject": subject,
                        "email": email,
                        "refresh": encrypted_refresh,
                        "root": root_folder,
                        "tryons": tryons_folder,
                        "connection": row["connection_id"],
                    },
                )
        except DriveIntegrationError as error:
            self._record_connection_failure(cast(UUID, row["connection_id"]), error.code)
            raise
        except Exception as error:
            if "uq_user_drive_connections_google_subject" in str(error):
                connection_error = DriveIntegrationError(
                    "GOOGLE_ACCOUNT_ALREADY_CONNECTED",
                    "This Google account is connected to another Wearo account.",
                )
                self._record_connection_failure(
                    cast(UUID, row["connection_id"]), connection_error.code
                )
                raise connection_error from None
            self._record_connection_failure(
                cast(UUID, row["connection_id"]), "GOOGLE_DRIVE_CONNECTION_FAILED"
            )
            raise
        return self.status(resolved_account_id)

    def _record_connection_failure(self, connection_id: UUID, error_code: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE user_drive_connections SET
                         status=CASE
                           WHEN last_error_code='GOOGLE_DRIVE_RECONNECT_REQUIRED'
                             THEN 'RECONNECT_REQUIRED'
                           WHEN encrypted_refresh_token IS NULL THEN 'DISCONNECTED'
                           ELSE 'CONNECTED' END,
                         last_error_code=:error, updated_at=now()
                       WHERE connection_id=:connection"""
                ),
                {"connection": connection_id, "error": error_code},
            )

    def cancel_connection_attempt(self, account_id: UUID, session_token: str, state: str) -> None:
        self._cancel_connection_attempt(
            state,
            account_id=account_id,
            session_token=session_token,
        )

    def cancel_connection_callback(self, state: str) -> None:
        self._cancel_connection_attempt(state)

    def _cancel_connection_attempt(
        self,
        state: str,
        *,
        account_id: UUID | None = None,
        session_token: str | None = None,
    ) -> None:
        state_hash = hashlib.sha256(state.encode()).digest()
        if account_id is not None and session_token is not None:
            cancel_query = text(
                """UPDATE user_drive_connections SET
                     status=CASE
                       WHEN last_error_code='GOOGLE_DRIVE_RECONNECT_REQUIRED'
                         THEN 'RECONNECT_REQUIRED'
                       WHEN encrypted_refresh_token IS NULL THEN 'DISCONNECTED'
                       ELSE 'CONNECTED' END,
                     oauth_state_hash=NULL, encrypted_code_verifier=NULL,
                     oauth_session_hash=NULL, oauth_state_expires_at=NULL, updated_at=now()
                   WHERE oauth_state_hash=:state
                     AND oauth_state_expires_at > now()
                     AND status='CONNECTING'
                     AND account_id=:account
                     AND oauth_session_hash=:session"""
            )
            parameters: dict[str, object] = {
                "state": state_hash,
                "account": account_id,
                "session": hashlib.sha256(session_token.encode()).digest(),
            }
        else:
            cancel_query = text(
                """UPDATE user_drive_connections SET
                     status=CASE
                       WHEN last_error_code='GOOGLE_DRIVE_RECONNECT_REQUIRED'
                         THEN 'RECONNECT_REQUIRED'
                       WHEN encrypted_refresh_token IS NULL THEN 'DISCONNECTED'
                       ELSE 'CONNECTED' END,
                     oauth_state_hash=NULL, encrypted_code_verifier=NULL,
                     oauth_session_hash=NULL, oauth_state_expires_at=NULL, updated_at=now()
                   WHERE oauth_state_hash=:state
                     AND oauth_state_expires_at > now()
                     AND status='CONNECTING'"""
            )
            parameters = {"state": state_hash}
        with self.engine.begin() as connection:
            result = connection.execute(cancel_query, parameters)
            if result.rowcount != 1:
                raise DriveIntegrationError(
                    "INVALID_OAUTH_STATE", "Google connection request is invalid or expired."
                )

    def status(self, account_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT c.status, c.google_email, c.auto_sync_enabled,
                              c.tryons_folder_id, c.last_successful_sync_at,
                              c.last_error_code,
                              (SELECT count(*) FROM drive_sync_jobs j
                               WHERE j.account_id=c.account_id
                                 AND j.status='PERMANENT_FAILURE') AS failed_sync_count
                       FROM user_drive_connections c WHERE c.account_id=:account"""
                    ),
                    {"account": account_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return {
                "status": "DISCONNECTED",
                "connected": False,
                "account_email": None,
                "auto_sync_enabled": False,
                "destination_folder": "Wearo.ai/Try-Ons",
                "last_successful_sync_at": None,
                "failed_sync_count": 0,
                "reconnect_required": False,
                "last_error_code": None,
            }
        return {
            "status": row["status"],
            "connected": row["status"] == "CONNECTED",
            "account_email": row["google_email"],
            "auto_sync_enabled": bool(row["auto_sync_enabled"]),
            "destination_folder": "Wearo.ai/Try-Ons" if row["tryons_folder_id"] else None,
            "last_successful_sync_at": row["last_successful_sync_at"],
            "failed_sync_count": row["failed_sync_count"],
            "reconnect_required": row["status"] == "RECONNECT_REQUIRED",
            "last_error_code": row["last_error_code"],
        }

    def set_enabled(self, account_id: UUID, enabled: bool) -> dict[str, object]:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE user_drive_connections
                       SET auto_sync_enabled=:enabled, updated_at=now()
                       WHERE account_id=:account AND status='CONNECTED'"""
                ),
                {"account": account_id, "enabled": enabled},
            )
            if result.rowcount != 1:
                raise DriveIntegrationError(
                    "GOOGLE_DRIVE_NOT_CONNECTED", "Connect Google Drive first."
                )
        return self.status(account_id)

    def disconnect(self, account_id: UUID) -> None:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """SELECT connection_id FROM user_drive_connections
                       WHERE account_id=:account FOR UPDATE"""
                ),
                {"account": account_id},
            ).one_or_none()
            if row is None:
                return
            connection.execute(
                text(
                    """UPDATE user_drive_connections SET status='DISCONNECTED',
                         auto_sync_enabled=false, encrypted_refresh_token=NULL,
                         google_subject=NULL, google_email=NULL,
                         oauth_state_hash=NULL, encrypted_code_verifier=NULL,
                         oauth_session_hash=NULL, oauth_state_expires_at=NULL, updated_at=now()
                       WHERE account_id=:account"""
                ),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status='CANCELLED', worker_id=NULL,
                         lease_expires_at=NULL, encrypted_upload_session=NULL, updated_at=now()
                       WHERE account_id=:account
                         AND status IN ('PENDING', 'RETRY', 'PROCESSING')"""
                ),
                {"account": account_id},
            )

    def retry_failed(self, account_id: UUID) -> int:
        with self.engine.begin() as connection:
            connected = connection.execute(
                text(
                    """SELECT 1 FROM user_drive_connections
                       WHERE account_id=:account AND status='CONNECTED'"""
                ),
                {"account": account_id},
            ).one_or_none()
            if connected is None:
                raise DriveIntegrationError(
                    "GOOGLE_DRIVE_NOT_CONNECTED", "Reconnect Google Drive first."
                )
            result = connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status='RETRY', available_at=now(),
                         last_error_code=NULL, last_error_message=NULL, updated_at=now()
                       WHERE account_id=:account AND status='PERMANENT_FAILURE'"""
                ),
                {"account": account_id},
            )
            connection.execute(
                text(
                    """UPDATE user_drive_connections SET failed_sync_count=0,
                         last_error_code=NULL, updated_at=now()
                       WHERE account_id=:account"""
                ),
                {"account": account_id},
            )
            return int(result.rowcount)


class DriveSyncWorker:
    def __init__(
        self,
        engine: Engine,
        service: GoogleDriveService,
        media: Any,
        *,
        worker_id: str,
        lease: timedelta = timedelta(minutes=10),
        max_attempts: int = 8,
    ) -> None:
        self.engine = engine
        self.service = service
        self.media = media
        self.worker_id = worker_id
        self.lease = lease
        self.max_attempts = max_attempts

    def recover_expired(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status='RETRY', worker_id=NULL,
                         lease_expires_at=NULL, available_at=:now, updated_at=:now
                       WHERE status='PROCESSING' AND lease_expires_at <= :now"""
                ),
                {"now": current},
            )
            return int(result.rowcount)

    def claim_next(self, *, now: datetime | None = None) -> ClaimedDriveJob | None:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """WITH candidate AS (
                         SELECT j.job_id
                         FROM drive_sync_jobs j
                         JOIN user_drive_connections c USING (connection_id)
                         WHERE j.status IN ('PENDING', 'RETRY') AND j.available_at <= :now
                           AND c.status='CONNECTED' AND c.auto_sync_enabled
                           AND pg_try_advisory_xact_lock(hashtextextended(j.connection_id::text, 0))
                           AND NOT EXISTS (
                             SELECT 1 FROM drive_sync_jobs active
                             WHERE active.connection_id=j.connection_id
                               AND active.status='PROCESSING'
                           )
                         ORDER BY j.available_at, j.created_at
                         FOR UPDATE OF j SKIP LOCKED LIMIT 1
                       )
                       UPDATE drive_sync_jobs j SET status='PROCESSING',
                         worker_id=:worker, lease_expires_at=:lease,
                         attempt_count=j.attempt_count + 1, updated_at=:now
                       FROM candidate WHERE j.job_id=candidate.job_id
                       RETURNING j.job_id, j.connection_id, j.account_id, j.render_job_id,
                         j.result_asset_id, j.attempt_count, j.encrypted_upload_session"""
                    ),
                    {"now": current, "worker": self.worker_id, "lease": current + self.lease},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            connection_row = (
                connection.execute(
                    text(
                        """SELECT encrypted_refresh_token, tryons_folder_id
                       FROM user_drive_connections WHERE connection_id=:connection"""
                    ),
                    {"connection": row["connection_id"]},
                )
                .mappings()
                .one()
            )
        return ClaimedDriveJob(
            **row,
            encrypted_refresh_token=bytes(connection_row["encrypted_refresh_token"]),
            tryons_folder_id=str(connection_row["tryons_folder_id"]),
        )

    def run_once(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        job = self.claim_next(now=current)
        if job is None:
            return False
        try:
            refresh_token = self.service.cipher.decrypt(
                job.encrypted_refresh_token, context=f"refresh-token:{job.account_id}"
            )
            access_token = self.service.client.refresh(refresh_token)
            existing = self.service.client.reconcile(access_token, job.job_id)
            if existing:
                self._complete(job, existing, current)
                return True
            content, mime_type = self.media.read_original(job.result_asset_id, job.account_id)
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
            upload_session = (
                self.service.cipher.decrypt(
                    job.encrypted_upload_session, context=f"upload-session:{job.job_id}"
                )
                if job.encrypted_upload_session
                else None
            )
            file_id = self.service.client.upload(
                access_token=access_token,
                job_id=job.job_id,
                folder_id=job.tryons_folder_id,
                filename=f"wearo-try-on-{job.render_job_id}.{extension}",
                content=content,
                mime_type=mime_type,
                upload_session=upload_session,
                save_upload_session=lambda value: self._save_upload_session(job, value),
            )
            self._complete(job, file_id, current)
        except DriveAuthorizationRevoked as error:
            self._reconnect_required(job, error, current)
        except DriveIntegrationError as error:
            if error.code == "CREDENTIAL_DECRYPTION_FAILED":
                self._reconnect_required(job, DriveAuthorizationRevoked(), current)
            else:
                self._fail(job, error, current)
        except (KeyError, MediaRuntimeError, OSError) as error:
            self._fail(
                job,
                DriveIntegrationError("DRIVE_SYNC_ASSET_UNAVAILABLE", str(error), retryable=True),
                current,
            )
        return True

    def _save_upload_session(self, job: ClaimedDriveJob, value: str) -> None:
        encrypted = self.service.cipher.encrypt(value, context=f"upload-session:{job.job_id}")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE drive_sync_jobs
                       SET encrypted_upload_session=:session, updated_at=now()
                       WHERE job_id=:job AND status='PROCESSING' AND worker_id=:worker"""
                ),
                {"session": encrypted, "job": job.job_id, "worker": self.worker_id},
            )

    def _complete(self, job: ClaimedDriveJob, file_id: str, now: datetime) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status='COMPLETED', drive_file_id=:file,
                         synced_at=:now, lease_expires_at=NULL, worker_id=NULL,
                         encrypted_upload_session=NULL, last_error_code=NULL,
                         last_error_message=NULL, updated_at=:now
                       WHERE job_id=:job AND status='PROCESSING' AND worker_id=:worker"""
                ),
                {"file": file_id, "now": now, "job": job.job_id, "worker": self.worker_id},
            )
            if result.rowcount == 1:
                connection.execute(
                    text(
                        """UPDATE user_drive_connections SET last_successful_sync_at=:now,
                             last_error_code=NULL, updated_at=:now
                           WHERE connection_id=:connection"""
                    ),
                    {"now": now, "connection": job.connection_id},
                )

    def _reconnect_required(
        self, job: ClaimedDriveJob, error: DriveIntegrationError, now: datetime
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE user_drive_connections SET status='RECONNECT_REQUIRED',
                         auto_sync_enabled=false, last_error_code=:code,
                         failed_sync_count=failed_sync_count + 1, updated_at=:now
                       WHERE connection_id=:connection"""
                ),
                {"code": error.code, "now": now, "connection": job.connection_id},
            )
            connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status='PERMANENT_FAILURE',
                         last_error_code=:code, last_error_message=:message,
                         lease_expires_at=NULL, worker_id=NULL, updated_at=:now
                       WHERE connection_id=:connection
                         AND status IN ('PENDING', 'RETRY', 'PROCESSING')"""
                ),
                {
                    "code": error.code,
                    "message": str(error)[:500],
                    "now": now,
                    "connection": job.connection_id,
                },
            )

    def _fail(self, job: ClaimedDriveJob, error: DriveIntegrationError, now: datetime) -> None:
        permanent = not error.retryable or job.attempt_count >= self.max_attempts
        delay = min(3600, 2 ** min(job.attempt_count, 10)) + secrets.randbelow(1000) / 1000
        next_attempt = now + timedelta(seconds=delay)
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE drive_sync_jobs SET status=:status, available_at=:available,
                         last_error_code=:code, last_error_message=:message,
                         lease_expires_at=NULL, worker_id=NULL, updated_at=:now
                       WHERE job_id=:job AND status='PROCESSING' AND worker_id=:worker"""
                ),
                {
                    "status": "PERMANENT_FAILURE" if permanent else "RETRY",
                    "available": next_attempt,
                    "code": error.code,
                    "message": str(error)[:500],
                    "now": now,
                    "job": job.job_id,
                    "worker": self.worker_id,
                },
            )
            if result.rowcount == 1 and permanent:
                connection.execute(
                    text(
                        """UPDATE user_drive_connections
                           SET failed_sync_count=failed_sync_count + 1,
                               last_error_code=:code, updated_at=:now
                           WHERE connection_id=:connection"""
                    ),
                    {"code": error.code, "now": now, "connection": job.connection_id},
                )
