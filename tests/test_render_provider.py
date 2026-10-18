import base64
from collections.abc import Callable

import pytest

from apps.api.wearo_api.render_provider import (
    HttpResponse,
    MultipartFile,
    OpenAIImageEditAdapter,
    ProviderError,
    RenderRequest,
    VertexTryOnAdapter,
)


class Tokens:
    def token(self) -> str:
        return "access-token"


class Transport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object], dict[str, str], int]] = []

    def post_json(
        self, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int
    ) -> HttpResponse:
        self.calls.append((url, payload, headers, timeout_seconds))
        return self.responses.pop(0)


class MultipartTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], list[MultipartFile], dict[str, str], int]] = []

    def post_multipart(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> HttpResponse:
        self.calls.append((url, fields, files, headers, timeout_seconds))
        return self.responses.pop(0)

    def post_multipart_stream(
        self,
        url: str,
        fields: dict[str, str],
        files: list[MultipartFile],
        headers: dict[str, str],
        timeout_seconds: int,
        on_event: Callable[[dict[str, object]], None],
    ) -> HttpResponse:
        response = self.post_multipart(url, fields, files, headers, timeout_seconds)
        if response.status == 200:
            data = response.body.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                on_event(
                    {
                        "type": "image_edit.partial_image",
                        "b64_json": data[0]["b64_json"],
                        "partial_image_index": 0,
                    }
                )
                on_event({"type": "image_edit.completed", "b64_json": data[0]["b64_json"]})
        return response


def request(capability: str = "APPAREL") -> RenderRequest:
    return RenderRequest(b"person", b"item", "image/jpeg", "image/png", capability)


def success() -> HttpResponse:
    return HttpResponse(
        200,
        {
            "predictions": [
                {
                    "bytesBase64Encoded": base64.b64encode(b"result").decode(),
                    "mimeType": "image/png",
                }
            ]
        },
        {"x-request-id": "provider-1"},
    )


def test_vertex_request_uses_approved_model_region_timeout_and_provenance() -> None:
    transport = Transport([success()])
    adapter = VertexTryOnAdapter(transport, Tokens(), project_id="wearo-beta")
    result = adapter.render(request())
    url, payload, headers, timeout = transport.calls[0]
    assert "asia-southeast1" in url and "virtual-try-on-001:predict" in url
    assert timeout == 120 and headers["Authorization"] == "Bearer access-token"
    assert "cGVyc29u" in str(payload)
    assert result.request_id == "provider-1" and result.image == b"result"


def test_one_transient_retry_is_same_adapter_call() -> None:
    transport = Transport([HttpResponse(503, {}, {}), success()])
    result = VertexTryOnAdapter(transport, Tokens(), project_id="wearo-beta").render(request())
    assert result.attempts == 2 and len(transport.calls) == 2


def test_permanent_failure_invalid_response_and_jewellery_fail_closed() -> None:
    for response, code in (
        (HttpResponse(400, {}, {}), "VERTEX_HTTP_400"),
        (HttpResponse(200, {}, {}), "VERTEX_INVALID_RESPONSE"),
    ):
        with pytest.raises(ProviderError) as error:
            VertexTryOnAdapter(Transport([response]), Tokens(), project_id="wearo-beta").render(
                request()
            )
        assert error.value.code == code
    with pytest.raises(ProviderError, match="CAPABILITY_UNSUPPORTED"):
        VertexTryOnAdapter(Transport([]), Tokens(), project_id="wearo-beta").render(
            request("JEWELLERY")
        )


def openai_success() -> HttpResponse:
    return HttpResponse(
        200,
        {"data": [{"b64_json": base64.b64encode(b"openai-result").decode()}]},
        {"x-request-id": "openai-request-1"},
    )


def test_openai_request_uses_two_references_and_records_provenance() -> None:
    transport = MultipartTransport([openai_success()])
    adapter = OpenAIImageEditAdapter(transport, api_key="secret-key")
    partials: list[tuple[bytes, str, int]] = []
    original = request()
    result = adapter.render(
        RenderRequest(
            original.person_image,
            original.item_image,
            original.person_mime,
            original.item_mime,
            original.capability,
            on_partial=lambda image, mime, index: partials.append((image, mime, index)),
        )
    )

    url, fields, files, headers, timeout = transport.calls[0]
    assert url == "https://api.openai.com/v1/images/edits"
    assert fields["model"] == "gpt-image-2.5-sunburst"
    assert fields["quality"] == "high" and fields["size"] == "1024x1536"
    assert fields["stream"] == "true" and fields["partial_images"] == "1"
    assert fields["prompt"] == (
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
    assert [file.field_name for file in files] == ["image[]", "image[]"]
    assert [file.filename for file in files] == ["person.jpg", "item.png"]
    assert headers == {"Authorization": "Bearer secret-key"} and timeout == 180
    assert result.image == b"openai-result"
    assert result.provider == "OPENAI" and result.region == "global"
    assert result.request_id == "openai-request-1" and result.attempts == 1
    assert partials == [(b"openai-result", "image/png", 0)]
    assert [file.filename for file in files] == ["person.jpg", "item.png"]


def test_openai_retries_transient_status_and_fails_closed() -> None:
    transport = MultipartTransport([HttpResponse(429, {}, {}), openai_success()])
    result = OpenAIImageEditAdapter(
        transport,
        api_key="secret-key",
        model="gpt-image-2",
    ).render(request())
    assert result.attempts == 2 and len(transport.calls) == 2

    for response, code in (
        (HttpResponse(401, {}, {}), "OPENAI_HTTP_401"),
        (HttpResponse(200, {}, {}), "OPENAI_INVALID_RESPONSE"),
    ):
        with pytest.raises(ProviderError) as error:
            OpenAIImageEditAdapter(MultipartTransport([response]), api_key="secret-key").render(
                request()
            )
        assert error.value.code == code

    with pytest.raises(ProviderError, match="CAPABILITY_UNSUPPORTED"):
        OpenAIImageEditAdapter(MultipartTransport([]), api_key="secret-key").render(
            request("JEWELLERY")
        )


def test_openai_rejects_unknown_models_and_invalid_images() -> None:
    with pytest.raises(ValueError, match="approved OpenAI image model"):
        OpenAIImageEditAdapter(
            MultipartTransport([]), api_key="secret-key", model="chatgpt-image-latest"
        )
    with pytest.raises(ProviderError, match="PROVIDER_IMAGE_INVALID"):
        OpenAIImageEditAdapter(MultipartTransport([]), api_key="secret-key").render(
            RenderRequest(b"person", b"item", "image/gif", "image/png", "APPAREL")
        )
