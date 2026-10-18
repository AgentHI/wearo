from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import google.auth
import requests
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

from .image_preflight import VisionAssessment
from .render_preflight import ModelRoute
from .render_provider import HttpResponse, MultipartFile, ProviderError
from .render_quality import QualitySignals


class AnalysisServiceError(RuntimeError):
    pass


PREFLIGHT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "person_count": {"type": "integer", "minimum": 0},
        "full_body_visible": {"type": "boolean"},
        "suspected_minor": {"type": "boolean"},
        "safe_content": {"type": "boolean"},
        "item_kind": {
            "type": "string",
            "enum": ["APPAREL", "JEWELLERY", "AMBIGUOUS", "UNSUPPORTED"],
        },
        "item_count": {"type": "integer", "minimum": 0},
    },
    "required": [
        "person_count",
        "full_body_visible",
        "suspected_minor",
        "safe_content",
        "item_kind",
        "item_count",
    ],
    "additionalProperties": False,
}

QUALITY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "identity_similarity": {"type": "number", "minimum": 0, "maximum": 1},
        "product_similarity": {"type": "number", "minimum": 0, "maximum": 1},
        "color_preserved": {"type": "boolean"},
        "print_preserved": {"type": "boolean"},
        "anatomy_valid": {"type": "boolean"},
        "safe_content": {"type": "boolean"},
        "fabricated_detail": {"type": "boolean"},
    },
    "required": [
        "identity_similarity",
        "product_similarity",
        "color_preserved",
        "print_preserved",
        "anatomy_valid",
        "safe_content",
        "fabricated_detail",
    ],
    "additionalProperties": False,
}


