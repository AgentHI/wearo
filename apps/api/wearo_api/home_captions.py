from __future__ import annotations

import json
import logging
import re
import secrets
import threading
from typing import Any

import requests

logger = logging.getLogger(__name__)

FALLBACK_CAPTIONS = (
    "Wear Confidence",
    "Radiate Elegance",
    "Own Beauty",
    "Feel Remarkable",
    "Look Limitless",
    "Glow Confidently",
    "Styled Boldly",
    "Beautifully You",
    "Confidence Shines",
    "Elegance Awaits",
    "Unapologetically You",
    "Own Today",
    "Shine Naturally",
    "Feel Fabulous",
    "Look Radiant",
    "Embrace Elegance",
    "Choose Confidence",
    "Boldly Beautiful",
    "Gracefully Confident",
    "Simply Stunning",
    "Endlessly Elegant",
    "Naturally Radiant",
    "Confidently You",
)

_TWO_WORD_CAPTION = re.compile(r"[A-Za-z][A-Za-z'’-]{0,23} [A-Za-z][A-Za-z'’-]{0,23}")


class HomeCaptionService:
    """Generate one caption library, then serve random captions from memory."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: int = 25,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self._captions: tuple[str, ...] = ()
        self._last_caption: str | None = None
        self._lock = threading.Lock()

    @property
    def library_size(self) -> int:
        return len(self._captions)

    def random_caption(self) -> str:
        with self._lock:
            if not self._captions:
                self._captions = self._load_library()
            choices = tuple(caption for caption in self._captions if caption != self._last_caption)
            caption = secrets.choice(choices or self._captions)
            self._last_caption = caption
            return caption

    def _load_library(self) -> tuple[str, ...]:
        if not self.api_key or not self.model:
            return FALLBACK_CAPTIONS
        try:
            captions = self._generate_library()
        except (KeyError, StopIteration, TypeError, ValueError, requests.RequestException) as error:
            status_code = (
                error.response.status_code
                if isinstance(error, requests.HTTPError) and error.response is not None
                else None
            )
            logger.warning(
                "OpenAI home-caption generation failed; using curated fallbacks "
                "error_type=%s status_code=%s",
                type(error).__name__,
                status_code,
            )
            return FALLBACK_CAPTIONS
        if len(captions) != 100 or len(set(captions)) != 100:
            logger.warning("OpenAI home-caption library was invalid; using curated fallbacks")
            return FALLBACK_CAPTIONS
        return captions

    def _generate_library(self) -> tuple[str, ...]:
        response = self.session.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "store": False,
                "instructions": (
                    "You write refined microcopy for Wearo.ai, a fashion virtual try-on app. "
                    "Generate exactly 100 unique captions about looking good, personal style, "
                    "self-expression, elegance, and confidence. Every caption must contain "
                    "exactly two words, use positive inclusive language, and be suitable as a "
                    "short home-page greeting. Avoid punctuation, emojis, body-shaming, gendered "
                    "language, promises, and the words morning, Wearo, AI, perfect, flawless, "
                    "skinny, and beautiful body. Use title case."
                ),
                "input": "Create the 100-caption library now and return only the schema output.",
                "max_output_tokens": 1600,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "wearo_home_captions",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "captions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 100,
                                    "maxItems": 100,
                                }
                            },
                            "required": ["captions"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        output_text = next(
            part["text"]
            for item in data["output"]
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        generated = json.loads(output_text)["captions"]
        captions = tuple(str(value).strip() for value in generated)
        if any(_TWO_WORD_CAPTION.fullmatch(caption) is None for caption in captions):
            raise ValueError("OpenAI returned a caption that was not exactly two words")
        return captions
