from __future__ import annotations

import base64
import io
import logging
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

from .render_quality_strategy import RenderQuality, quality_parameters

logger = logging.getLogger(__name__)


PERSON_PRESERVATION_PROMPT = (
    "PERSON IDENTITY AND ANATOMY LOCK — HIGHEST PRIORITY: treat PERSON IMAGE 1 as a locked "
    "photographic base, never as loose visual inspiration. The output must contain exactly the "
    "same person. Treat the face and head as a protected no-edit region except for the minimum "
    "contact or occlusion pixels strictly required by the target wearable. Preserve the exact "
    "head and face shape, facial geometry, facial landmarks and their spacing, eyes, eyelids, "
    "eyebrows, nose, lips, mouth, teeth, jawline, chin, cheeks, ears, skin tone and natural skin "
    "texture, scars, moles, makeup, hair and hairline, facial hair, and eyewear. Preserve the "
    "exact facial expression, including gaze direction, eye openness, eyebrow position, mouth "
    "openness, "
    "and lip shape, and preserve the apparent age. Do not regenerate, redraw, reinterpret, "
    "beautify, retouch, smooth, or replace the face or head. Preserve the person's exact "
    "anatomical structure and proportions: "
    "height, head-to-body ratio, neck, shoulder width and slope, torso length and width, chest, "
    "waist, abdomen, hips, arms, hands, legs, feet, stance, pose, and camera perspective. Never "
    "make the person wider, narrower, taller, shorter, heavier, thinner, more muscular, or more "
    "curved; never bulge, inflate, compress, reshape, retouch, or beautify any body part. Fit, "
    "drape, or place the target wearable around the unchanged anatomy; only the wearable's outer "
    "silhouette may vary naturally with its construction and material. Change only the target "
    "wearable and its strictly required local occlusion pixels. Keep every non-wearable region, "
    "background, framing, crop, and viewpoint unchanged. "
)

PERSON_PRESERVATION_FINAL_CHECK = (
    "FINAL PERSON CHECK: compare the result directly against PERSON IMAGE 1 and reject any change "
    "to identity, facial features or their spacing, expression, gaze, skin texture, hairline, "
    "eyewear, apparent age, anatomy, body proportions, pose, or camera geometry. The wearable "
    "must adapt to the unchanged person; the person must never be changed to fit the wearable."
)

PERSON_PRESERVATION_NEGATIVE_PROMPT = (
    "different person, changed identity, altered face, face reshaping, changed facial geometry, "
    "changed facial landmarks, changed landmark spacing, changed eyes, changed eyebrows, changed "
    "nose, changed mouth, changed lips, changed teeth, changed jawline, changed ears, altered "
    "expression, changed gaze, changed eye openness, changed mouth openness, beautified face, "
    "retouched face, smoothed skin, plastic skin, changed skin tone, changed skin texture, changed "
    "hair, changed hairline, changed facial hair, changed eyewear, changed age, changed body, body "
    "reshaping, changed body proportions, widened body, widened torso, enlarged torso, bulging "
    "body, bloated body, inflated body, compressed body, weight gain, weight loss, changed "
    "shoulder width, changed height, changed pose, changed stance, changed camera angle, changed "
    "framing"
)

APPAREL_ACCESSORY_PRESERVATION_PROMPT = (
    "APPAREL-ONLY NON-GARMENT OBJECT LOCK: clothing is the only permitted change. Preserve the "
    "exact visible object inventory and styling state from PERSON IMAGE 1. Keep the head, face, "
    "ears, neck, wrists, hands, and every uncovered body region exactly as shown in IMAGE 1. Do "
    "not introduce any new object, adornment, decoration, accessory, or styling element. Do not "
    "remove, replace, move, resize, or redesign any existing non-garment object. Treat IMAGE 2 "
    "only as a garment-design reference; ignore and never transfer its person, mannequin, body, "
    "styling, props, background, or any non-garment object. Change only the target clothing and "
    "its physically necessary boundary and occlusion pixels."
)

APPAREL_ACCESSORY_NEGATIVE_PROMPT = (
    "new earrings, added earrings, invented earrings, transferred earrings, extra earrings, "
    "new jewellery, added jewellery, invented jewellery, transferred jewellery, new necklace, "
    "added necklace, new chain, added chain, new pendant, added pendant, new bracelet, added "
    "bracelet, new watch, added watch, new ring, added ring, new eyewear, added glasses, new "
    "headwear, added accessories, styling accessories copied from product image"
)