def _image_data_url(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        mime_type = "image/webp"
    else:
        mime_type = "image/jpeg"
    return f"data:{mime_type};base64,{base64.b64encode(content).decode()}"


class OpenAIAnalysisClient:
    """OpenAI Responses vision adapter for preflight and render-quality checks."""

    endpoint = "https://api.openai.com/v1/responses"
    item_kinds: set[str] = {"APPAREL", "JEWELLERY", "AMBIGUOUS", "UNSUPPORTED"}

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-6-luna",
        timeout_seconds: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key or not model.strip():
            raise ValueError("OpenAI analysis credential and model are required")
        self.api_key = api_key
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def assess(self, person_image: bytes, item_image: bytes) -> VisionAssessment:
        body = self._call(
            schema_name="wearo_preflight",
            schema=PREFLIGHT_SCHEMA,
            prompt=(
                "Analyze exactly two images for a private virtual try-on preflight. Image 1 is "
                "the person profile; image 2 is the uploaded wearable. Count visible people, "
                "check whether one person's full body is visible, flag clearly child-like "
                "subjects, check basic content safety, and classify the primary featured wearable. "
                "For image 2, identify the product the photo is primarily presenting. Ignore the "
                "reference person, mannequin, clothing used only to display jewellery, hands, "
                "props, and background when counting products. Treat an earring pair or matching "
                "jewellery set presented as one product. "
                "APPAREL includes clothing such as shirts, jeans, sarees, dresses, and blouses. "
                "JEWELLERY includes necklaces, chains, earrings, rings, and similar accessories. "
                "Use AMBIGUOUS whenever uncertain and UNSUPPORTED for non-wearable objects."
            ),
            images=(person_image, item_image),
        )
        item_kind = body.get("item_kind")
        if item_kind not in self.item_kinds:
            raise AnalysisServiceError("OpenAI analysis returned an invalid item kind")
        try:
            return VisionAssessment(
                person_count=int(body["person_count"]),
                full_body_visible=body["full_body_visible"] is True,
                suspected_minor=body["suspected_minor"] is True,
                safe_content=body["safe_content"] is True,
                item_kind=item_kind,
                item_count=int(body["item_count"]),
            )
        except (KeyError, TypeError, ValueError):
            raise AnalysisServiceError("OpenAI analysis returned invalid preflight data") from None

    def analyze(self, person: bytes, item: bytes, result: bytes) -> QualitySignals:
        body = self._call(
            schema_name="wearo_render_quality",
            schema=QUALITY_SCHEMA,
            prompt=(
                "Evaluate a virtual try-on result using exactly three images: original person, "
                "original wearable, then generated result. Score identity and product similarity "
                "from 0 to 1. Check color and print preservation, valid human anatomy, content "
                "safety, and whether unsupported visual details were fabricated. Be conservative."
            ),
            images=(person, item, result),
        )
        try:
            identity = float(body["identity_similarity"])
            product = float(body["product_similarity"])
            if not 0 <= identity <= 1 or not 0 <= product <= 1:
                raise ValueError
            return QualitySignals(
                identity_similarity=identity,
                product_similarity=product,
                color_preserved=body["color_preserved"] is True,
                print_preserved=body["print_preserved"] is True,
                anatomy_valid=body["anatomy_valid"] is True,
                safe_content=body["safe_content"] is True,
                fabricated_detail=body["fabricated_detail"] is True,
            )
        except (KeyError, TypeError, ValueError):
            raise AnalysisServiceError("OpenAI analysis returned invalid quality data") from None

    def _call(
        self,
        *,
        schema_name: str,
        schema: dict[str, object],
        prompt: str,
        images: tuple[bytes, ...],
    ) -> dict[str, Any]:
        content: list[dict[str, object]] = [{"type": "input_text", "text": prompt}]
        content.extend(
            {"type": "input_image", "image_url": _image_data_url(image), "detail": "auto"}
            for image in images
        )
        payload: dict[str, object] = {
            "model": self.model,
            "store": False,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": 400,
        }
        json_payload: Any = payload
        try:
            response = self.session.post(
                self.endpoint,
                json=json_payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            raise AnalysisServiceError("OpenAI analysis is unavailable") from None
        if response.status_code != 200:
            raise AnalysisServiceError("OpenAI analysis is unavailable")
        try:
            response_body = response.json()
        except requests.JSONDecodeError:
            raise AnalysisServiceError("OpenAI analysis returned invalid JSON") from None
        if not isinstance(response_body, dict) or response_body.get("status") != "completed":
            raise AnalysisServiceError("OpenAI analysis did not complete")
        for output in response_body.get("output", []):
            if not isinstance(output, dict) or output.get("type") != "message":
                continue
            for part in output.get("content", []):
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise AnalysisServiceError("OpenAI analysis refused the images")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    try:
                        parsed = json.loads(part["text"])
                    except (json.JSONDecodeError, TypeError):
                        raise AnalysisServiceError(
                            "OpenAI analysis returned invalid structured output"
                        ) from None
                    if isinstance(parsed, dict):
                        return parsed
        raise AnalysisServiceError("OpenAI analysis returned no structured output")


class RequestsJsonTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> HttpResponse:
        json_payload: Any = payload
        try:
            response = self.session.post(
                url,
                json=json_payload,
                headers=headers,
                timeout=timeout_seconds,
            )
        except requests.RequestException:
            raise ProviderError("VERTEX_TRANSPORT_ERROR", retryable=True) from None
        try:
            body = response.json()
        except requests.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return HttpResponse(response.status_code, body, dict(response.headers))


class RequestsMultipartTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def post_multipart(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> HttpResponse:
        request_files = [
            (file.field_name, (file.filename, file.content, file.mime_type)) for file in files
        ]
        try:
            response = self.session.post(
                url,
                data=fields,
                files=request_files,
                headers=headers,
                timeout=timeout_seconds,
            )
        except requests.RequestException:
            raise ProviderError("OPENAI_TRANSPORT_ERROR", retryable=True) from None
        try:
            body = response.json()
        except requests.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return HttpResponse(response.status_code, body, dict(response.headers))

    def post_multipart_stream(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
        on_event: Callable[[dict[str, object]], None],
    ) -> HttpResponse:
        request_files = [
            (file.field_name, (file.filename, file.content, file.mime_type)) for file in files
        ]
        try:
            with self.session.post(
                url,
                data=fields,
                files=request_files,
                headers=headers,
                timeout=timeout_seconds,
                stream=True,
            ) as response:
                response_headers = dict(response.headers)
                if response.status_code != 200:
                    return HttpResponse(response.status_code, {}, response_headers)
                data_lines: list[str] = []
                for raw_line in response.iter_lines(decode_unicode=True):
                    line = raw_line.decode() if isinstance(raw_line, bytes) else raw_line
                    if not line:
                        self._dispatch_sse_data(data_lines, on_event)
                        data_lines.clear()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                self._dispatch_sse_data(data_lines, on_event)
                return HttpResponse(response.status_code, {}, response_headers)
        except (requests.RequestException, UnicodeDecodeError):
            raise ProviderError("OPENAI_STREAM_INTERRUPTED", retryable=False) from None

    @staticmethod
    def _dispatch_sse_data(
        data_lines: list[str], on_event: Callable[[dict[str, object]], None]
    ) -> None:
        if not data_lines:
            return
        if len(data_lines) == 1 and data_lines[0] == "[DONE]":
            return
        try:
            event = json.loads("\n".join(data_lines))
        except (json.JSONDecodeError, TypeError):
            raise ProviderError("OPENAI_INVALID_STREAM", retryable=False) from None
        if not isinstance(event, dict):
            raise ProviderError("OPENAI_INVALID_STREAM", retryable=False)
        on_event(event)


class GoogleDefaultAccessTokenProvider:
    def __init__(self, credentials: Credentials | None = None) -> None:
        if credentials is None:
            credentials, _ = google.auth.default(
                scopes=("https://www.googleapis.com/auth/cloud-platform",)
            )
        self.credentials = credentials
        self.request = GoogleAuthRequest()
        self.lock = threading.Lock()

    def token(self) -> str:
        with self.lock:
            expiry = self.credentials.expiry
            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            needs_refresh = (
                not self.credentials.token
                or expiry is None
                or expiry <= datetime.now(UTC) + timedelta(minutes=1)
            )
            if needs_refresh:
                self.credentials.refresh(self.request)  # type: ignore[no-untyped-call]
            token = self.credentials.token
        if not isinstance(token, str) or not token:
            raise ProviderError("VERTEX_AUTH_UNAVAILABLE", retryable=True)
        return token


class HttpAnalysisClient:
    """Provider-neutral boundary for the approved vision and quality analysis service."""

    item_kinds: set[str] = {"APPAREL", "JEWELLERY", "AMBIGUOUS", "UNSUPPORTED"}

    def __init__(
        self,
        endpoint: str,
        *,
        bearer_token: str,
        timeout_seconds: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not endpoint.startswith("https://") or not bearer_token:
            raise ValueError("approved HTTPS analysis endpoint and credential are required")
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def assess(self, person_image: bytes, item_image: bytes) -> VisionAssessment:
        body = self._call("PREFLIGHT", person_image, item_image, None)
        item_kind = body.get("item_kind")
        if item_kind not in self.item_kinds:
            raise AnalysisServiceError("analysis service returned an invalid item kind")
        try:
            return VisionAssessment(
                person_count=int(body["person_count"]),
                full_body_visible=body["full_body_visible"] is True,
                suspected_minor=body["suspected_minor"] is True,
                safe_content=body["safe_content"] is True,
                item_kind=item_kind,
                item_count=int(body["item_count"]),
            )
        except (KeyError, TypeError, ValueError):
            raise AnalysisServiceError(
                "analysis service returned an invalid preflight response"
            ) from None

    def analyze(self, person: bytes, item: bytes, result: bytes) -> QualitySignals:
        body = self._call("QUALITY", person, item, result)
        try:
            identity = float(body["identity_similarity"])
            product = float(body["product_similarity"])
            if not 0 <= identity <= 1 or not 0 <= product <= 1:
                raise ValueError
            return QualitySignals(
                identity_similarity=identity,
                product_similarity=product,
                color_preserved=body["color_preserved"] is True,
                print_preserved=body["print_preserved"] is True,
                anatomy_valid=body["anatomy_valid"] is True,
                safe_content=body["safe_content"] is True,
                fabricated_detail=body["fabricated_detail"] is True,
            )
        except (KeyError, TypeError, ValueError):
            raise AnalysisServiceError(
                "analysis service returned an invalid quality response"
            ) from None

    def _call(
        self,
        stage: str,
        person: bytes,
        item: bytes,
        result: bytes | None,
    ) -> dict[str, Any]:
        images = {
            "person_base64": base64.b64encode(person).decode(),
            "item_base64": base64.b64encode(item).decode(),
        }
        if result is not None:
            images["result_base64"] = base64.b64encode(result).decode()
        try:
            response = self.session.post(
                self.endpoint,
                json={"stage": stage, **images},
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            raise AnalysisServiceError("analysis service is unavailable") from None
        if response.status_code != 200:
            raise AnalysisServiceError("analysis service is unavailable")
        try:
            body = response.json()
        except requests.JSONDecodeError:
            raise AnalysisServiceError("analysis service returned invalid JSON") from None
        if not isinstance(body, dict):
            raise AnalysisServiceError("analysis service returned invalid JSON")
        return body


class ApprovedBetaRouteRegistry:
    def __init__(
        self,
        *,
        enabled: bool,
        provider: str = "GOOGLE_VERTEX",
        model: str | None = None,
        region: str | None = None,
    ) -> None:
        if provider == "GOOGLE_VERTEX":
            self.model = model or "virtual-try-on-001"
            self.region = region or "asia-southeast1"
            if self.model != "virtual-try-on-001" or self.region != "asia-southeast1":
                raise ValueError("approved Vertex model and region are required")
        elif provider == "OPENAI":
            from .render_provider import OPENAI_IMAGE_MODELS

            self.model = model or "gpt-image-2.5-sunburst"
            self.region = region or "global"
            if self.model not in OPENAI_IMAGE_MODELS or self.region != "global":
                raise ValueError("approved OpenAI model and region are required")
        else:
            raise ValueError("approved render provider is required")
        self.enabled = enabled
        self.provider = provider

    def route_for(self, capability: str, at: datetime) -> ModelRoute | None:
        if capability != "APPAREL":
            return None
        return ModelRoute(
            provider=self.provider,
            model=self.model,
            region=self.region,
            capability="APPAREL",
            enabled=self.enabled,
        )
