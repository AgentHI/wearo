from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
import requests

from apps.api.wearo_api.external_runtime import (
    AnalysisServiceError,
    ApprovedBetaRouteRegistry,
    HttpAnalysisClient,
    OpenAIAnalysisClient,
    RequestsJsonTransport,
    RequestsMultipartTransport,
)
from apps.api.wearo_api.render_provider import MultipartFile, ProviderError


def response(status: int, body: dict[str, object]) -> requests.Response:
    item = requests.Response()
    item.status_code = status
    item.headers["x-request-id"] = "request-1"
    item._content = json.dumps(body).encode()
    return item


class Session:
    def __init__(self, responses: list[requests.Response] | None = None) -> None:
        self.responses = responses or []
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> requests.Response:
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


def token() -> str:
    return "-".join(("scoped", "token"))


def test_analysis_client_decodes_preflight_and_quality_signals() -> None:
    session = Session(
        [
            response(
                200,
                {
                    "person_count": 1,
                    "full_body_visible": True,
                    "suspected_minor": False,
                    "safe_content": True,
                    "item_kind": "APPAREL",
                    "item_count": 1,
                },
            ),
            response(
                200,
                {
                    "identity_similarity": 0.97,
                    "product_similarity": 0.96,
                    "color_preserved": True,
                    "print_preserved": True,
                    "anatomy_valid": True,
                    "safe_content": True,
                    "fabricated_detail": False,
                },
            ),
        ]
    )
    client = HttpAnalysisClient(
        "https://analysis.example.test/v1/evaluate",
        bearer_token=token(),
        session=session,  # type: ignore[arg-type]
    )
    preflight = client.assess(b"person", b"item")
    quality = client.analyze(b"person", b"item", b"result")
    assert preflight.item_kind == "APPAREL" and preflight.person_count == 1
    assert quality.identity_similarity == 0.97 and quality.safe_content
    assert session.requests[0]["timeout"] == 30


def test_analysis_client_fails_closed_on_bad_response() -> None:
    session = Session([response(200, {"item_kind": "INVENTED"})])
    client = HttpAnalysisClient(
        "https://analysis.example.test/v1/evaluate",
        bearer_token=token(),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(AnalysisServiceError, match="invalid item kind"):
        client.assess(b"person", b"item")


def structured_response(payload: dict[str, object]) -> requests.Response:
    return response(
        200,
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(payload)}],
                }
            ],
        },
    )


