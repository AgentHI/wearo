from __future__ import annotations

import base64
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, UnidentifiedImageError


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class RenderRequest:
    person_image: bytes
    item_image: bytes
    person_mime: str
    item_mime: str
    capability: str
    on_partial: Callable[[bytes, str, int], None] | None = None


@dataclass(frozen=True)
class RenderResponse:
    image: bytes
    mime_type: str
    provider: str
    model: str
    region: str
    request_id: str | None
    attempts: int


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, object]
    headers: dict[str, str]


class HttpTransport(Protocol):
    def post_json(
        self, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class MultipartFile:
    field_name: str
    filename: str
    content: bytes
    mime_type: str


class MultipartHttpTransport(Protocol):
    def post_multipart(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> HttpResponse: ...

    def post_multipart_stream(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
        on_event: Callable[[dict[str, object]], None],
    ) -> HttpResponse: ...


class AccessTokenProvider(Protocol):
    def token(self) -> str: ...


class VertexTryOnAdapter:
    provider = "GOOGLE_VERTEX"
    model = "virtual-try-on-001"

    def __init__(
        self,
        transport: HttpTransport,
        tokens: AccessTokenProvider,
        *,
        project_id: str,
        region: str = "asia-southeast1",
        timeout_seconds: int = 120,
    ) -> None:
        if not project_id or region != "asia-southeast1":
            raise ValueError("approved Vertex project and region are required")
        self.transport = transport
        self.tokens = tokens
        self.project_id = project_id
        self.region = region
        self.timeout_seconds = timeout_seconds

    def render(self, request: RenderRequest) -> RenderResponse:
        if request.capability != "APPAREL":
            raise ProviderError("CAPABILITY_UNSUPPORTED", retryable=False)
        person_image, person_mime = self._provider_image(request.person_image, request.person_mime)
        item_image, item_mime = self._provider_image(request.item_image, request.item_mime)
        payload: dict[str, object] = {
            "instances": [
                {
                    "personImage": {
                        "image": {
                            "bytesBase64Encoded": base64.b64encode(person_image).decode(),
                            "mimeType": person_mime,
                        }
                    },
                    "productImages": [
                        {
                            "image": {
                                "bytesBase64Encoded": base64.b64encode(item_image).decode(),
                                "mimeType": item_mime,
                            }
                        }
                    ],
                }
            ],
            "parameters": {"sampleCount": 1},
        }
        url = (
            f"https://{self.region}-aiplatform.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.region}/publishers/google/models/{self.model}:predict"
        )
        for attempt in (1, 2):
            response = self.transport.post_json(
                url,
                payload,
                {
                    "Authorization": f"Bearer {self.tokens.token()}",
                    "Content-Type": "application/json",
                },
                self.timeout_seconds,
            )
            if response.status == 200:
                return self._decode(response, attempt)
            retryable = response.status in {408, 429, 500, 502, 503, 504}
            if not retryable or attempt == 2:
                raise ProviderError(f"VERTEX_HTTP_{response.status}", retryable=retryable)
        raise AssertionError("unreachable")

    @staticmethod
    def _provider_image(content: bytes, mime_type: str) -> tuple[bytes, str]:
        if mime_type in {"image/jpeg", "image/png"}:
            converted, converted_type = content, mime_type
        elif mime_type == "image/webp":
            try:
                with Image.open(io.BytesIO(content)) as image:
                    output = io.BytesIO()
                    image.convert("RGB").save(output, format="PNG", optimize=True)
                    converted = output.getvalue()
                    converted_type = "image/png"
            except (UnidentifiedImageError, OSError, ValueError):
                raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False) from None
        else:
            raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False)
        if not converted or len(converted) > 7 * 1024 * 1024:
            raise ProviderError("PROVIDER_IMAGE_TOO_LARGE", retryable=False)
        return converted, converted_type

    def _decode(self, response: HttpResponse, attempts: int) -> RenderResponse:
        try:
            predictions = response.body["predictions"]
            if not isinstance(predictions, list) or not predictions:
                raise ValueError
            first = predictions[0]
            if not isinstance(first, dict):
                raise ValueError
            encoded = first["bytesBase64Encoded"]
            mime_type = first.get("mimeType", "image/png")
            if not isinstance(encoded, str) or not isinstance(mime_type, str):
                raise ValueError
            image = base64.b64decode(encoded, validate=True)
            if not image or mime_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("VERTEX_INVALID_RESPONSE", retryable=False) from None
        return RenderResponse(
            image,
            str(mime_type),
            self.provider,
            self.model,
            self.region,
            response.headers.get("x-request-id"),
            attempts,
        )


