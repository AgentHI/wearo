from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)
TRANSIENT_UPSTREAM_STATUSES = {502, 503, 504}


class BFLUpstreamError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        phase: str,
        status_code: int = 502,
        response_body: Any = None,
        request_id: str | None = None,
        job_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id
        self.job_id = job_id

    def public_detail(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "upstream": "BFL",
            "phase": self.phase,
            "upstream_status": self.status_code,
            "upstream_response": self.response_body,
            "request_id": self.request_id,
            "generation_id": self.job_id,
        }


def _safe_response_body(response: Any) -> Any:
    try:
        body = response.json()
    except (ValueError, requests.JSONDecodeError):
        return str(getattr(response, "text", ""))[:2000]

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[redacted]"
                if key.casefold() in {"image", "images", "input_image", "api_key", "x-key"}
                else redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [redact(item) for item in value[:20]]
        if isinstance(value, str) and len(value) > 2000:
            return f"{value[:200]}...[truncated]"
        return value

    return redact(body)


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
        is_flash_5 = model.startswith("dola-seedream-5-0-flash-")
        if is_flash_5:
            payload["prompt"] = (
                f"{prompt.rstrip()} Output a portrait image with a 2:3 aspect ratio."
            )
        if images:
            payload["image"] = [self._data_url(image) for image in images]
            if not is_flash_5:
                payload["sequential_image_generation"] = "disabled"
            else:
                payload.pop("sequential_image_generation", None)
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


