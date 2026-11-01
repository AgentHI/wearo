from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests


@dataclass(frozen=True)
class GenerationResult:
    image_bytes: bytes
    request_id: str | None
    usage: dict[str, Any]
    raw_metadata: dict[str, Any]
    latency_ms: int


class ProviderAdapter(Protocol):
    def validate(self) -> tuple[bool, str]: ...
    def generate(
        self, *, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> GenerationResult: ...


def normalize_openai_usage(raw: dict[str, Any]) -> dict[str, Any]:
    """Map only explicitly reported OpenAI image usage fields."""
    details = raw.get("input_tokens_details") or {}
    output_details = raw.get("output_tokens_details") or {}
    normalized: dict[str, Any] = {}
    if details.get("image_tokens") is not None:
        normalized["image_input_tokens"] = details["image_tokens"]
    if details.get("text_tokens") is not None:
        normalized["text_input_tokens"] = details["text_tokens"]
    if details.get("cached_tokens") is not None:
        normalized["cached_input_tokens"] = details["cached_tokens"]
    if output_details.get("image_tokens") is not None:
        normalized["image_output_tokens"] = output_details["image_tokens"]
    elif raw.get("output_tokens") is not None:
        normalized["image_output_tokens"] = raw["output_tokens"]
    if raw.get("total_tokens") is not None:
        normalized["total_reported_tokens"] = raw["total_tokens"]
    return normalized


class OpenAICompatibleAdapter:
    """Explicit OpenAI Images adapter; other providers need their own request contract."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def validate(self) -> tuple[bool, str]:
        response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=15)
        return (
            response.ok,
            "Connection successful" if response.ok else f"HTTP {response.status_code}",
        )

    def generate(
        self, *, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> GenerationResult:
        started = time.monotonic()
        files = [
            ("image[]", (f"input-{index}.png", value, "image/png"))
            for index, value in enumerate(images)
        ]
        response = requests.post(
            f"{self.base_url}/images/edits",
            headers=self.headers,
            data={"model": model, "prompt": prompt, "n": "1", **parameters},
            files=files,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        item = body["data"][0]
        if "b64_json" in item:
            image = base64.b64decode(item["b64_json"])
        else:
            image_response = requests.get(item["url"], timeout=30)
            image_response.raise_for_status()
            image = image_response.content
        raw_usage = body.get("usage") or {}
        usage = normalize_openai_usage(raw_usage)
        return GenerationResult(
            image,
            response.headers.get("x-request-id"),
            usage,
            {"usage": raw_usage},
            round((time.monotonic() - started) * 1000),
        )

    def generate_from_prompt(
        self, *, model: str, prompt: str, parameters: dict[str, Any] | None = None
    ) -> GenerationResult:
        started = time.monotonic()
        response = requests.post(
            f"{self.base_url}/images/generations",
            headers={**self.headers, "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt, "n": 1, **(parameters or {})},
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        item = body["data"][0]
        if "b64_json" in item:
            image = base64.b64decode(item["b64_json"])
        else:
            image_response = requests.get(item["url"], timeout=30)
            image_response.raise_for_status()
            image = image_response.content
        raw_usage = body.get("usage") or {}
        usage = normalize_openai_usage(raw_usage)
        return GenerationResult(
            image,
            response.headers.get("x-request-id"),
            usage,
            {"usage": raw_usage},
            round((time.monotonic() - started) * 1000),
        )


class BytePlusAdapter:
    """BytePlus ModelArk image generation adapter."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def validate(self) -> tuple[bool, str]:
        response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=15)
        return (
            response.ok,
            "Connection successful" if response.ok else f"HTTP {response.status_code}",
        )

    def generate(
        self, *, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> GenerationResult:
        return self._generate(model, prompt, images, parameters)

    def generate_from_prompt(
        self, *, model: str, prompt: str, parameters: dict[str, Any] | None = None
    ) -> GenerationResult:
        return self._generate(model, prompt, [], parameters or {})

    def _generate(
        self, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> GenerationResult:
        started = time.monotonic()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "response_format": "b64_json",
            "watermark": False,
            **parameters,
        }
        if images:
            payload["image"] = [self._data_url(image) for image in images]
            payload["sequential_image_generation"] = "disabled"
        response = requests.post(
            f"{self.base_url}/images/generations",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            try:
                error = response.json().get("error") or {}
                code = str(error.get("code") or f"HTTP_{response.status_code}")
                message = str(error.get("message") or "BytePlus request failed")
            except (requests.JSONDecodeError, AttributeError, TypeError, ValueError):
                code = f"HTTP_{response.status_code}"
                message = "BytePlus request failed"
            raise RuntimeError(f"BYTEPLUS_{code}: {message}")
        body = response.json()
        item = body["data"][0]
        if "b64_json" in item:
            image = base64.b64decode(item["b64_json"], validate=True)
        else:
            image_response = requests.get(item["url"], timeout=30)
            image_response.raise_for_status()
            image = image_response.content
        raw_usage = body.get("usage") or {}
        usage = self._normalize_usage(raw_usage)
        return GenerationResult(
            image,
            response.headers.get("x-request-id") or response.headers.get("x-tt-logid"),
            usage,
            {"usage": raw_usage},
            round((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _data_url(image: bytes) -> str:
        if image.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif image.startswith(b"RIFF") and image[8:12] == b"WEBP":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"
        return f"data:{mime_type};base64,{base64.b64encode(image).decode()}"

    @staticmethod
    def _normalize_usage(raw: dict[str, Any]) -> dict[str, Any]:
        usage: dict[str, Any] = {}
        for source, target in (
            ("input_tokens", "image_input_tokens"),
            ("output_tokens", "image_output_tokens"),
            ("total_tokens", "total_reported_tokens"),
            ("generated_images", "output_images"),
        ):
            if raw.get(source) is not None:
                usage[target] = raw[source]
        return usage