APPAREL_TRYON_PROMPT = (
    "APPAREL TRY-ON — CATEGORY IS FIXED AS CLOTHING. Use exactly two images. IMAGE 1 is the "
    "immutable person photograph and fixed output canvas. IMAGE 2 supplies only the target "
    "garment's design. Extract exactly one garment from IMAGE 2 and discard every other visual "
    "element from that reference. Replace only the corresponding clothing region in IMAGE 1; "
    "modify only pixels necessary for the wearable plus the minimum boundary and occlusion pixels "
    "needed for a realistic fit. Do not edit the face or recreate the body. Keep IMAGE 1's exact "
    "person, expression, body structure, pose, hands, uncovered skin, existing non-garment "
    "objects, background, lighting, camera angle, original composition and aspect ratio unchanged. "
    "Fit the garment around the unchanged body with natural folds, drape, contact shadows, and "
    "occlusion; never reshape the body to fit the garment. IMAGE 2 is the authoritative product "
    "appearance. "
    "Preserve its exact garment type and construction, colour and colour placement, fabric, weave, "
    "knit, grain, texture, thickness, opacity, sheen, pattern scale, print, embroidery, stitching, "
    "seams, hems, buttons, pockets, neckline, sleeves, distressing, wash, branding, and visible "
    "logo. Do not recolour, redesign, simplify, embellish, duplicate, omit, or invent product "
    "details. Applicable garments include a shirt, T-shirt, dress, saree, blouse, trousers, jeans, "
    "skirt, jacket, and other clothing. Return one photorealistic edited IMAGE 1 with no "
    "additional people, objects, text, watermark, collage, or product-display layout. PRIORITY "
    "ORDER: exact person identity first, exact product appearance second, realistic wearable fit "
    "third."
)


def person_preserving_prompt(prompt: str) -> str:
    """Wrap a try-on prompt with an idempotent identity and anatomy lock."""
    cleaned = prompt.strip()
    if PERSON_PRESERVATION_PROMPT in cleaned:
        return cleaned
    return f"{PERSON_PRESERVATION_PROMPT}{cleaned} {PERSON_PRESERVATION_FINAL_CHECK}"


def person_preserving_negative_prompt(prompt: str | None) -> str:
    """Add person-mutation exclusions without replacing provider-specific exclusions."""
    cleaned = (prompt or "").strip()
    if PERSON_PRESERVATION_NEGATIVE_PROMPT in cleaned:
        return cleaned
    return (
        f"{PERSON_PRESERVATION_NEGATIVE_PROMPT}, {cleaned}"
        if cleaned
        else PERSON_PRESERVATION_NEGATIVE_PROMPT
    )


def apparel_accessory_preserving_prompt(prompt: str) -> str:
    """For apparel edits, preserve the person's exact pre-existing accessory inventory."""
    cleaned = prompt.strip()
    if APPAREL_ACCESSORY_PRESERVATION_PROMPT in cleaned:
        return cleaned
    return f"{cleaned} {APPAREL_ACCESSORY_PRESERVATION_PROMPT}"


def apparel_accessory_negative_prompt(prompt: str | None) -> str:
    """Forbid newly invented accessories while retaining provider-specific exclusions."""
    cleaned = (prompt or "").strip()
    if APPAREL_ACCESSORY_NEGATIVE_PROMPT in cleaned:
        return cleaned
    return (
        f"{APPAREL_ACCESSORY_NEGATIVE_PROMPT}, {cleaned}"
        if cleaned
        else APPAREL_ACCESSORY_NEGATIVE_PROMPT
    )


def runware_aspect_dimensions(
    person_image: bytes,
    *,
    target_dimension: int,
) -> dict[str, int]:
    """Preserve the person's aspect ratio within Runware's FLUX-safe dimension limits."""
    if target_dimension <= 0:
        raise ValueError("target dimension must be positive")
    try:
        with Image.open(io.BytesIO(person_image)) as source:
            oriented = ImageOps.exif_transpose(source)
            source_width, source_height = oriented.size
    except (OSError, UnidentifiedImageError):
        raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False) from None
    if source_width <= 0 or source_height <= 0:  # pragma: no cover - Pillow guarantees this.
        raise ProviderError("PROVIDER_IMAGE_INVALID", retryable=False)

    target_area = target_dimension * target_dimension
    scale = math.sqrt(target_area / (source_width * source_height))
    width = source_width * scale
    height = source_height * scale

    maximum_edge = 2048
    minimum_edge = 128
    multiple = 64
    if max(width, height) > maximum_edge:
        downscale = maximum_edge / max(width, height)
        width *= downscale
        height *= downscale
    if min(width, height) < minimum_edge:
        upscale = minimum_edge / min(width, height)
        if max(width, height) * upscale <= maximum_edge:
            width *= upscale
            height *= upscale

    def safe_edge(value: float) -> int:
        rounded = round(value / multiple) * multiple
        return min(max(rounded, minimum_edge), maximum_edge)

    return {"width": safe_edge(width), "height": safe_edge(height)}


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
    product_kind: str | None = None


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
    prompt = apparel_accessory_preserving_prompt(
        person_preserving_prompt(APPAREL_TRYON_PROMPT)
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
