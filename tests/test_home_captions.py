from __future__ import annotations

import json
from typing import Any, cast

import requests

from apps.api.wearo_api.home_captions import FALLBACK_CAPTIONS, HomeCaptionService


def response(captions: list[str]) -> requests.Response:
    item = requests.Response()
    item.status_code = 200
    item._content = json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"captions": captions}),
                        }
                    ],
                }
            ]
        }
    ).encode()
    return item


class Session:
    def __init__(self, result: requests.Response) -> None:
        self.result = result
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> requests.Response:
        self.requests.append({"url": url, **kwargs})
        return self.result


def caption_library() -> list[str]:
    openings = [
        "Radiant",
        "Elegant",
        "Confident",
        "Limitless",
        "Graceful",
        "Inspired",
        "Fearless",
        "Authentic",
        "Timeless",
        "Brilliant",
    ]
    endings = [
        "Confidence",
        "Elegance",
        "Style",
        "Presence",
        "Energy",
        "Expression",
        "Spirit",
        "Charm",
        "Poise",
        "Glow",
    ]
    return [f"{opening} {ending}" for opening in openings for ending in endings]


def test_openai_caption_library_is_generated_only_once_and_cached() -> None:
    session = Session(response(caption_library()))
    service = HomeCaptionService(
        "secret-key",
        "gpt-5-mini",
        session=session,  # type: ignore[arg-type]
    )

    first = service.random_caption()
    second = service.random_caption()

    assert service.library_size == 100
    assert first in caption_library()
    assert second in caption_library()
    assert first != second
    assert len(session.requests) == 1
    request = session.requests[0]
    assert request["url"] == "https://api.openai.com/v1/responses"
    assert request["headers"] == {"Authorization": "Bearer secret-key"}
    body = cast(dict[str, Any], request["json"])
    assert body["store"] is False
    assert body["text"]["format"]["schema"]["properties"]["captions"]["minItems"] == 100
    assert body["text"]["format"]["schema"]["properties"]["captions"]["maxItems"] == 100


def test_missing_openai_configuration_uses_cached_fallbacks() -> None:
    session = Session(response([]))
    service = HomeCaptionService(
        "",
        "gpt-5-mini",
        session=session,  # type: ignore[arg-type]
    )

    first = service.random_caption()
    second = service.random_caption()

    assert service.library_size == len(FALLBACK_CAPTIONS)
    assert first in FALLBACK_CAPTIONS
    assert second in FALLBACK_CAPTIONS
    assert first != second
    assert session.requests == []
