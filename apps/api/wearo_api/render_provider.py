from __future__ import annotations

import base64
import io
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, UnidentifiedImageError

from .render_quality_strategy import RenderQuality, quality_parameters

logger = logging.getLogger(__name__)


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
    quality: RenderQuality = RenderQuality.HIGH
    job_id: str | None = None


@dataclass(frozen=True)
class RenderResponse:
    image: bytes
    mime_type: str
    provider: str
    model: str
    region: str
    request_id: str | None
    attempts: int
    usage: dict[str, object] | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, object]
    headers: dict[str, str]
    response_headers_ms: int | None = None
    total_ms: int | None = None


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
        timeout_seconds: int | tuple[int, int],
    ) -> HttpResponse: ...

    def post_multipart_stream(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int | tuple[int, int],
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
            "parameters": {
                "sampleCount": 1,
                **quality_parameters(self.provider, self.model, request.quality),
            },
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
        "Perform a photorealistic virtual try-on using exactly two images. IMAGE 1 (PERSON) is the "
        "original person photo and fixed output canvas. IMAGE 2 (PRODUCT) is the exact wearable to "
        "apply. Replace or add ONLY the target wearable in IMAGE 1 using the product from IMAGE 2. "
        "STRICT PRESERVATION — PERSON: keep the exact original face, identity, hair, skin tone, "
        "expression, glasses, facial hair, body shape, pose, hands, accessories, background, "
        "lighting, framing, composition, and aspect ratio. Never regenerate, beautify, or retouch "
        "the face. PRODUCT: preserve the exact colour, fabric texture, material, prints, "
        "patterns, embroidery, logos, stitching, neckline, sleeves, construction, and design. "
        "Never recolour, "
        "redesign, simplify, or invent details. EDIT REGION: modify only pixels necessary for the "
        "wearable and preserve every unaffected area of IMAGE 1. FIT AND REALISM: fit the wearable "
        "naturally to the existing body and pose with realistic folds, draping, shadows, and "
        "occlusion while keeping product colours and details faithful to IMAGE 2. OUTPUT: return "
        "one photorealistic image with IMAGE 1's original composition and aspect ratio, with no "
        "additional people, text, or watermarks. PRIORITY ORDER: exact person identity first, "
        "exact "
        "product appearance second, realistic wearable fit third. Never regenerate the entire "
        "person or scene. "
        "IMAGE 1 IS THE IMMUTABLE BASE PHOTO AND THE EXACT CUSTOMER TO EDIT. Perform a localized "
        "image edit on Image 1; do not generate, recreate, redraw, reinterpret, beautify, or "
        "replace the person or the photograph. Image 2 is only the wearable reference. The final "
        "image must remain the same photograph of the same person, with only the pixels required "
        "to apply the selected wearable changed. Preserve the customer's face exactly and "
        "pixel-faithfully: keep the same facial identity, facial geometry, eyes, eyebrows, nose, "
        "mouth, teeth, ears, skin texture, skin tone, expression, gaze, makeup, facial hair, and "
        "all distinguishing features. Never synthesize a new face, retouch the face, improve the "
        "face, change apparent age or gender, or copy a face from Image 2. Preserve the original "
        "head, hair, hairline, neck, body shape, body proportions, pose, hands, fingers, legs, "
        "feet, camera angle, crop, resolution, lighting, shadows, background, and every unrelated "
        "object. Do not change the person's posture or camera framing to make the wearable fit. "
        "Pixels outside the anatomically necessary wearable and occlusion region should remain "
        "unchanged from Image 1. "
        "Identify the primary wearable shown in the second image. If the reference is contextual, "
        "isolate only the intended garment or jewellery and ignore any reference person, "
        "mannequin, clothing used only to display jewellery, hands, props, and background. Apply "
        "only the "
        "identified wearable to the correct location on the customer. For a dress, saree, blouse, "
        "shirt, T-shirt, trousers, jeans, or other apparel, edit only the existing clothing region "
        "and the minimum boundary pixels required for realistic fit and occlusion; do not edit the "
        "face or recreate the body. For jewellery, add only the jewellery at its correct body "
        "location without replacing the person, face, hair, body, or unrelated clothing. "
        "For any jewellery, first classify the exact jewellery type and intended wearing "
        "configuration from the reference, including whether it is a single item, matching pair, "
        "or coordinated set. Place each component only on its anatomically correct location at a "
        "realistic scale and orientation: earrings on the corresponding earlobes, nose jewellery "
        "on the correct nostril or septum, maang tikka and head jewellery at the hairline and "
        "forehead, necklaces around the neck and collarbone, brooches on the intended garment "
        "area, armlets on the upper arm, bangles and bracelets around the wrists, rings on the "
        "appropriate fingers, waist belts or chains around the waist, and anklets around the "
        "ankles. Preserve the reference's exact item count and wearing arrangement; do not turn a "
        "single item into a pair, merge a pair into one item, or split, combine, or relocate set "
        "components. Respect occlusion and perspective so jewellery sits on the body rather than "
        "floating, embedding into skin, or hanging from the wrong body part. "
        "When the wearable is a necklace, first infer its exact necklace type, original length, "
        "silhouette, width, curvature, chain-to-ornament ratio, pendant position, and intended "
        "wearing height from the reference. Fit that same necklace closely and naturally around "
        "the customer's neck, following the neck and collarbone perspective. A short necklace, "
        "choker, collar necklace, or collarbone necklace must remain short and must not be "
        "converted into a long chain or lowered onto the mid-chest. For earrings, preserve "
        "whether they are studs, hoops, drops, jhumkas, chandbalis, ear cuffs, or another design "
        "and retain their original drop length and orientation. For bangles, bracelets, rings, "
        "armlets, waist "
        "jewellery, and anklets, preserve the original circumference, width, stacking order, and "
        "body placement. Preserve the exact number, order, spacing, shape, and relative size of "
        "links, motifs, stones, beads, drops, clasps, chains, and pendants across every jewellery "
        "type. Preserve the exact metal color, stone colors, enamel colors, color placement, "
        "symmetry, proportions, and construction. Do not redesign, simplify, embellish, extend, "
        "duplicate, remove, recolor, or invent any jewellery component. Scale and curve only as "
        "needed for anatomically realistic contact with the customer's neck. "
        "Treat Image 2 as the authoritative product appearance and preserve it exactly. Lock the "
        "wearable's original colour and colour placement, including hue, saturation, brightness, "
        "contrast, undertone, gradients, panels, borders, and every printed or embroidered colour. "
        "Do not recolour, colour-match to the person, apply a stylistic colour grade, brighten, "
        "darken, fade, wash out, or replace any product colour. Preserve the exact fabric and "
        "material identity, weave, knit, grain, texture, thickness, opacity, sheen, finish, drape, "
        "pattern scale, print, embroidery, stitching, seams, hems, buttons, pockets, neckline, "
        "sleeves, distressing, wash, branding, and visible logo. Do not substitute a similar "
        "fabric or simplify small product details. Only geometrically warp, fold, scale, and "
        "occlude the original product appearance as strictly necessary to fit the unchanged "
        "person. Lighting adaptation may add physically plausible local highlights and shadows, "
        "but the product's perceived base colour and material must remain the same as Image 2. "
        "Produce a realistic virtual try-on with natural lighting and fitting. "
        "Do not copy unrelated content from the reference image or modify unrelated parts of the "
        "customer image. Before returning the result, verify that the face and all non-wearable "
        "regions still match Image 1 exactly. Return only the edited customer photo."
    )

    def __init__(
        self,
        transport: MultipartHttpTransport,
        *,
        api_key: str,
        model: str = "gpt-image-2.5-sunburst",
        streaming: bool = False,
        connect_timeout_seconds: int = 15,
        read_timeout_seconds: int = 180,
        max_attempts: int = 3,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        if model not in OPENAI_IMAGE_MODELS:
            raise ValueError("approved OpenAI image model is required")
        self.transport = transport
        self.api_key = api_key
        self.model = model
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("OpenAI image timeouts must be positive")
        if not 1 <= max_attempts <= 3:
            raise ValueError("OpenAI image max attempts must be between 1 and 3")
        self.streaming = streaming
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.max_attempts = max_attempts

    def render(self, request: RenderRequest) -> RenderResponse:
        if request.capability != "APPAREL":
            raise ProviderError("CAPABILITY_UNSUPPORTED", retryable=False)
        person = self._provider_file("person", request.person_image, request.person_mime)
        item = self._provider_file("item", request.item_image, request.item_mime)
        fields = {
            "model": self.model,
            "prompt": self.prompt,
            "n": "1",
            "output_format": "png",
            **{
                key: str(value)
                for key, value in quality_parameters(
                    self.provider, self.model, request.quality
                ).items()
            },
        }
        if self.streaming:
            fields.update({"stream": "true", "partial_images": "1"})
        timeout = (self.connect_timeout_seconds, self.read_timeout_seconds)
        for attempt in range(1, self.max_attempts + 1):
            final_event: dict[str, object] = {}
            started_at = time.monotonic()

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

            logger.info(
                "OpenAI image edit started job_id=%s provider=%s model=%s streaming=%s "
                "attempt=%d started_at=%s",
                request.job_id,
                self.provider,
                self.model,
                self.streaming,
                attempt,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            try:
                if self.streaming:
                    response = self.transport.post_multipart_stream(
                        self.endpoint,
                        fields,
                        [person, item],
                        {"Authorization": f"Bearer {self.api_key}"},
                        timeout,
                        on_event,
                    )
                else:
                    response = self.transport.post_multipart(
                        self.endpoint,
                        fields,
                        [person, item],
                        {"Authorization": f"Bearer {self.api_key}"},
                        timeout,
                    )
            except ProviderError as error:
                elapsed_ms = round((time.monotonic() - started_at) * 1000)
                logger.warning(
                    "OpenAI image edit transport failed job_id=%s provider=%s model=%s "
                    "streaming=%s attempt=%d timeout_category=%s exception=%s "
                    "final_status=%s total_ms=%d",
                    request.job_id,
                    self.provider,
                    self.model,
                    self.streaming,
                    attempt,
                    error.code,
                    type(error).__name__,
                    "retrying" if error.retryable and attempt < self.max_attempts else "failed",
                    elapsed_ms,
                )
                if not error.retryable or attempt == self.max_attempts:
                    raise
                self._backoff(attempt)
                continue
            if response.status == 200:
                logger.info(
                    "OpenAI image edit completed model=%s status=%d request_id=%s "
                    "streaming=%s attempt=%d response_headers_ms=%s total_ms=%d "
                    "final_status=completed",
                    self.model,
                    response.status,
                    response.headers.get("x-request-id"),
                    self.streaming,
                    attempt,
                    response.response_headers_ms,
                    round((time.monotonic() - started_at) * 1000),
                )
                return (
                    self._decode_stream(response, final_event, attempt)
                    if self.streaming
                    else self._decode_response(response, attempt)
                )
            retryable = response.status in {408, 409, 429, 500, 502, 503, 504}
            raw_error = response.body.get("error")
            error_type = raw_error.get("type") if isinstance(raw_error, dict) else None
            error_code = raw_error.get("code") if isinstance(raw_error, dict) else None
            logger.warning(
                "OpenAI image edit failed model=%s status=%d request_id=%s "
                "error_type=%s error_code=%s retryable=%s attempt=%d streaming=%s "
                "response_headers_ms=%s total_ms=%d final_status=%s",
                self.model,
                response.status,
                response.headers.get("x-request-id"),
                error_type,
                error_code,
                retryable,
                attempt,
                self.streaming,
                response.response_headers_ms,
                round((time.monotonic() - started_at) * 1000),
                "retrying" if retryable and attempt < self.max_attempts else "failed",
            )
            if not retryable or attempt == self.max_attempts:
                raise ProviderError(f"OPENAI_HTTP_{response.status}", retryable=retryable)
            self._backoff(attempt)
        raise AssertionError("unreachable")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep((0.5 * (2 ** (attempt - 1))) + (secrets.randbelow(251) / 1000))

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
        raw_usage = final_event.get("usage")
        usage = dict(raw_usage) if isinstance(raw_usage, dict) else None
        return RenderResponse(
            image,
            "image/png",
            self.provider,
            self.model,
            self.region,
            response.headers.get("x-request-id"),
            attempts,
            usage,
        )

    def _decode_response(self, response: HttpResponse, attempts: int) -> RenderResponse:
        data = response.body.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ProviderError("OPENAI_INVALID_RESPONSE", retryable=False)
        image = self._event_image(data[0])
        raw_usage = response.body.get("usage")
        usage = dict(raw_usage) if isinstance(raw_usage, dict) else None
        return RenderResponse(
            image,
            "image/png",
            self.provider,
            self.model,
            self.region,
            response.headers.get("x-request-id"),
            attempts,
            usage,
        )


class BytePlusImageGenerationAdapter:
    """BytePlus ModelArk image generation adapter using two reference images."""

    provider = "BYTEPLUS"
    region = "ap-southeast-1"
    endpoint = "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
    prompt = OpenAIImageEditAdapter.prompt

    def __init__(
        self,
        transport: HttpTransport,
        *,
        api_key: str,
        model: str,
        region: str = "ap-southeast-1",
        timeout_seconds: int = 180,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("BytePlus API key and image model are required")
        if region != self.region:
            raise ValueError("approved BytePlus region is required")
        self.transport = transport
        self.api_key = api_key
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds

    def render(self, request: RenderRequest) -> RenderResponse:
        if request.capability != "APPAREL":
            raise ProviderError("CAPABILITY_UNSUPPORTED", retryable=False)
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": self.prompt,
            "image": [
                self._data_url(request.person_image, request.person_mime),
                self._data_url(request.item_image, request.item_mime),
            ],
            "response_format": "b64_json",
            "watermark": False,
            **quality_parameters(self.provider, self.model, request.quality),
        }
        if self.model.startswith("dola-seedream-5-0-flash-"):
            payload["prompt"] = (
                f"{self.prompt.rstrip()} Output a portrait image with a 2:3 aspect ratio."
            )
        else:
            payload["sequential_image_generation"] = "disabled"
        for attempt in (1, 2):
            response = self.transport.post_json(
                self.endpoint,
                payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                self.timeout_seconds,
            )
            if response.status == 200:
                return self._decode(response, attempt)
            retryable = response.status in {408, 409, 429, 500, 502, 503, 504}
            if not retryable or attempt == 2:
                raise ProviderError(f"BYTEPLUS_HTTP_{response.status}", retryable=retryable)
        raise AssertionError("unreachable")

    @staticmethod
    def _data_url(content: bytes, mime_type: str) -> str:
        if not content or mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False)
        if len(content) > 10 * 1024 * 1024:
            raise ProviderError("PROVIDER_IMAGE_TOO_LARGE", retryable=False)
        return f"data:{mime_type};base64,{base64.b64encode(content).decode()}"

    def _decode(self, response: HttpResponse, attempts: int) -> RenderResponse:
        try:
            data = response.body["data"]
            if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                raise ValueError
            encoded = data[0]["b64_json"]
            if not isinstance(encoded, str):
                raise ValueError
            image = base64.b64decode(encoded, validate=True)
            if not image:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ProviderError("BYTEPLUS_INVALID_RESPONSE", retryable=False) from None
        raw_usage = response.body.get("usage")
        usage = dict(raw_usage) if isinstance(raw_usage, dict) else None
        mime_type = "image/png" if image.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        return RenderResponse(
            image,
            mime_type,
            self.provider,
            self.model,
            self.region,
            response.headers.get("x-request-id") or response.headers.get("x-tt-logid"),
            attempts,
            usage,
        )