def test_openai_analysis_client_uses_responses_vision_and_structured_output() -> None:
    session = Session(
        [
            structured_response(
                {
                    "person_count": 1,
                    "full_body_visible": True,
                    "suspected_minor": False,
                    "safe_content": True,
                    "item_kind": "APPAREL",
                    "item_count": 1,
                }
            ),
            structured_response(
                {
                    "identity_similarity": 0.98,
                    "product_similarity": 0.95,
                    "color_preserved": True,
                    "print_preserved": True,
                    "anatomy_valid": True,
                    "safe_content": True,
                    "fabricated_detail": False,
                }
            ),
        ]
    )
    client = OpenAIAnalysisClient(api_key="secret", session=session)  # type: ignore[arg-type]

    preflight = client.assess(b"\x89PNG\r\n\x1a\nperson", b"item")
    quality = client.analyze(b"person", b"item", b"result")

    assert preflight.item_kind == "APPAREL"
    assert quality.identity_similarity == 0.98
    request = session.requests[0]
    assert request["url"] == "https://api.openai.com/v1/responses"
    assert request["headers"] == {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }
    payload = request["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-6-luna"
    assert payload["store"] is False
    text = payload["text"]
    assert isinstance(text, dict)
    output_format = text["format"]
    assert isinstance(output_format, dict)
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    inputs = payload["input"]
    assert isinstance(inputs, list)
    first_input = inputs[0]
    assert isinstance(first_input, dict)
    content = first_input["content"]
    assert isinstance(content, list)
    images = [part for part in content if part["type"] == "input_image"]
    assert len(images) == 2
    assert str(images[0]["image_url"]).startswith("data:image/png;base64,")
    assert len(session.requests[1]["json"]["input"][0]["content"]) == 4  # type: ignore[index]


def test_openai_analysis_client_fails_closed_on_provider_or_output_error() -> None:
    unavailable = OpenAIAnalysisClient(
        api_key="secret",
        session=Session([response(429, {"error": {"message": "rate limited"}})]),  # type: ignore[arg-type]
    )
    with pytest.raises(AnalysisServiceError, match="unavailable"):
        unavailable.assess(b"person", b"item")

    invalid = OpenAIAnalysisClient(
        api_key="secret",
        session=Session([structured_response({"item_kind": "INVENTED"})]),  # type: ignore[arg-type]
    )
    with pytest.raises(AnalysisServiceError, match="invalid item kind"):
        invalid.assess(b"person", b"item")


def test_vertex_http_transport_maps_network_failure_to_safe_provider_error() -> None:
    class BrokenSession:
        def post(self, *_: object, **__: object) -> requests.Response:
            raise requests.ConnectionError

    transport = RequestsJsonTransport(BrokenSession())  # type: ignore[arg-type]
    with pytest.raises(ProviderError, match="VERTEX_TRANSPORT_ERROR") as error:
        transport.post_json("https://vertex.example", {}, {}, 120)
    assert error.value.retryable


def test_openai_multipart_transport_maps_request_and_network_failure() -> None:
    session = Session([response(200, {"data": []})])
    transport = RequestsMultipartTransport(session)  # type: ignore[arg-type]
    result = transport.post_multipart(
        "https://api.openai.com/v1/images/edits",
        {"model": "gpt-image-2"},
        [MultipartFile("image[]", "person.png", b"person", "image/png")],
        {"Authorization": "Bearer secret"},
        180,
    )
    assert result.status == 200
    assert session.requests[0]["data"] == {"model": "gpt-image-2"}
    assert session.requests[0]["files"] == [("image[]", ("person.png", b"person", "image/png"))]

    class BrokenSession:
        def post(self, *_: object, **__: object) -> requests.Response:
            raise requests.ConnectionError

    broken = RequestsMultipartTransport(BrokenSession())  # type: ignore[arg-type]
    with pytest.raises(ProviderError, match="OPENAI_TRANSPORT_ERROR") as error:
        broken.post_multipart("https://api.openai.com/v1/images/edits", {}, [], {}, 180)
    assert error.value.retryable


def test_openai_multipart_transport_dispatches_real_sse_events() -> None:
    class StreamingResponse:
        status_code = 200
        headers = {"x-request-id": "stream-request"}

        def __enter__(self) -> StreamingResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def iter_lines(self, *, decode_unicode: bool) -> list[str]:
            assert decode_unicode is True
            partial = base64.b64encode(b"partial").decode()
            final = base64.b64encode(b"final").decode()
            return [
                "event: image_edit.partial_image",
                (
                    'data: {"type":"image_edit.partial_image",'
                    f'"b64_json":"{partial}","partial_image_index":0}}'
                ),
                "",
                "event: image_edit.completed",
                f'data: {{"type":"image_edit.completed","b64_json":"{final}"}}',
                "",
            ]

    class StreamingSession:
        def __init__(self) -> None:
            self.request: dict[str, object] = {}

        def post(self, url: str, **kwargs: object) -> StreamingResponse:
            self.request = {"url": url, **kwargs}
            return StreamingResponse()

    session = StreamingSession()
    events: list[dict[str, object]] = []
    response = RequestsMultipartTransport(session).post_multipart_stream(  # type: ignore[arg-type]
        "https://api.openai.com/v1/images/edits",
        {"stream": "true", "partial_images": "1"},
        [MultipartFile("image[]", "person.png", b"person", "image/png")],
        {"Authorization": "Bearer secret"},
        180,
        events.append,
    )
    assert response.status == 200
    assert session.request["stream"] is True
    assert [event["type"] for event in events] == [
        "image_edit.partial_image",
        "image_edit.completed",
    ]


def test_openai_stream_interruption_is_terminal_to_prevent_duplicate_request() -> None:
    class InterruptedResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> InterruptedResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def iter_lines(self, *, decode_unicode: bool) -> object:
            raise requests.Timeout

    class InterruptedSession:
        def post(self, *_: object, **__: object) -> InterruptedResponse:
            return InterruptedResponse()

    transport = RequestsMultipartTransport(InterruptedSession())  # type: ignore[arg-type]
    with pytest.raises(ProviderError, match="OPENAI_STREAM_INTERRUPTED") as error:
        transport.post_multipart_stream(
            "https://api.openai.com/v1/images/edits",
            {"stream": "true"},
            [],
            {},
            180,
            lambda _: None,
        )
    assert error.value.retryable is False


def test_approved_route_is_apparel_only_and_explicitly_enabled() -> None:
    now = datetime.now(UTC)
    route = ApprovedBetaRouteRegistry(enabled=True).route_for("APPAREL", now)
    assert route is not None and route.model == "virtual-try-on-001" and route.enabled
    assert ApprovedBetaRouteRegistry(enabled=True).route_for("JEWELLERY", now) is None

    openai = ApprovedBetaRouteRegistry(
        enabled=True,
        provider="OPENAI",
        model="gpt-image-2.5-flare",
        region="global",
    ).route_for("APPAREL", now)
    assert openai is not None and openai.provider == "OPENAI"
    assert openai.model == "gpt-image-2.5-flare" and openai.region == "global"

    with pytest.raises(ValueError, match="approved OpenAI model"):
        ApprovedBetaRouteRegistry(enabled=True, provider="OPENAI", model="unsupported")