class BFLAdapter:
    """Black Forest Labs submit-and-poll image generation adapter."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 120,
        *,
        submit_timeout: int = 20,
        poll_timeout: int = 10,
        download_timeout: int = 30,
        max_poll_attempts: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.api_key = api_key
        self.timeout = timeout
        self.submit_timeout = submit_timeout
        self.poll_timeout = poll_timeout
        self.download_timeout = download_timeout
        self.max_poll_attempts = max_poll_attempts

    @property
    def headers(self) -> dict[str, str]:
        return {"x-key": self.api_key, "Content-Type": "application/json"}

    def validate(self) -> tuple[bool, str]:
        response = requests.get(f"{self.base_url}/v1/credits", headers=self.headers, timeout=15)
        return (
            response.ok,
            "Connection successful" if response.ok else f"HTTP {response.status_code}",
        )

    def generate(
        self, *, model: str, prompt: str, images: list[bytes], parameters: dict[str, Any]
    ) -> GenerationResult:
        payload = {"prompt": prompt, **parameters}
        encoded = [base64.b64encode(image).decode() for image in images]
        model_path = model.strip("/").removeprefix("v1/")
        if model_path == "flux-3-image-klein":
            if encoded:
                payload["images"] = encoded
        else:
            for index, image in enumerate(encoded):
                field = "input_image" if index == 0 else f"input_image_{index + 1}"
                payload[field] = image
        return self._submit(model, payload)

    def generate_from_prompt(
        self, *, model: str, prompt: str, parameters: dict[str, Any] | None = None
    ) -> GenerationResult:
        return self._submit(model, {"prompt": prompt, **(parameters or {})})

    def _submit(self, model: str, payload: dict[str, Any]) -> GenerationResult:
        started = time.monotonic()
        model_path = model.strip("/")
        if model_path.startswith("v1/"):
            model_path = model_path[3:]
        try:
            response = requests.post(
                f"{self.base_url}/v1/{model_path}",
                headers=self.headers,
                json=payload,
                timeout=self.submit_timeout,
            )
        except requests.RequestException as error:
            self._log("submit", started, error=str(error))
            raise BFLUpstreamError(
                f"BFL submission failed before a job was confirmed: {error}", phase="submit"
            ) from error
        request_header = self._request_id(response)
        submission_body = _safe_response_body(response)
        self._log(
            "submit",
            started,
            status=getattr(response, "status_code", None),
            response=submission_body,
            request_id=request_header,
        )
        if not response.ok:
            raise BFLUpstreamError(
                f"BFL submission returned HTTP {response.status_code}",
                phase="submit",
                status_code=response.status_code,
                response_body=submission_body,
                request_id=request_header,
            )
        try:
            submission = response.json()
            request_id = str(submission["id"])
            polling_url = str(submission["polling_url"])
        except (KeyError, TypeError, ValueError) as error:
            raise BFLUpstreamError(
                "BFL submission did not return the documented id and polling_url",
                phase="submit",
                response_body=submission_body,
                request_id=request_header,
            ) from error
        self._log(
            "submit_accepted",
            started,
            status=getattr(response, "status_code", None),
            request_id=request_header,
            job_id=request_id,
        )
        deadline = time.monotonic() + self.timeout
        result_body: dict[str, Any] = {}
        for attempt in range(self.max_poll_attempts):
            if time.monotonic() >= deadline:
                break
            poll = self._get_with_retry(
                polling_url,
                phase="poll",
                timeout=self.poll_timeout,
                job_id=request_id,
            )
            result_body = poll.json()
            status = str(result_body.get("status", "")).casefold()
            if status == "ready":
                break
            if status in {
                "error",
                "failed",
                "task not found",
                "request moderated",
                "content moderated",
                "no card generated",
            }:
                raise BFLUpstreamError(
                    f"BFL generation failed with status {result_body.get('status')}",
                    phase="poll",
                    response_body=_safe_response_body(poll),
                    request_id=self._request_id(poll),
                    job_id=request_id,
                )
            if status not in {"pending", "reasoning", "generating"}:
                raise BFLUpstreamError(
                    f"BFL returned unknown generation status {result_body.get('status')}",
                    phase="poll",
                    response_body=_safe_response_body(poll),
                    job_id=request_id,
                )
            time.sleep(min(0.5 * (2 ** min(attempt, 3)), 4.0))
        else:
            attempt = self.max_poll_attempts
        if str(result_body.get("status", "")).casefold() != "ready":
            raise BFLUpstreamError(
                f"BFL generation timed out after {attempt + 1} polling attempts",
                phase="timeout",
                status_code=504,
                response_body=result_body or None,
                job_id=request_id,
            )
        image_url = (result_body.get("result") or {}).get("sample")
        if not image_url:
            raise BFLUpstreamError(
                "BFL generation completed without an image URL",
                phase="poll",
                response_body=result_body,
                job_id=request_id,
            )
        image_response = self._get_with_retry(
            str(image_url),
            phase="download",
            timeout=self.download_timeout,
            job_id=request_id,
            authenticated=False,
        )
        usage: dict[str, Any] = {"output_images": 1}
        if submission.get("input_mp") is not None:
            usage["megapixels"] = submission["input_mp"]
        return GenerationResult(
            image_response.content,
            request_id,
            usage,
            {"submission": submission, "result": result_body},
            round((time.monotonic() - started) * 1000),
        )

    def _get_with_retry(
        self,
        url: str,
        *,
        phase: str,
        timeout: int,
        job_id: str,
        authenticated: bool = True,
    ) -> Any:
        started = time.monotonic()
        for attempt in range(3):
            try:
                response = requests.get(
                    url,
                    headers=self.headers if authenticated else None,
                    timeout=timeout,
                )
            except requests.RequestException as error:
                self._log(phase, started, job_id=job_id, error=str(error))
                if attempt == 2:
                    raise BFLUpstreamError(
                        f"BFL {phase} request failed: {error}",
                        phase=phase,
                        job_id=job_id,
                    ) from error
                time.sleep(0.5 * (2**attempt))
                continue
            body = None if phase == "download" else _safe_response_body(response)
            self._log(
                phase,
                started,
                status=getattr(response, "status_code", None),
                response=body,
                request_id=self._request_id(response),
                job_id=job_id,
            )
            if response.ok:
                return response
            if response.status_code in TRANSIENT_UPSTREAM_STATUSES and attempt < 2:
                time.sleep(0.5 * (2**attempt))
                continue
            raise BFLUpstreamError(
                f"BFL {phase} returned HTTP {response.status_code}",
                phase=phase,
                status_code=response.status_code,
                response_body=body,
                request_id=self._request_id(response),
                job_id=job_id,
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _request_id(response: Any) -> str | None:
        headers = getattr(response, "headers", {}) or {}
        return headers.get("x-request-id") or headers.get("x-bfl-request-id")

    @staticmethod
    def _log(phase: str, started: float, **fields: Any) -> None:
        logger.info(
            "bfl_upstream %s",
            json.dumps(
                {
                    "phase": phase,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    **fields,
                },
                default=str,
            ),
        )