OPENAI_IMAGE_MODELS = frozenset(
    {
        "gpt-image-2.5-sunburst",
        "gpt-image-2.5-sunburst-2026-09-08",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-flare-2026-09-08",
        "gpt-image-2",
        "gpt-image-2-2026-04-21",
    }
)


class OpenAIImageEditAdapter:
    """OpenAI Images API adapter for a person plus wearable reference edit."""

    provider = "OPENAI"
    region = "global"
    endpoint = "https://api.openai.com/v1/images/edits"
    prompt = (
        "Use the first image as the customer and the second image as the wearable reference. "
        "Identify the primary wearable shown in the second image. If the reference is contextual, "
        "isolate only the intended garment or jewellery and ignore any reference person, "
        "mannequin, clothing used only to display jewellery, hands, props, and background. Apply "
        "only the "
        "identified wearable to the correct location on the customer. For apparel, replace only "
        "the relevant clothing; for jewellery, add the item without replacing unrelated clothing. "
        "Preserve the customer's identity, face, hairstyle, body proportions, pose, and "
        "background. Preserve the wearable's color, design, pattern, texture, material details, "
        "and visible logo. Produce a realistic virtual try-on with natural lighting and fitting. "
        "Do not copy unrelated content from the reference image or modify unrelated parts of the "
        "customer image."
    )

    def __init__(
        self,
        transport: MultipartHttpTransport,
        *,
        api_key: str,
        model: str = "gpt-image-2.5-sunburst",
        timeout_seconds: int = 180,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        if model not in OPENAI_IMAGE_MODELS:
            raise ValueError("approved OpenAI image model is required")
        self.transport = transport
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def render(self, request: RenderRequest) -> RenderResponse:
        if request.capability != "APPAREL":
            raise ProviderError("CAPABILITY_UNSUPPORTED", retryable=False)
        person = self._provider_file("person", request.person_image, request.person_mime)
        item = self._provider_file("item", request.item_image, request.item_mime)
        fields = {
            "model": self.model,
            "prompt": self.prompt,
            "n": "1",
            "quality": "high",
            "size": "1024x1536",
            "output_format": "png",
            "stream": "true",
            "partial_images": "1",
        }
        for attempt in (1, 2):
            final_event: dict[str, object] = {}

            def on_event(event: dict[str, object]) -> None:
                nonlocal final_event
                event_type = event.get("type")
                if event_type == "image_edit.partial_image":
                    image = self._event_image(event)
                    index = event.get("partial_image_index")
                    if request.on_partial is not None and isinstance(index, int):
                        request.on_partial(image, "image/png", index)
                elif event_type == "image_edit.completed":
                    final_event = event

            response = self.transport.post_multipart_stream(
                self.endpoint,
                fields,
                [person, item],
                {"Authorization": f"Bearer {self.api_key}"},
                self.timeout_seconds,
                on_event,
            )
            if response.status == 200:
                return self._decode_stream(response, final_event, attempt)
            retryable = response.status in {408, 409, 429, 500, 502, 503, 504}
            if not retryable or attempt == 2:
                raise ProviderError(f"OPENAI_HTTP_{response.status}", retryable=retryable)
        raise AssertionError("unreachable")

    @staticmethod
    def _provider_file(label: str, content: bytes, mime_type: str) -> MultipartFile:
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        extension = extensions.get(mime_type)
        if extension is None or not content:
            raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False)
        if len(content) > 50 * 1024 * 1024:
            raise ProviderError("PROVIDER_IMAGE_TOO_LARGE", retryable=False)
        return MultipartFile("image[]", f"{label}.{extension}", content, mime_type)

    @staticmethod
    def _event_image(event: dict[str, object]) -> bytes:
        try:
            encoded = event["b64_json"]
            if not isinstance(encoded, str):
                raise ValueError
            image = base64.b64decode(encoded, validate=True)
            if not image:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("OPENAI_INVALID_RESPONSE", retryable=False) from None
        return image

    def _decode_stream(
        self, response: HttpResponse, final_event: dict[str, object], attempts: int
    ) -> RenderResponse:
        image = self._event_image(final_event)
        return RenderResponse(
            image,
            "image/png",
            self.provider,
            self.model,
            self.region,
            response.headers.get("x-request-id"),
            attempts,
        )
