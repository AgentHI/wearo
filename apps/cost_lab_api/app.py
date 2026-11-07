import hashlib
import hmac
import html
import json
import os
import random
import re
import secrets
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageOps
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.admin_auth import verify_password
from apps.api.wearo_api.render_quality_strategy import quality_parameters

from .adapters import BFLAdapter, BFLUpstreamError, BytePlusAdapter, OpenAICompatibleAdapter
from .config import Settings
from .pricing import calculate_cost

COOKIE = "wearo_cost_lab_session"


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class ProviderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    provider_type: Literal["OPENAI_COMPATIBLE", "BYTEPLUS", "BFL", "SECRET_REFERENCE"]
    api_base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    secret_reference: str | None = Field(default=None, max_length=512)
    pricing_reference_url: AnyHttpUrl | None = None
    pricing_reference_text: str | None = Field(default=None, max_length=10_000)
    enabled: bool = True


class ModelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: UUID
    name: str = Field(min_length=1, max_length=120)
    api_identifier: str = Field(min_length=1, max_length=240)
    version: str | None = Field(default=None, max_length=120)
    input_formats: list[str] = ["png", "jpeg"]
    output_formats: list[str] = ["png"]
    quality_levels: list[str] = []
    enabled: bool = True


class PricingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_at: datetime
    components: list[dict[str, Any]]


class ModelWithPricingBody(ModelBody):
    image_input_price_usd_per_million: Decimal | None = Field(default=None, ge=0)
    image_output_price_usd_per_million: Decimal | None = Field(default=None, ge=0)
    output_image_price_usd_low: Decimal | None = Field(default=None, ge=0)
    output_image_price_usd_medium: Decimal | None = Field(default=None, ge=0)
    output_image_price_usd_high: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def has_pricing(self) -> "ModelWithPricingBody":
        prices = (
            self.image_input_price_usd_per_million,
            self.image_output_price_usd_per_million,
            self.output_image_price_usd_low,
            self.output_image_price_usd_medium,
            self.output_image_price_usd_high,
        )
        if all(price is None for price in prices):
            raise ValueError("At least one token or per-image price is required")
        return self


def _model_pricing_components(body: ModelWithPricingBody) -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    token_prices = (
        ("image_input_tokens", body.image_input_price_usd_per_million),
        ("image_output_tokens", body.image_output_price_usd_per_million),
    )
    components.extend(
        {"unit": unit, "price_usd": str(price)} for unit, price in token_prices if price is not None
    )
    quality_prices = (
        ("LOW", body.output_image_price_usd_low),
        ("MEDIUM", body.output_image_price_usd_medium),
        ("HIGH", body.output_image_price_usd_high),
    )
    components.extend(
        {"unit": "output_images", "quality": quality, "price_usd": str(price)}
        for quality, price in quality_prices
        if price is not None
    )
    return components


class QualityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    compression_quality: int = Field(ge=1, le=100)
    output_resolution: str = Field(min_length=1, max_length=80)
    settings: dict[str, Any] = {}


class MappingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: UUID
    supported: bool = True
    provider_quality: str | None = None
    request_parameters: dict[str, Any] = {}


class BenchmarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: UUID
    category: Literal["JEWELLERY", "SAREE", "DRESS"]
    person_asset_id: UUID | None = None
    person_result_tryon_id: UUID | None = None
    product_asset_id: UUID | None = None
    product_asset_ids: list[UUID] = Field(default_factory=list, max_length=100)
    input_complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"] = "MEDIUM"
    input_quality: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH"
    output_quality: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH"
    image_count: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def product_sources_are_valid(self) -> "BenchmarkBody":
        if self.product_asset_id is not None and self.product_asset_ids:
            raise ValueError("Select either one legacy product or multiple product sources")
        if len(self.product_asset_ids) != len(set(self.product_asset_ids)):
            raise ValueError("Product source IDs must be unique")
        return self


class DatasetGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: UUID
    generation_quality: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH"
    category: Literal["PERSON", "JEWELLERY", "SAREE", "DRESS"]
    complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"] = "MEDIUM"
    count: int = Field(default=10, ge=1, le=100)
    prompt: str | None = Field(default=None, max_length=4000)
    direction: str | None = Field(default=None, max_length=4000)


class ModelComparisonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_result_tryon_id: UUID
    product_asset_id: UUID
    category: Literal["JEWELLERY", "SAREE", "DRESS"]
    output_quality: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH"


class ModelTestStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tested: bool


class FinalCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: UUID
    person_asset_id: UUID
    jewellery_complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"] = "MEDIUM"
    saree_complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"] = "MEDIUM"
    dress_complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"] = "MEDIUM"


class AssetComplexityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    complexity: Literal["SIMPLE", "MEDIUM", "COMPLEX"]


class FinalReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tryon_id: UUID
    score: int = Field(ge=1, le=10)
    comment: str = Field(default="", max_length=4000)


class FinalReviewsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviews: list[FinalReviewItem] = Field(min_length=1, max_length=12)


class PromoteFinalCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quality_levels: list[Literal["LOW", "MEDIUM", "HIGH"]] = Field(
        min_length=1, max_length=3
    )

    @model_validator(mode="after")
    def qualities_are_unique(self) -> "PromoteFinalCheckBody":
        if len(self.quality_levels) != len(set(self.quality_levels)):
            raise ValueError("Quality levels must be unique")
        return self


class ProductionModelPriorityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_id: UUID
    priority: int = Field(ge=1, le=20)


class ProductionModelPrioritiesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priorities: list[ProductionModelPriorityItem] = Field(min_length=1)

    @model_validator(mode="after")
    def priorities_are_unique(self) -> "ProductionModelPrioritiesBody":
        release_ids = [item.release_id for item in self.priorities]
        priorities = [item.priority for item in self.priorities]
        if len(release_ids) != len(set(release_ids)):
            raise ValueError("Release IDs must be unique")
        if len(priorities) != len(set(priorities)):
            raise ValueError("Priorities must be unique")
        return self


class KnowledgeTextBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=1_000_000)


def _single_item_dataset_instruction(kind: str, index: int, count: int) -> str:
    if kind == "PERSON":
        return (
            " Generate exactly one person in this image. Do not create a group, collage, grid, "
            "contact sheet, or multiple alternatives."
        )
    return (
        " This is one image in a multi-image dataset batch. Generate exactly ONE standalone "
        "wearable product in this image. Do not place multiple products, an assortment, a "
        "collection, a collage, a grid, a contact sheet, or alternative designs in the same "
        "image. Treat quantities and product lists in the evaluator prompt as the requested "
        "distribution across the whole batch, not as contents for one image. For dataset image "
        f"{index + 1} of {count}, select only one of the requested product types while preserving "
        "the requested distribution across the batch. Allocate requested quantities in the order "
        "they are listed: the first quantity fills the first output positions, the next quantity "
        "fills the following positions, and so on. A matching pair or coordinated set is "
        "allowed only when the evaluator explicitly requests that set as one try-on product."
    )


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def _provider_adapter(provider: dict[str, Any]) -> type:
    provider_type = provider.get("provider_type")
    base_url = str(provider.get("api_base_url") or "").casefold()
    if provider_type == "BFL" or (provider_type == "SECRET_REFERENCE" and "bfl.ai" in base_url):
        return BFLAdapter
    if provider_type == "BYTEPLUS":
        return BytePlusAdapter
    if provider_type == "OPENAI_COMPATIBLE":
        return OpenAICompatibleAdapter
    raise HTTPException(422, "This provider has no generation adapter configured")


def _provider_quality_parameters(
    provider: dict[str, Any], model: str, quality: str
) -> dict[str, str | int]:
    adapter = _provider_adapter(provider)
    strategy_provider = {
        OpenAICompatibleAdapter: "OPENAI",
        BytePlusAdapter: "BYTEPLUS",
        BFLAdapter: "BFL",
    }[adapter]
    return quality_parameters(strategy_provider, model, quality)


def _knowledge_html(value: str) -> str:
    """Render common pasted-text structure without accepting arbitrary HTML."""
    blocks: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{' '.join(paragraph)}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind and list_items:
            blocks.append(
                f"<{list_kind}>{''.join(f'<li>{item}</li>' for item in list_items)}</{list_kind}>"
            )
        list_kind = None
        list_items.clear()

    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        bullet = re.match(r"^(?:[-*•])\s+(.+)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(len(heading.group(1)) + 1, 4)
            blocks.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
        elif bullet or numbered:
            flush_paragraph()
            wanted_kind = "ul" if bullet else "ol"
            if list_kind != wanted_kind:
                flush_list()
                list_kind = wanted_kind
            match = bullet or numbered
            if match:
                list_items.append(html.escape(match.group(1)))
        elif line.startswith("> "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        else:
            flush_list()
            paragraph.append(html.escape(line))
    flush_paragraph()
    flush_list()
    return "".join(blocks)


KNOWLEDGE_DOCUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["heading", "paragraph", "bullets", "numbered", "quote"],
                    },
                    "level": {"type": "integer", "minimum": 2, "maximum": 4},
                    "text": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["type", "level", "text", "items"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["blocks"],
    "additionalProperties": False,
}


def _structured_knowledge_html(document: dict[str, Any]) -> str:
    blocks = document.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("Knowledge formatter returned no document blocks")
    rendered: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Knowledge formatter returned an invalid block")
        kind = block.get("type")
        text_value = html.escape(str(block.get("text") or "").strip())
        raw_items = block.get("items")
        items = (
            [html.escape(str(item).strip()) for item in raw_items]
            if isinstance(raw_items, list)
            else []
        )
        items = [item for item in items if item]
        if kind == "heading" and text_value:
            level = min(max(int(block.get("level") or 2), 2), 4)
            rendered.append(f"<h{level}>{text_value}</h{level}>")
        elif kind == "paragraph" and text_value:
            rendered.append(f"<p>{text_value}</p>")
        elif kind == "quote" and text_value:
            rendered.append(f"<blockquote>{text_value}</blockquote>")
        elif kind in {"bullets", "numbered"} and items:
            tag = "ul" if kind == "bullets" else "ol"
            rendered.append(f"<{tag}>{''.join(f'<li>{item}</li>' for item in items)}</{tag}>")
        else:
            raise ValueError("Knowledge formatter returned an empty or unsupported block")
    return "".join(rendered)


def _format_knowledge_with_llm(content: str) -> tuple[str, str, dict[str, Any]]:
    api_key = os.getenv("WEARO_OPENAI_API_KEY", "").strip()
    model = os.getenv("WEARO_OPENAI_ANALYSIS_MODEL", "").strip()
    if not api_key or not model:
        raise HTTPException(
            503,
            "WEARO_OPENAI_API_KEY and WEARO_OPENAI_ANALYSIS_MODEL are required",
        )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": [
                    {
                        "role": "developer",
                        "content": (
                            "Structure the complete supplied knowledge for comfortable reading. "
                            "Preserve every factual detail and the original meaning. Do not summarize, "
                            "add facts, answer questions, or omit content. Organize only with headings, "
                            "paragraphs, lists, and quotations."
                        ),
                    },
                    {"role": "user", "content": content},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "wearo_knowledge_document",
                        "strict": True,
                        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
                    }
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, requests.JSONDecodeError) as error:
        raise HTTPException(502, "Knowledge formatting model is unavailable") from error
    if body.get("status") != "completed":
        raise HTTPException(502, "Knowledge formatting did not complete")
    for output in body.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for part in output.get("content", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise HTTPException(422, "Knowledge formatting was refused")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                try:
                    document = json.loads(part["text"])
                    if not isinstance(document, dict):
                        raise ValueError
                    return _structured_knowledge_html(document), model, body.get("usage") or {}
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    raise HTTPException(
                        502, "Knowledge formatting returned invalid content"
                    ) from error
    raise HTTPException(502, "Knowledge formatting returned no content")


def reproducible_combinations(
    people: list[dict[str, Any]],
    products: list[dict[str, Any]],
    qualities: Sequence[str],
    count: int,
    seed: int,
) -> list[tuple[str, UUID, UUID]]:
    rng = random.Random(seed)
    return [
        (quality, rng.choice(people)["asset_id"], rng.choice(products)["asset_id"])
        for quality in qualities
        for _ in range(count)
    ]


def final_check_score_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build the category/quality-aware final-check score summary."""
    if not rows:
        raise ValueError("Final check has no reviews")
    groups: dict[str, list[int]] = {}
    for row in rows:
        groups.setdefault(f"{row['category']}:{row['quality']}", []).append(int(row["score"]))
    scores = [int(row["score"]) for row in rows]
    return {
        "review_count": len(scores),
        "average_score": round(sum(scores) / len(scores), 2),
        "minimum_score": min(scores),
        "maximum_score": max(scores),
        "by_category_quality": {
            key: {"count": len(values), "average": round(sum(values) / len(values), 2)}
            for key, values in sorted(groups.items())
        },
    }


class CostLab:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self.settings = settings
        self.engine = engine
        try:
            self.cipher = Fernet(settings.encryption_key.encode())
        except ValueError as error:
            raise RuntimeError("COST_LAB_ENCRYPTION_KEY must be a Fernet key") from error
        settings.storage_root.mkdir(parents=True, exist_ok=True)

    def secret_for(self, provider: dict[str, Any]) -> str:
        if provider.get("secret_ciphertext"):
            try:
                return self.cipher.decrypt(bytes(provider["secret_ciphertext"])).decode()
            except InvalidToken as error:
                raise HTTPException(500, "Provider credential cannot be decrypted") from error
        reference = provider.get("secret_reference") or ""
        if not reference.startswith("env:"):
            raise HTTPException(400, "Only env:NAME secret references are supported")
        value = os.getenv(reference[4:])
        if not value:
            raise HTTPException(400, "Provider secret reference is unavailable")
        return value


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    actual = settings or Settings.from_env()
    service = CostLab(actual, engine or create_engine(actual.database_url, pool_pre_ping=True))
    app = FastAPI(title="Wearo Model Cost Lab API", version="1.0.0")
    app.state.cost_lab = service

    def require_session(request: Request) -> str:
        token = request.cookies.get(COOKIE)
        if not token:
            raise HTTPException(401, "Cost Lab login required")
        digest = hashlib.sha256(token.encode()).digest()
        with service.engine.begin() as connection:
            username = connection.execute(
                text("""SELECT username FROM cost_lab.login_sessions
                WHERE token_hash=:token AND revoked_at IS NULL AND expires_at > now()"""),
                {"token": digest},
            ).scalar_one_or_none()
        if username is None:
            raise HTTPException(401, "Cost Lab session expired")
        return str(username)

    Auth = Annotated[str, Depends(require_session)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "cost-lab-api"}

    @app.post("/api/cost-lab/auth/login")
    def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
        username = body.username.strip().casefold()
        ip_hash = hmac.digest(
            actual.session_secret.encode(),
            (request.client.host if request.client else "unknown").encode(),
            "sha256",
        )
        with service.engine.begin() as connection:
            failures: int = connection.execute(
                text("""SELECT count(*) FROM cost_lab.login_attempts WHERE username=:username
                AND ip_hash=:ip AND succeeded=false AND attempted_at > now() - interval '15 minutes'"""),
                {"username": username, "ip": ip_hash},
            ).scalar_one()
            if failures >= 5:
                raise HTTPException(429, "Too many failed login attempts; try again later")
            valid = hmac.compare_digest(
                username, actual.admin_username.strip().casefold()
            ) and verify_password(body.password, actual.password_hash.encode())
            connection.execute(
                text("""INSERT INTO cost_lab.login_attempts(attempt_id,username,ip_hash,succeeded)
                VALUES(:id,:username,:ip,:valid)"""),
                {"id": uuid4(), "username": username, "ip": ip_hash, "valid": valid},
            )
            if not valid:
                raise HTTPException(401, "Invalid Cost Lab credentials")
            token = secrets.token_urlsafe(48)
            expires = datetime.now(UTC) + timedelta(minutes=actual.session_ttl_minutes)
            connection.execute(
                text("""INSERT INTO cost_lab.login_sessions(session_id,token_hash,username,expires_at)
                VALUES(:id,:hash,:username,:expires)"""),
                {
                    "id": uuid4(),
                    "hash": hashlib.sha256(token.encode()).digest(),
                    "username": username,
                    "expires": expires,
                },
            )
        response.set_cookie(
            COOKIE,
            token,
            max_age=actual.session_ttl_minutes * 60,
            secure=actual.secure_cookie,
            httponly=True,
            samesite="strict",
            path="/api/cost-lab",
        )
        return {"authenticated": True, "username": username, "expires_at": expires}

    @app.get("/api/cost-lab/auth/session")
    def session(username: Auth) -> dict[str, Any]:
        return {"authenticated": True, "username": username}

    @app.post("/api/cost-lab/auth/logout")
    def logout(request: Request, response: Response, _: Auth) -> dict[str, bool]:
        token = request.cookies.get(COOKIE, "")
        with service.engine.begin() as connection:
            connection.execute(
                text("UPDATE cost_lab.login_sessions SET revoked_at=now() WHERE token_hash=:hash"),
                {"hash": hashlib.sha256(token.encode()).digest()},
            )
        response.delete_cookie(COOKIE, path="/api/cost-lab")
        return {"logged_out": True}

    @app.get("/api/cost-lab/providers")
    def providers(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            items = _rows(
                connection.execute(
                    text("""SELECT provider_id,name,provider_type,api_base_url,
                secret_reference,(secret_ciphertext IS NOT NULL) has_stored_secret,
                pricing_reference_url,pricing_reference_text,enabled,created_at,updated_at
                FROM cost_lab.model_providers ORDER BY name""")
                )
            )
        return {"providers": items}

    @app.get("/api/cost-lab/overview")
    def overview(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            provider_metrics = _rows(
                connection.execute(
                    text("""SELECT p.provider_id,p.name,p.enabled,count(m.model_id) model_count
                    FROM cost_lab.model_providers p LEFT JOIN cost_lab.ai_models m USING(provider_id)
                    GROUP BY p.provider_id,p.name,p.enabled ORDER BY p.name""")
                )
            )
            model_metrics = _rows(
                connection.execute(
                    text("""SELECT m.model_id,m.name model_name,p.name provider_name,m.enabled,
                    count(DISTINCT r.run_id) benchmark_runs,
                    count(t.tryon_id) FILTER (WHERE t.status='SUCCEEDED') successful_tryons,
                    avg(u.calculated_cost_usd) FILTER (WHERE t.status='SUCCEEDED') average_tryon_cost_usd
                    FROM cost_lab.ai_models m JOIN cost_lab.model_providers p USING(provider_id)
                    LEFT JOIN cost_lab.benchmark_runs r USING(model_id)
                    LEFT JOIN cost_lab.tryon_runs t USING(run_id)
                    LEFT JOIN cost_lab.tryon_usage u USING(tryon_id)
                    GROUP BY m.model_id,m.name,p.name,m.enabled ORDER BY p.name,m.name""")
                )
            )
            quality_metrics = _rows(
                connection.execute(
                    text("""SELECT m.model_id,m.name model_name,p.name provider_name,c.quality,
                    count(DISTINCT r.run_id) benchmark_runs,
                    count(t.tryon_id) total_tryons,
                    count(t.tryon_id) FILTER (WHERE t.status='SUCCEEDED') successful_tryons
                    FROM cost_lab.ai_models m JOIN cost_lab.model_providers p USING(provider_id)
                    LEFT JOIN cost_lab.benchmark_runs r USING(model_id)
                    LEFT JOIN cost_lab.tryon_runs t USING(run_id)
                    LEFT JOIN cost_lab.benchmark_combinations c USING(combination_id)
                    GROUP BY m.model_id,m.name,p.name,c.quality ORDER BY p.name,m.name,c.quality""")
                )
            )
        return {
            "provider_count": len(provider_metrics),
            "model_count": len(model_metrics),
            "providers": provider_metrics,
            "models": model_metrics,
            "qualities": [item for item in quality_metrics if item["quality"] is not None],
        }

    @app.post("/api/cost-lab/providers", status_code=201)
    def create_provider(body: ProviderBody, _: Auth) -> dict[str, Any]:
        if not body.api_key and not body.secret_reference:
            raise HTTPException(422, "api_key or secret_reference is required")
        if body.secret_reference and not body.secret_reference.startswith("env:"):
            raise HTTPException(422, "secret_reference must use env:NAME")
        provider_id = uuid4()
        encrypted = service.cipher.encrypt(body.api_key.encode()) if body.api_key else None
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.model_providers
                (provider_id,name,provider_type,api_base_url,secret_ciphertext,secret_reference,
                 pricing_reference_url,pricing_reference_text,enabled)
                VALUES(:id,:name,:type,:url,:secret,:reference,:pricing_url,:pricing_text,:enabled)"""),
                {
                    "id": provider_id,
                    "name": body.name,
                    "type": body.provider_type,
                    "url": body.api_base_url,
                    "secret": encrypted,
                    "reference": body.secret_reference,
                    "pricing_url": (
                        str(body.pricing_reference_url) if body.pricing_reference_url else None
                    ),
                    "pricing_text": body.pricing_reference_text,
                    "enabled": body.enabled,
                },
            )
        return {"provider_id": provider_id, "name": body.name}

    @app.put("/api/cost-lab/providers/{provider_id}")
    def update_provider(provider_id: UUID, body: ProviderBody, _: Auth) -> dict[str, Any]:
        if body.secret_reference and not body.secret_reference.startswith("env:"):
            raise HTTPException(422, "secret_reference must use env:NAME")
        encrypted = service.cipher.encrypt(body.api_key.encode()) if body.api_key else None
        with service.engine.begin() as connection:
            existing = (
                connection.execute(
                    text("""SELECT secret_ciphertext,secret_reference FROM cost_lab.model_providers
                WHERE provider_id=:id"""),
                    {"id": provider_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                raise HTTPException(404, "Provider not found")
            if body.api_key:
                secret_ciphertext, secret_reference = encrypted, None
            elif body.secret_reference:
                secret_ciphertext, secret_reference = None, body.secret_reference
            else:
                secret_ciphertext = existing["secret_ciphertext"]
                secret_reference = existing["secret_reference"]
            if not secret_ciphertext and not secret_reference:
                raise HTTPException(422, "api_key or secret_reference is required")
            connection.execute(
                text("""UPDATE cost_lab.model_providers SET name=:name,provider_type=:type,
                api_base_url=:url,secret_ciphertext=:secret,secret_reference=:reference,
                pricing_reference_url=:pricing_url,pricing_reference_text=:pricing_text,
                enabled=:enabled,updated_at=now() WHERE provider_id=:id"""),
                {
                    "id": provider_id,
                    "name": body.name,
                    "type": body.provider_type,
                    "url": body.api_base_url,
                    "secret": secret_ciphertext,
                    "reference": secret_reference,
                    "pricing_url": (
                        str(body.pricing_reference_url) if body.pricing_reference_url else None
                    ),
                    "pricing_text": body.pricing_reference_text,
                    "enabled": body.enabled,
                },
            )
        return {"provider_id": provider_id, "name": body.name}

    @app.post("/api/cost-lab/providers/{provider_id}/validate")
    def validate_provider(provider_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            provider = (
                connection.execute(
                    text("SELECT * FROM cost_lab.model_providers WHERE provider_id=:id"),
                    {"id": provider_id},
                )
                .mappings()
                .one_or_none()
            )
        if provider is None:
            raise HTTPException(404, "Provider not found")
        if not provider["api_base_url"]:
            raise HTTPException(400, "This provider type has no connection validator")
        try:
            adapter_type = _provider_adapter(dict(provider))
            ok, message = adapter_type(
                provider["api_base_url"], service.secret_for(dict(provider))
            ).validate()
        except requests.RequestException as error:
            return {"valid": False, "message": str(error)}
        return {"valid": ok, "message": message}

    @app.get("/api/cost-lab/models")
    def models(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            items = _rows(
                connection.execute(
                    text("""SELECT m.*,p.name provider_name,
                (SELECT jsonb_agg(jsonb_build_object('pricing_id',x.pricing_id,'effective_at',x.effective_at,'components',x.components) ORDER BY x.effective_at DESC)
                 FROM cost_lab.model_pricing x WHERE x.model_id=m.model_id) pricing
                FROM cost_lab.ai_models m JOIN cost_lab.model_providers p USING(provider_id) ORDER BY p.name,m.name""")
                )
            )
        return {"models": items}

    @app.post("/api/cost-lab/models", status_code=201)
    def create_model(body: ModelBody, _: Auth) -> dict[str, Any]:
        model_id = uuid4()
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.ai_models(model_id,provider_id,name,api_identifier,version,input_formats,output_formats,quality_levels,enabled)
                VALUES(:id,:provider,:name,:api,:version,CAST(:inputs AS jsonb),CAST(:outputs AS jsonb),CAST(:qualities AS jsonb),:enabled)"""),
                {
                    "id": model_id,
                    "provider": body.provider_id,
                    "name": body.name,
                    "api": body.api_identifier,
                    "version": body.version,
                    "inputs": _json(body.input_formats),
                    "outputs": _json(body.output_formats),
                    "qualities": _json(body.quality_levels),
                    "enabled": body.enabled,
                },
            )
            connection.execute(
                text("""INSERT INTO cost_lab.model_quality_mapping(mapping_id,model_id,profile_id,supported,request_parameters)
                SELECT gen_random_uuid(),:model,profile_id,true,'{}'::jsonb FROM cost_lab.quality_profiles WHERE code=ANY(:levels)"""),
                {"model": model_id, "levels": body.quality_levels},
            )
        return {"model_id": model_id, "name": body.name}

    @app.post("/api/cost-lab/models-with-pricing", status_code=201)
    def create_model_with_pricing(body: ModelWithPricingBody, _: Auth) -> dict[str, Any]:
        model_id = uuid4()
        pricing_id = uuid4()
        components = _model_pricing_components(body)
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.ai_models(model_id,provider_id,name,api_identifier,version,input_formats,output_formats,quality_levels,enabled)
                VALUES(:id,:provider,:name,:api,:version,CAST(:inputs AS jsonb),CAST(:outputs AS jsonb),CAST(:qualities AS jsonb),:enabled)"""),
                {
                    "id": model_id,
                    "provider": body.provider_id,
                    "name": body.name,
                    "api": body.api_identifier,
                    "version": body.version,
                    "inputs": _json(body.input_formats),
                    "outputs": _json(body.output_formats),
                    "qualities": _json(body.quality_levels),
                    "enabled": body.enabled,
                },
            )
            connection.execute(
                text("""INSERT INTO cost_lab.model_quality_mapping(mapping_id,model_id,profile_id,supported,request_parameters)
                SELECT gen_random_uuid(),:model,profile_id,true,'{}'::jsonb FROM cost_lab.quality_profiles WHERE code=ANY(:levels)"""),
                {"model": model_id, "levels": body.quality_levels},
            )
            connection.execute(
                text("""INSERT INTO cost_lab.model_pricing
                (pricing_id,model_id,effective_at,components)
                VALUES(:id,:model,now(),CAST(:components AS jsonb))"""),
                {"id": pricing_id, "model": model_id, "components": _json(components)},
            )
        return {"model_id": model_id, "pricing_id": pricing_id, "name": body.name}

    @app.put("/api/cost-lab/models-with-pricing/{model_id}")
    def update_model_with_pricing(
        model_id: UUID, body: ModelWithPricingBody, _: Auth
    ) -> dict[str, Any]:
        pricing_id = uuid4()
        components = _model_pricing_components(body)
        with service.engine.begin() as connection:
            updated = connection.execute(
                text("""UPDATE cost_lab.ai_models SET provider_id=:provider,name=:name,
                api_identifier=:api,version=:version,input_formats=CAST(:inputs AS jsonb),
                output_formats=CAST(:outputs AS jsonb),quality_levels=CAST(:qualities AS jsonb),
                enabled=:enabled,updated_at=now() WHERE model_id=:id RETURNING model_id"""),
                {
                    "id": model_id,
                    "provider": body.provider_id,
                    "name": body.name,
                    "api": body.api_identifier,
                    "version": body.version,
                    "inputs": _json(body.input_formats),
                    "outputs": _json(body.output_formats),
                    "qualities": _json(body.quality_levels),
                    "enabled": body.enabled,
                },
            ).scalar_one_or_none()
            if updated is None:
                raise HTTPException(404, "Model not found")
            connection.execute(
                text("""INSERT INTO cost_lab.model_pricing
                (pricing_id,model_id,effective_at,components)
                VALUES(:id,:model,now(),CAST(:components AS jsonb))"""),
                {"id": pricing_id, "model": model_id, "components": _json(components)},
            )
        return {"model_id": model_id, "pricing_id": pricing_id, "name": body.name}

    @app.post("/api/cost-lab/models/{model_id}/pricing", status_code=201)
    def add_pricing(model_id: UUID, body: PricingBody, _: Auth) -> dict[str, Any]:
        allowed = {
            "text_input_tokens",
            "image_input_tokens",
            "cached_input_tokens",
            "image_output_tokens",
            "output_images",
            "megapixels",
            "runtime_seconds",
            "requests",
        }
        if any(
            not str(item.get("unit", "")).startswith("custom:") and item.get("unit") not in allowed
            for item in body.components
        ):
            raise HTTPException(422, "Unsupported pricing unit")
        pricing_id = uuid4()
        with service.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO cost_lab.model_pricing(pricing_id,model_id,effective_at,components) VALUES(:id,:model,:effective,CAST(:components AS jsonb))"
                ),
                {
                    "id": pricing_id,
                    "model": model_id,
                    "effective": body.effective_at,
                    "components": _json(body.components),
                },
            )
        return {"pricing_id": pricing_id}

    @app.post("/api/cost-lab/models/{model_id}/test")
    def test_model(
        model_id: UUID,
        _: Auth,
        prompt: Annotated[str, Form(min_length=1, max_length=4000)],
        quality: Annotated[Literal["LOW", "MEDIUM", "HIGH"], Form()] = "MEDIUM",
        images: Annotated[list[UploadFile] | None, File()] = None,
    ) -> dict[str, Any]:
        uploads = images or []
        if len(uploads) > 2:
            raise HTTPException(422, "A model test accepts at most two input images")
        image_bytes: list[bytes] = []
        for upload in uploads:
            if upload.content_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise HTTPException(415, "Test images must be PNG, JPEG, or WebP")
            content = upload.file.read(15 * 1024 * 1024 + 1)
            if len(content) > 15 * 1024 * 1024:
                raise HTTPException(413, "Each test image must be 15 MB or smaller")
            try:
                with Image.open(BytesIO(content)) as candidate:
                    candidate.verify()
            except Exception as error:
                raise HTTPException(422, "One of the test images is invalid") from error
            image_bytes.append(content)

        with service.engine.begin() as connection:
            model = (
                connection.execute(
                    text("""SELECT m.api_identifier,m.enabled model_enabled,p.*,
                    q.settings quality_settings,mapping.provider_quality,mapping.request_parameters
                    FROM cost_lab.ai_models m JOIN cost_lab.model_providers p USING(provider_id)
                    JOIN cost_lab.quality_profiles q ON q.code=:quality
                    LEFT JOIN cost_lab.model_quality_mapping mapping
                      ON mapping.model_id=m.model_id AND mapping.profile_id=q.profile_id
                    WHERE m.model_id=:id"""),
                    {"id": model_id, "quality": quality},
                )
                .mappings()
                .one_or_none()
            )
        if model is None:
            raise HTTPException(404, "Model not found")
        if not model["model_enabled"]:
            raise HTTPException(422, "Enable this model before generation testing")
        adapter_type = _provider_adapter(dict(model))
        parameters = dict(model["quality_settings"] or {}) | dict(model["request_parameters"] or {})
        if model["provider_quality"]:
            parameters["quality"] = model["provider_quality"]
        parameters |= _provider_quality_parameters(dict(model), model["api_identifier"], quality)
        try:
            adapter = adapter_type(
                model["api_base_url"],
                service.secret_for(dict(model)),
                int(os.getenv("COST_LAB_REQUEST_TIMEOUT_SECONDS", "120")),
            )
            result = (
                adapter.generate(
                    model=model["api_identifier"],
                    prompt=prompt,
                    images=image_bytes,
                    parameters=parameters,
                )
                if image_bytes
                else adapter.generate_from_prompt(
                    model=model["api_identifier"], prompt=prompt, parameters=parameters
                )
            )
        except BFLUpstreamError as error:
            raise HTTPException(error.status_code, detail=error.public_detail()) from error
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as error:
            raise HTTPException(502, f"Model test failed: {str(error)[:1000]}") from error

        folder = service.settings.storage_root / "model-tests" / str(model_id)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(BytesIO(result.image_bytes)) as generated:
                extension = ".png" if generated.format == "PNG" else ".jpg"
                generated.verify()
        except Exception as error:
            raise HTTPException(502, "Provider returned an invalid image") from error
        relative_path = (
            folder / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}{extension}"
        ).relative_to(service.settings.storage_root)
        (service.settings.storage_root / relative_path).write_bytes(result.image_bytes)
        input_paths: list[str] = []
        test_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        for index, content in enumerate(image_bytes):
            with Image.open(BytesIO(content)) as source:
                input_extension = (
                    ".png"
                    if source.format == "PNG"
                    else (".webp" if source.format == "WEBP" else ".jpg")
                )
            input_path = (folder / f"{test_stamp}-input-{index + 1}{input_extension}").relative_to(
                service.settings.storage_root
            )
            (service.settings.storage_root / input_path).write_bytes(content)
            input_paths.append(str(input_path))
        with service.engine.begin() as connection:
            connection.execute(
                text("""UPDATE cost_lab.ai_models SET tested_at=now(),tested_method='GENERATED',
                test_prompt=:prompt,test_output_path=:path,test_input_paths=CAST(:inputs AS jsonb),
                test_provider_request_id=:request,
                updated_at=now() WHERE model_id=:id"""),
                {
                    "id": model_id,
                    "prompt": prompt,
                    "path": str(relative_path),
                    "inputs": _json(input_paths),
                    "request": result.request_id,
                },
            )
            connection.execute(
                text("""INSERT INTO cost_lab.audit_events
                (event_id,action,target_type,target_id,metadata)
                VALUES(:event,'MODEL_GENERATION_TEST_SUCCEEDED','AI_MODEL',:id,CAST(:metadata AS jsonb))"""),
                {
                    "event": uuid4(),
                    "id": model_id,
                    "metadata": _json({"quality": quality, "input_image_count": len(image_bytes)}),
                },
            )
        return {
            "tested": True,
            "tested_method": "GENERATED",
            "image_url": f"/api/cost-lab/models/{model_id}/test-image",
            "input_urls": [
                f"/api/cost-lab/models/{model_id}/test-input/{index}"
                for index in range(len(input_paths))
            ],
            "prompt": prompt,
            "latency_ms": result.latency_ms,
        }

    @app.put("/api/cost-lab/models/{model_id}/test-status")
    def update_model_test_status(
        model_id: UUID, body: ModelTestStatusBody, _: Auth
    ) -> dict[str, Any]:
        with service.engine.begin() as connection:
            updated = connection.execute(
                text("""UPDATE cost_lab.ai_models SET
                tested_at=CASE WHEN :tested THEN now() ELSE NULL END,
                tested_method=CASE WHEN :tested THEN 'MANUAL' ELSE NULL END,
                test_prompt=CASE WHEN :tested THEN test_prompt ELSE NULL END,
                test_output_path=CASE WHEN :tested THEN test_output_path ELSE NULL END,
                test_input_paths=CASE WHEN :tested THEN test_input_paths ELSE '[]'::jsonb END,
                test_provider_request_id=CASE WHEN :tested THEN test_provider_request_id ELSE NULL END,
                updated_at=now() WHERE model_id=:id RETURNING model_id"""),
                {"id": model_id, "tested": body.tested},
            ).scalar_one_or_none()
            if updated is None:
                raise HTTPException(404, "Model not found")
            connection.execute(
                text("""INSERT INTO cost_lab.audit_events
                (event_id,action,target_type,target_id,metadata)
                VALUES(:event,'MODEL_TEST_STATUS_UPDATED','AI_MODEL',:id,CAST(:metadata AS jsonb))"""),
                {
                    "event": uuid4(),
                    "id": model_id,
                    "metadata": _json({"tested": body.tested, "method": "MANUAL"}),
                },
            )
        return {"model_id": model_id, "tested": body.tested}

    @app.get("/api/cost-lab/models/{model_id}/test-image")
    def model_test_image(model_id: UUID, _: Auth) -> FileResponse:
        with service.engine.begin() as connection:
            path = connection.execute(
                text("SELECT test_output_path FROM cost_lab.ai_models WHERE model_id=:id"),
                {"id": model_id},
            ).scalar_one_or_none()
        if not path:
            raise HTTPException(404, "Model test image not found")
        resolved = (service.settings.storage_root / path).resolve()
        if (
            service.settings.storage_root.resolve() not in resolved.parents
            or not resolved.is_file()
        ):
            raise HTTPException(404, "Model test image not found")
        return FileResponse(resolved)

    @app.get("/api/cost-lab/models/{model_id}/test-input/{input_index}")
    def model_test_input(model_id: UUID, input_index: int, _: Auth) -> FileResponse:
        if input_index not in {0, 1}:
            raise HTTPException(404, "Model test input image not found")
        with service.engine.begin() as connection:
            paths = connection.execute(
                text("SELECT test_input_paths FROM cost_lab.ai_models WHERE model_id=:id"),
                {"id": model_id},
            ).scalar_one_or_none()
        if not paths or input_index >= len(paths):
            raise HTTPException(404, "Model test input image not found")
        resolved = (service.settings.storage_root / paths[input_index]).resolve()
        if (
            service.settings.storage_root.resolve() not in resolved.parents
            or not resolved.is_file()
        ):
            raise HTTPException(404, "Model test input image not found")
        return FileResponse(resolved)

    @app.get("/api/cost-lab/quality-profiles")
    def profiles(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            return {
                "profiles": _rows(
                    connection.execute(
                        text("SELECT * FROM cost_lab.quality_profiles ORDER BY code")
                    )
                )
            }

    @app.put("/api/cost-lab/quality-profiles/{code}")
    def update_profile(
        code: Literal["LOW", "MEDIUM", "HIGH"], body: QualityBody, _: Auth
    ) -> dict[str, Any]:
        with service.engine.begin() as connection:
            row = connection.execute(
                text("""UPDATE cost_lab.quality_profiles SET width=:width,height=:height,compression_quality=:compression,
                output_resolution=:resolution,settings=CAST(:settings AS jsonb),updated_at=now() WHERE code=:code RETURNING profile_id"""),
                {
                    "width": body.width,
                    "height": body.height,
                    "compression": body.compression_quality,
                    "resolution": body.output_resolution,
                    "settings": _json(body.settings),
                    "code": code,
                },
            ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Profile not found")
        return {"profile_id": row, "code": code}

    @app.put("/api/cost-lab/models/{model_id}/quality-mapping")
    def quality_mapping(model_id: UUID, body: MappingBody, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.model_quality_mapping(mapping_id,model_id,profile_id,supported,provider_quality,request_parameters)
                VALUES(:id,:model,:profile,:supported,:quality,CAST(:params AS jsonb)) ON CONFLICT(model_id,profile_id) DO UPDATE SET
                supported=excluded.supported,provider_quality=excluded.provider_quality,request_parameters=excluded.request_parameters"""),
                {
                    "id": uuid4(),
                    "model": model_id,
                    "profile": body.profile_id,
                    "supported": body.supported,
                    "quality": body.provider_quality,
                    "params": _json(body.request_parameters),
                },
            )
        return {"saved": True}

    @app.get("/api/cost-lab/knowledge")
    def knowledge(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            items = _rows(
                connection.execute(
                    text("""SELECT knowledge_id,source_type,title,original_filename,mime_type,
                    size_bytes,content_hash,created_at,
                    CASE WHEN content_text IS NULL THEN NULL ELSE left(content_text,240) END preview
                    FROM cost_lab.knowledge_items ORDER BY created_at DESC""")
                )
            )
        return {"items": items}

    @app.post("/api/cost-lab/knowledge/text", status_code=201)
    def add_knowledge_text(body: KnowledgeTextBody, _: Auth) -> dict[str, Any]:
        content = body.content.strip()
        if not content:
            raise HTTPException(422, "Knowledge text cannot be empty")
        formatted_html, formatter_model, formatting_usage = _format_knowledge_with_llm(content)
        knowledge_id = uuid4()
        encoded = content.encode("utf-8")
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.knowledge_items
                (knowledge_id,source_type,title,content_text,formatted_html,formatter_model,
                formatting_usage,size_bytes,content_hash)
                VALUES(:id,'TEXT',:title,:content,:formatted,:model,CAST(:usage AS jsonb),:size,:hash)"""),
                {
                    "id": knowledge_id,
                    "title": body.title.strip(),
                    "content": content,
                    "formatted": formatted_html,
                    "model": formatter_model,
                    "usage": _json(formatting_usage),
                    "size": len(encoded),
                    "hash": hashlib.sha256(encoded).hexdigest(),
                },
            )
        return {"knowledge_id": knowledge_id, "source_type": "TEXT"}

    @app.post("/api/cost-lab/knowledge/pdf", status_code=201)
    async def add_knowledge_pdf(
        title: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        _: Auth,
    ) -> dict[str, Any]:
        if not title.strip():
            raise HTTPException(422, "Title is required")
        content = await file.read()
        if not content:
            raise HTTPException(422, "PDF cannot be empty")
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(413, "PDF exceeds 25 MB")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "Invalid PDF file")
        knowledge_id = uuid4()
        folder = actual.storage_root / "knowledge" / str(knowledge_id)
        folder.mkdir(parents=True)
        stored = folder / "source.pdf"
        stored.write_bytes(content)
        relative_path = str(stored.relative_to(actual.storage_root))
        try:
            with service.engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO cost_lab.knowledge_items
                    (knowledge_id,source_type,title,file_path,original_filename,mime_type,
                    size_bytes,content_hash) VALUES(:id,'PDF',:title,:path,:filename,
                    'application/pdf',:size,:hash)"""),
                    {
                        "id": knowledge_id,
                        "title": title.strip(),
                        "path": relative_path,
                        "filename": (file.filename or "knowledge.pdf")[:512],
                        "size": len(content),
                        "hash": hashlib.sha256(content).hexdigest(),
                    },
                )
        except Exception:
            stored.unlink(missing_ok=True)
            folder.rmdir()
            raise
        return {"knowledge_id": knowledge_id, "source_type": "PDF"}

    @app.get("/api/cost-lab/knowledge/{knowledge_id}/content")
    def knowledge_content(knowledge_id: UUID, _: Auth) -> Response:
        with service.engine.begin() as connection:
            item = (
                connection.execute(
                    text("""SELECT source_type,title,content_text,formatted_html,file_path,
                original_filename,created_at
                FROM cost_lab.knowledge_items WHERE knowledge_id=:id"""),
                    {"id": knowledge_id},
                )
                .mappings()
                .one_or_none()
            )
        if item is None:
            raise HTTPException(404, "Knowledge item not found")
        if item["source_type"] == "TEXT":
            title = html.escape(str(item["title"]))
            content = str(item["formatted_html"] or _knowledge_html(str(item["content_text"])))
            added = item["created_at"].astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")
            return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Wearo Cost Lab</title><style>
:root{{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#2d1830;background:#f7f2f5}}
*{{box-sizing:border-box}}body{{margin:0;padding:clamp(1rem,4vw,3.5rem);background:radial-gradient(circle at 90% 0,#f2dfb8,transparent 30%),#f7f2f5;line-height:1.7}}
main{{width:min(100%,56rem);margin:auto;overflow:hidden;border:1px solid #dfc18c;border-radius:1.2rem;background:#fffdf9;box-shadow:0 1.5rem 4rem rgb(45 24 48/.12)}}
header{{padding:clamp(1.4rem,4vw,2.6rem);border-bottom:1px solid #ead8b7;background:linear-gradient(145deg,#fffdf8,#f6e5c4)}}
.eyebrow{{margin:0 0 .4rem;color:#9a682d;font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
h1{{margin:0;color:#3b173d;font-family:Georgia,serif;font-size:clamp(1.8rem,4vw,3rem);font-weight:500;line-height:1.15}}
.meta{{margin:.65rem 0 0;color:#806578;font-size:.78rem}}article{{padding:clamp(1.4rem,4vw,2.8rem)}}
.content{{color:#382d38;font-family:Georgia,serif;font-size:clamp(1rem,2vw,1.12rem);overflow-wrap:anywhere}}
.content p{{margin:0 0 1.2em}}.content p:last-child{{margin-bottom:0}}
.content h2,.content h3,.content h4{{margin:1.6em 0 .55em;color:#3b173d;line-height:1.25}}.content h2:first-child,.content h3:first-child{{margin-top:0}}
.content ul,.content ol{{margin:.4em 0 1.3em;padding-left:1.5em}}.content li{{margin:.35em 0;padding-left:.25em}}
.content li::marker{{color:#a26f31;font-weight:700}}blockquote{{margin:1.2em 0;padding:.8em 1.1em;border-left:3px solid #c9974d;background:#fff8e9;color:#684f62;font-style:italic}}
</style></head><body><main><header><p class="eyebrow">Wearo Model Cost Lab · Knowledge</p><h1>{title}</h1><p class="meta">Added {added}</p></header><article><div class="content">{content}</div></article></main></body></html>""")
        resolved = (actual.storage_root / item["file_path"]).resolve()
        if actual.storage_root.resolve() not in resolved.parents or not resolved.is_file():
            raise HTTPException(404, "Knowledge PDF not found")
        return FileResponse(
            resolved,
            media_type="application/pdf",
            filename=item["original_filename"] or "knowledge.pdf",
            content_disposition_type="inline",
        )

    @app.delete("/api/cost-lab/knowledge/{knowledge_id}", status_code=204)
    def delete_knowledge(knowledge_id: UUID, _: Auth) -> Response:
        with service.engine.begin() as connection:
            file_path = connection.execute(
                text("""DELETE FROM cost_lab.knowledge_items WHERE knowledge_id=:id
                RETURNING file_path"""),
                {"id": knowledge_id},
            ).scalar_one_or_none()
        if file_path:
            resolved = (actual.storage_root / file_path).resolve()
            if actual.storage_root.resolve() in resolved.parents and resolved.is_file():
                resolved.unlink()
                try:
                    resolved.parent.rmdir()
                except OSError:
                    pass
        return Response(status_code=204)

    @app.get("/api/cost-lab/assets")
    def assets(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            items = _rows(
                connection.execute(
                    text(
                        "SELECT * FROM cost_lab.benchmark_assets WHERE replaced_at IS NULL ORDER BY kind,created_at"
                    )
                )
            )
        for item in items:
            item["url"] = f"/api/cost-lab/assets/{item['asset_id']}/content"
        return {"assets": items}

    @app.post("/api/cost-lab/assets", status_code=201)
    async def upload_asset(
        kind: Annotated[Literal["PERSON", "JEWELLERY", "BLOUSE", "SAREE", "DRESS"], Form()],
        name: Annotated[str, Form()],
        complexity: Annotated[Literal["SIMPLE", "MEDIUM", "COMPLEX"], Form()],
        authorized: Annotated[bool, Form()],
        file: Annotated[UploadFile, File()],
        _: Auth,
    ) -> dict[str, Any]:
        if not authorized:
            raise HTTPException(422, "Authorization for the test image must be confirmed")
        content = await file.read()
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(413, "Image exceeds 15 MB")
        try:
            source = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
        except Exception as error:
            raise HTTPException(422, "Invalid image") from error
        asset_id = uuid4()
        folder = actual.storage_root / "assets" / str(asset_id)
        folder.mkdir(parents=True)
        original = folder / "original.jpg"
        source.save(original, "JPEG", quality=96)
        variants: dict[str, str] = {}
        with service.engine.begin() as connection:
            profiles = (
                connection.execute(
                    text(
                        "SELECT code,width,height,compression_quality FROM cost_lab.quality_profiles"
                    )
                )
                .mappings()
                .all()
            )
        for profile in profiles:
            target = folder / f"{profile['code'].lower()}.jpg"
            image = source.copy()
            image.thumbnail((profile["width"], profile["height"]), Image.Resampling.LANCZOS)
            image.save(target, "JPEG", quality=profile["compression_quality"], optimize=True)
            variants[profile["code"]] = str(target.relative_to(actual.storage_root))
        digest = hashlib.sha256(content).hexdigest()
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.benchmark_assets(asset_id,kind,name,original_path,variants,content_hash,authorized,complexity)
                VALUES(:id,:kind,:name,:path,CAST(:variants AS jsonb),:hash,true,:complexity)"""),
                {
                    "id": asset_id,
                    "kind": kind,
                    "name": name,
                    "path": str(original.relative_to(actual.storage_root)),
                    "variants": _json(variants),
                    "hash": digest,
                    "complexity": complexity,
                },
            )
        return {"asset_id": asset_id, "variants": variants}

    @app.patch("/api/cost-lab/assets/{asset_id}/complexity")
    def update_asset_complexity(
        asset_id: UUID, body: AssetComplexityBody, _: Auth
    ) -> dict[str, Any]:
        with service.engine.begin() as connection:
            updated = connection.execute(text("""UPDATE cost_lab.benchmark_assets
            SET complexity=:complexity WHERE asset_id=:id AND replaced_at IS NULL
            RETURNING asset_id,complexity"""),
                {"id": asset_id, "complexity": body.complexity}).mappings().one_or_none()
        if updated is None:
            raise HTTPException(404, "Active dataset image not found")
        return dict(updated)

    @app.get("/api/cost-lab/assets/{asset_id}/content")
    def asset_content(asset_id: UUID, _: Auth, quality: str | None = None) -> FileResponse:
        normalized_quality = quality.upper() if quality else None
        if normalized_quality and normalized_quality not in {"LOW", "MEDIUM", "HIGH"}:
            raise HTTPException(422, "Unsupported dataset quality")
        with service.engine.begin() as connection:
            asset = (
                connection.execute(
                    text(
                        "SELECT original_path,variants FROM cost_lab.benchmark_assets WHERE asset_id=:id"
                    ),
                    {"id": asset_id},
                )
                .mappings()
                .one_or_none()
            )
        if not asset:
            raise HTTPException(404, "Asset not found")
        path = (
            dict(asset["variants"] or {}).get(normalized_quality)
            if normalized_quality
            else asset["original_path"]
        )
        if not path:
            raise HTTPException(404, "Dataset quality variant not found")
        resolved = (actual.storage_root / path).resolve()
        if actual.storage_root.resolve() not in resolved.parents:
            raise HTTPException(400, "Invalid asset path")
        return FileResponse(resolved)

    @app.delete("/api/cost-lab/assets/{asset_id}", status_code=204)
    def delete_asset(asset_id: UUID, _: Auth) -> Response:
        # Keep the files and row for historical benchmark reproducibility, but remove the
        # asset from the active dataset and all future benchmark selections.
        with service.engine.begin() as connection:
            removed = connection.execute(
                text("""UPDATE cost_lab.benchmark_assets SET replaced_at=now()
                WHERE asset_id=:id AND replaced_at IS NULL RETURNING asset_id"""),
                {"id": asset_id},
            ).scalar_one_or_none()
        if removed is None:
            raise HTTPException(404, "Active dataset image not found")
        return Response(status_code=204)

    @app.get("/api/cost-lab/dataset-generations")
    def dataset_generations(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            jobs = _rows(
                connection.execute(
                    text("""SELECT j.*,m.name model_name,p.name provider_name
                    FROM cost_lab.dataset_generation_jobs j
                    JOIN cost_lab.ai_models m USING(model_id)
                    JOIN cost_lab.model_providers p USING(provider_id)
                    ORDER BY j.created_at DESC LIMIT 20""")
                )
            )
        return {"jobs": jobs}

    @app.post("/api/cost-lab/dataset-generations", status_code=202)
    def create_dataset_generation(body: DatasetGenerationBody, _: Auth) -> dict[str, Any]:
        direction = (body.direction or "").strip()
        custom_prompt = (body.prompt or "").strip()
        direction_suffix = (
            f" Additional dataset direction from the evaluator: {direction}" if direction else ""
        )
        complexity_suffix = (
            f" Input complexity must be {body.complexity.lower()}. "
            "Simple means minimal details and plain construction; medium means moderate detail; "
            "complex means intricate patterns, layered construction, embroidery, stones, or fine detail."
        )
        dress_styles = [
            "evening gown",
            "summer midi dress",
            "formal sheath dress",
            "floral maxi dress",
            "cocktail dress",
            "A-line day dress",
            "wrap dress",
            "embroidered festive dress",
            "minimalist shift dress",
            "flowing resort dress",
        ]
        prompts: list[tuple[str, str]] = []
        kind = body.category
        count = body.count
        for index in range(count):
            if custom_prompt:
                base = (
                    f"{custom_prompt} Dataset category: {kind}. Create visually distinct "
                    f"variation {index + 1} of {count}."
                )
            elif kind == "PERSON":
                base = (
                    f"Create a photorealistic full-body studio portrait of an adult Indian woman, "
                    f"person {index + 1} of {count}, standing naturally, front-facing, neutral "
                    "fitted base clothing, hands visible, plain warm-grey background, even soft "
                    "lighting, no jewellery, no text or logo. This is a synthetic reference "
                    "person for authorized virtual try-on testing."
                )
            elif kind == "JEWELLERY":
                base = (
                    f"Create a photorealistic isolated Indian jewellery product image, design "
                    f"{index + 1} of {count}, visually distinct in metal, stones and silhouette, "
                    "centered on a clean neutral background, ecommerce studio lighting, no "
                    "person, no text, no logo."
                )
            elif kind == "SAREE":
                base = (
                    f"Create a photorealistic isolated Indian saree product image, design "
                    f"{index + 1} of {count}, uniquely varied fabric, colour, weave and border, "
                    "neatly draped on a neutral invisible form, clean ecommerce background, no "
                    "person, no text, no logo."
                )
            else:
                style = dress_styles[index % len(dress_styles)]
                base = (
                    f"Create a photorealistic isolated women's {style} product image, design "
                    f"{index + 1} of {count}, with a distinct colour and fabric, front view on a "
                    "neutral invisible form, clean ecommerce studio background, no person, no "
                    "text, no logo."
                )
            prompts.append(
                (
                    kind,
                    base
                    + _single_item_dataset_instruction(kind, index, count)
                    + complexity_suffix
                    + direction_suffix,
                )
            )
        job_id = uuid4()
        with service.engine.begin() as connection:
            model = connection.execute(
                text("""SELECT m.model_id FROM cost_lab.ai_models m
                JOIN cost_lab.model_providers p USING(provider_id)
                WHERE m.model_id=:id AND m.enabled=true AND p.enabled=true"""),
                {"id": body.model_id},
            ).scalar_one_or_none()
            if model is None:
                raise HTTPException(404, "Enabled model and provider not found")
            active = connection.execute(
                text("""SELECT job_id FROM cost_lab.dataset_generation_jobs
                WHERE status IN ('QUEUED','RUNNING') LIMIT 1""")
            ).scalar_one_or_none()
            if active is not None:
                raise HTTPException(409, "A dataset generation job is already running")
            connection.execute(
                text("""INSERT INTO cost_lab.dataset_generation_jobs
                (job_id,model_id,status,total_items,generation_quality,direction,category,custom_prompt,complexity)
                VALUES(:id,:model,'QUEUED',:total,:quality,:direction,:category,:prompt,:complexity)"""),
                {
                    "id": job_id,
                    "model": body.model_id,
                    "total": len(prompts),
                    "quality": body.generation_quality,
                    "direction": direction or None,
                    "category": body.category,
                    "prompt": custom_prompt or None,
                    "complexity": body.complexity,
                },
            )
            for ordinal, (kind, prompt) in enumerate(prompts):
                connection.execute(
                    text("""INSERT INTO cost_lab.dataset_generation_items
                    (item_id,job_id,ordinal,kind,prompt,status)
                    VALUES(:id,:job,:ordinal,:kind,:prompt,'QUEUED')"""),
                    {
                        "id": uuid4(),
                        "job": job_id,
                        "ordinal": ordinal,
                        "kind": kind,
                        "prompt": prompt,
                    },
                )
        return {
            "job_id": job_id,
            "status": "QUEUED",
            "total_items": len(prompts),
            "generation_quality": body.generation_quality,
            "category": body.category,
            "complexity": body.complexity,
        }

    @app.post("/api/cost-lab/dataset-generations/{job_id}/cancel")
    def cancel_dataset_generation(job_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            requested = connection.execute(
                text("""UPDATE cost_lab.dataset_generation_jobs
                SET status='CANCEL_REQUESTED'
                WHERE job_id=:id AND status IN ('QUEUED','RUNNING') RETURNING job_id"""),
                {"id": job_id},
            ).scalar_one_or_none()
            if requested is None:
                raise HTTPException(409, "Dataset generation cannot be cancelled")
            connection.execute(
                text("""UPDATE cost_lab.dataset_generation_items
                SET status='CANCELLED',finished_at=now()
                WHERE job_id=:id AND status='QUEUED'"""),
                {"id": job_id},
            )
            status = connection.execute(
                text("""UPDATE cost_lab.dataset_generation_jobs j SET
                cancelled_items=(SELECT count(*) FROM cost_lab.dataset_generation_items i
                    WHERE i.job_id=j.job_id AND i.status='CANCELLED'),
                status=CASE WHEN EXISTS(
                    SELECT 1 FROM cost_lab.dataset_generation_items i
                    WHERE i.job_id=j.job_id AND i.status='PROCESSING'
                ) THEN 'CANCEL_REQUESTED' ELSE 'CANCELLED' END,
                finished_at=CASE WHEN EXISTS(
                    SELECT 1 FROM cost_lab.dataset_generation_items i
                    WHERE i.job_id=j.job_id AND i.status='PROCESSING'
                ) THEN NULL ELSE now() END
                WHERE job_id=:id RETURNING status"""),
                {"id": job_id},
            ).scalar_one()
        return {"job_id": job_id, "status": status}

    @app.post("/api/cost-lab/benchmarks", status_code=202)
    def create_benchmark(body: BenchmarkBody, _: Auth) -> dict[str, Any]:
        input_quality = body.input_quality
        output_quality = body.output_quality
        qualities = [output_quality]
        categories = [body.category]
        tryons_per_quality = body.image_count
        prompt_version = "wearo-preservation-priority-v7"
        prompt = (
            "Perform a photorealistic virtual try-on using exactly two images. IMAGE 1 (PERSON) is "
            "the original person photo and fixed output canvas. IMAGE 2 (PRODUCT) is the exact "
            "wearable to apply. Replace or add ONLY the target wearable in IMAGE 1 using the "
            "product from IMAGE 2. STRICT PRESERVATION — PERSON: keep the exact original face, "
            "identity, hair, skin tone, expression, glasses, facial hair, body shape, pose, hands, "
            "accessories, background, lighting, framing, composition, and aspect ratio. Never "
            "regenerate, beautify, or retouch the face. PRODUCT: preserve the exact colour, fabric "
            "texture, material, prints, patterns, embroidery, logos, stitching, neckline, sleeves, "
            "construction, and design. Never recolour, redesign, simplify, or invent details. EDIT "
            "REGION: modify only pixels necessary for the wearable and preserve every unaffected "
            "area of IMAGE 1. FIT AND REALISM: fit the wearable naturally to the existing body and "
            "pose with realistic folds, draping, shadows, and occlusion while keeping product "
            "colours and details faithful to IMAGE 2. OUTPUT: return one photorealistic image with "
            "IMAGE 1's original composition and aspect ratio, with no additional people, text, or "
            "watermarks. PRIORITY ORDER: exact person identity first, exact product appearance "
            "second, realistic wearable fit third. Never regenerate the entire person or scene. "
            "EDIT IMAGE 1; DO NOT RECREATE IT. Image 1 is the immutable base photograph and the "
            "only source for the person, face, body, pose, framing, lighting, and background. "
            "Perform a localized image edit by adding or replacing only the wearable region on "
            "Image 1. Do not generate a new portrait, compose the person into another image, "
            "redraw the person, reinterpret the photograph, or use Image 2 as the output canvas. "
            "The output must be the same photograph as Image 1 with the selected wearable applied. "
            "Preserve the face exactly and pixel-faithfully: identical identity, facial geometry, "
            "head shape, eyes, eyebrows, glasses, nose, mouth, moustache or beard, ears, skin "
            "texture, skin tone, expression, gaze, age, and all distinguishing features. Never "
            "synthesize, retouch, beautify, sharpen, restyle, or replace the face. Preserve the "
            "exact hair, hairline, neck, shoulder position, body structure, body proportions, "
            "silhouette outside the wearable, pose, hand and finger positions, leg and foot "
            "positions, camera angle, perspective, crop, resolution, background, floor, lighting, "
            "shadows, and every unrelated pixel from Image 1. Do not straighten, enlarge, slim, "
            "repose, recrop, recenter, or otherwise improve the person. Pixels outside the minimum "
            "anatomically necessary wearable and occlusion mask must remain unchanged. "
            "Create exactly one photorealistic virtual try-on from the two supplied reference "
            "images. Image 2 is the product "
            "reference. Determine from Image 2 whether the primary product is jewellery, a saree, "
            "or a dress, then follow only the matching instruction below within this same generation. "
            "For jewellery: extract only the jewellery product from Image 2 and place exactly one of "
            "it naturally on the anatomically correct location of the person in Image 1. Ignore and "
            "never copy any reference person, face, skin, hair, hands, arms, legs, feet, mannequin, "
            "display stand, support, clothing, or background from Image 2. "
            "First classify the exact jewellery type and intended wearing configuration from Image "
            "2, including whether it is a single item, matching pair, or coordinated set. Place "
            "every component only on its anatomically correct location at a realistic scale and "
            "orientation: earrings on the corresponding earlobes, nose jewellery on the correct "
            "nostril or septum, maang tikka and head jewellery at the hairline and forehead, "
            "necklaces around the neck and collarbone, brooches on the intended garment area, "
            "armlets on the upper arm, bangles and bracelets around the wrists, rings on the "
            "appropriate fingers, waist belts or chains around the waist, and anklets around the "
            "ankles. Preserve the exact item count and wearing arrangement; do not turn a single "
            "item into a pair, merge a pair into one item, or split, combine, or relocate set "
            "components. Respect occlusion and perspective so jewellery sits on the body rather "
            "than floating, embedding into skin, or hanging from the wrong body part. "
            "For a necklace, first infer its exact necklace type, original length, silhouette, "
            "width, curvature, chain-to-ornament ratio, pendant position, and intended wearing "
            "height from Image 2. Fit that same necklace closely and naturally around the neck in "
            "Image 1, following the neck and collarbone perspective. A short necklace, choker, "
            "collar necklace, or collarbone necklace must remain short and must not become a long "
            "chain or hang down onto the mid-chest. For earrings, preserve whether they are studs, "
            "hoops, drops, jhumkas, chandbalis, ear cuffs, or another design and retain their "
            "original drop length and orientation. For bangles, bracelets, rings, armlets, waist "
            "jewellery, and anklets, preserve the original circumference, width, stacking order, "
            "and body placement. Preserve the exact number, order, spacing, shape, and relative "
            "size of every link, motif, stone, bead, drop, clasp, chain, and pendant across all "
            "jewellery types. "
            "Preserve the exact metal color, stone colors, enamel colors, color placement, "
            "symmetry, proportions, and construction. Do not redesign, simplify, embellish, "
            "extend, duplicate, remove, recolor, or invent any jewellery component. Scale and "
            "curve only as required for anatomically realistic contact with the neck. "
            "For a saree: modify only the existing clothing area and the minimum adjacent occlusion "
            "boundary needed to apply the referenced saree with realistic pleats, pallu, drape, "
            "scale, and fabric behaviour. Do not regenerate the person underneath it. For a dress, "
            "shirt, T-shirt, blouse, trousers, jeans, or other apparel: replace only the existing "
            "garment pixels and the minimum edge pixels required for natural fit. Retain the exact "
            "person, face, body structure, pose, and visible non-garment areas from Image 1. For "
            "jewellery, overlay only the jewellery at the correct anatomical location; do not alter "
            "the face, hair, body, clothing, or background except for essential local occlusion. "
            "Treat Image 2 as the authoritative product appearance. Lock the product's exact "
            "colour and colour placement, including hue, saturation, brightness, contrast, "
            "undertone, gradients, panels, borders, prints, and embroidery colours. Do not "
            "recolour, colour-match to the person, apply a colour grade, brighten, darken, fade, "
            "wash out, or replace any product colour. Preserve the exact fabric and material "
            "identity, weave, knit, grain, texture, thickness, opacity, sheen, finish, drape, "
            "pattern scale, print, embroidery, stitching, seams, hems, buttons, pockets, neckline, "
            "sleeves, distressing, wash, stones, pendant, chain, construction, branding, and "
            "visible logo. Do not substitute a similar fabric or simplify product details. Only "
            "geometrically warp, fold, scale, and occlude the product as strictly necessary to fit "
            "the unchanged person. Lighting adaptation may add physically plausible local "
            "highlights and shadows, but the perceived base colour and material must remain the "
            "same as Image 2. Preserve the target person's identity, face, expression, hairstyle, skin "
            "tone, body, pose, hands, feet, camera framing, lighting, and background. Do not create "
            "another person, miniature person, mannequin, extra or missing body parts, duplicate "
            "products, black shapes, text, logos not present in the product, or unrelated objects. "
            "Keep all unrelated areas of Image 1 unchanged. Before returning, compare the result "
            "against Image 1 and verify that the face, head, body structure, pose, hands, legs, "
            "background, crop, and lighting are unchanged. Return only the locally edited Image 1."
        )
        selected_result: dict[str, Any] | None = None
        with service.engine.begin() as connection:
            model = (
                connection.execute(
                    text("SELECT * FROM cost_lab.ai_models WHERE model_id=:id AND enabled=true"),
                    {"id": body.model_id},
                )
                .mappings()
                .one_or_none()
            )
            pricing = (
                connection.execute(
                    text(
                        "SELECT * FROM cost_lab.model_pricing WHERE model_id=:id AND effective_at <= now() ORDER BY effective_at DESC LIMIT 1"
                    ),
                    {"id": body.model_id},
                )
                .mappings()
                .one_or_none()
            )
            mappings = _rows(
                connection.execute(
                    text("""SELECT q.*,m.supported,m.provider_quality,m.request_parameters FROM cost_lab.quality_profiles q
                LEFT JOIN cost_lab.model_quality_mapping m ON m.profile_id=q.profile_id AND m.model_id=:model WHERE q.code=ANY(:qualities)"""),
                    {"model": body.model_id, "qualities": qualities},
                )
            )
            people = _rows(
                connection.execute(
                    text(
                        """SELECT asset_id,content_hash FROM cost_lab.benchmark_assets
                        WHERE kind='PERSON' AND replaced_at IS NULL
                        AND (CAST(:person_id AS uuid) IS NULL OR asset_id=CAST(:person_id AS uuid))
                        ORDER BY asset_id"""
                    ),
                    {"person_id": body.person_asset_id},
                )
            )
            if body.person_result_tryon_id is not None:
                selected_result_row = (
                    connection.execute(
                        text("""SELECT t.tryon_id,t.output_path,c.ordinal,r.run_id
                    FROM cost_lab.tryon_runs t
                    JOIN cost_lab.benchmark_combinations c
                      ON c.combination_id=t.combination_id
                    JOIN cost_lab.benchmark_runs r ON r.run_id=t.run_id
                    WHERE t.tryon_id=:id AND t.status='SUCCEEDED' AND t.output_path IS NOT NULL"""),
                        {"id": body.person_result_tryon_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                selected_result = dict(selected_result_row) if selected_result_row else None
            selected_product_ids = body.product_asset_ids or (
                [body.product_asset_id] if body.product_asset_id is not None else []
            )
            product_filter = " AND asset_id=ANY(:product_ids)" if selected_product_ids else ""
            products = _rows(connection.execute(text(
                """SELECT asset_id,kind,content_hash FROM cost_lab.benchmark_assets
                WHERE kind=ANY(:categories) AND replaced_at IS NULL
                AND complexity=:complexity"""
                + product_filter + " ORDER BY kind,asset_id"
            ), {"categories": categories, "product_ids": selected_product_ids,
                "complexity": body.input_complexity}))
        if model is None:
            raise HTTPException(404, "Enabled model not found")
        if body.person_asset_id is not None and body.person_result_tryon_id is not None:
            raise HTTPException(422, "Select either a dataset person or a result image, not both")
        if body.person_result_tryon_id is not None and selected_result is None:
            raise HTTPException(422, "Selected result image is not available")
        if selected_product_ids and len(products) != len(selected_product_ids):
            raise HTTPException(422, "One or more selected product images are unavailable in this category")
        if any(item["supported"] is not True for item in mappings) or len(mappings) != len(
            qualities
        ):
            raise HTTPException(422, "One or more model/quality combinations are unsupported")
        if body.person_asset_id is not None and not people:
            raise HTTPException(422, "Selected person image is not available in the active dataset")
        if not products or (not people and selected_result is None):
            raise HTTPException(422, "Dataset needs person and product assets")
        derived_person: dict[str, Any] | None = None
        if selected_result is not None:
            source_path = (actual.storage_root / selected_result["output_path"]).resolve()
            if (
                actual.storage_root.resolve() not in source_path.parents
                or not source_path.is_file()
            ):
                raise HTTPException(422, "Selected result image file is not available")
            try:
                source = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
            except Exception as error:
                raise HTTPException(422, "Selected result image is invalid") from error
            derived_id = uuid4()
            folder = actual.storage_root / "assets" / str(derived_id)
            folder.mkdir(parents=True)
            original = folder / "original.jpg"
            source.save(original, "JPEG", quality=96)
            variants: dict[str, str] = {}
            for profile in mappings:
                target = folder / f"{str(profile['code']).lower()}.jpg"
                image = source.copy()
                image.thumbnail((profile["width"], profile["height"]), Image.Resampling.LANCZOS)
                image.save(
                    target,
                    "JPEG",
                    quality=profile["compression_quality"],
                    optimize=True,
                )
                variants[str(profile["code"])] = str(target.relative_to(actual.storage_root))
            content = source_path.read_bytes()
            derived_person = {
                "asset_id": derived_id,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "original_path": str(original.relative_to(actual.storage_root)),
                "variants": variants,
                "name": f"Result image {selected_result['tryon_id']}",
            }
            people = [derived_person]
        components = list(pricing["components"]) if pricing else []
        fixed_components = [
            item for item in components if item.get("unit") in {"requests", "output_images"}
        ]
        total_jobs = tryons_per_quality
        estimated = (
            calculate_cost(
                {"requests": 1, "output_images": 1, "output_quality": output_quality},
                fixed_components,
            )
            * total_jobs
            if fixed_components
            else None
        )
        seed = secrets.randbits(63)
        fingerprint = hashlib.sha256(
            "|".join(sorted(item["content_hash"] for item in people + products)).encode()
        ).hexdigest()
        run_id = uuid4()
        combinations = [
            (uuid4(), *item)
            for item in reproducible_combinations(
                people, products, [input_quality], tryons_per_quality, seed
            )
        ]
        with service.engine.begin() as connection:
            if derived_person is not None:
                connection.execute(
                    text("""INSERT INTO cost_lab.benchmark_assets
                    (asset_id,kind,name,original_path,variants,content_hash,authorized,replaced_at)
                    VALUES(:id,'PERSON',:name,:path,CAST(:variants AS jsonb),:hash,true,now())"""),
                    {
                        "id": derived_person["asset_id"],
                        "name": derived_person["name"],
                        "path": derived_person["original_path"],
                        "variants": _json(derived_person["variants"]),
                        "hash": derived_person["content_hash"],
                    },
                )
            connection.execute(
                text("""INSERT INTO cost_lab.benchmark_runs(run_id,model_id,category,qualities,tryons_per_quality,random_seed,prompt,prompt_version,
                dataset_fingerprint,pricing_snapshot,quality_snapshot,status,estimated_max_usd,spending_limit_usd,confirmed_at,total_jobs,input_complexity)
                VALUES(:id,:model,:category,CAST(:qualities AS jsonb),:count,:seed,:prompt,:version,:fingerprint,CAST(:pricing AS jsonb),CAST(:quality AS jsonb),
                'QUEUED',:estimated,:limit,now(),:total,:complexity)"""),
                {
                    "id": run_id,
                    "model": body.model_id,
                    "category": body.category,
                    "qualities": _json(qualities),
                    "count": tryons_per_quality,
                    "seed": seed,
                    "prompt": prompt,
                    "version": prompt_version,
                    "fingerprint": fingerprint,
                    "pricing": _json(components),
                    "quality": _json(mappings),
                    "estimated": estimated,
                    "limit": None,
                    "total": total_jobs,
                    "complexity": body.input_complexity,
                },
            )
            for ordinal, (combination_id, quality, person, product) in enumerate(combinations):
                connection.execute(
                    text(
                        "INSERT INTO cost_lab.benchmark_combinations(combination_id,run_id,ordinal,quality,output_quality,person_asset_id,product_asset_id) VALUES(:id,:run,:ordinal,:quality,:output_quality,:person,:product)"
                    ),
                    {
                        "id": combination_id,
                        "run": run_id,
                        "ordinal": ordinal,
                        "quality": quality,
                        "output_quality": output_quality,
                        "person": person,
                        "product": product,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO cost_lab.tryon_runs(tryon_id,run_id,combination_id,status) VALUES(:id,:run,:combination,'QUEUED')"
                    ),
                    {"id": uuid4(), "run": run_id, "combination": combination_id},
                )
        return {
            "run_id": run_id,
            "status": "QUEUED",
            "total_jobs": total_jobs,
            "estimated_max_usd": estimated,
            "random_seed": seed,
        }

    @app.get("/api/cost-lab/benchmarks")
    def benchmarks(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            return {
                "runs": _rows(
                    connection.execute(
                        text("""SELECT r.*,m.name model_name,p.name provider_name,
                CASE WHEN count(DISTINCT c.quality)>1 THEN 'MIXED' ELSE min(c.quality) END input_quality,
                CASE WHEN count(DISTINCT c.output_quality)>1 THEN 'MIXED' ELSE min(c.output_quality) END output_quality
                FROM cost_lab.benchmark_runs r JOIN cost_lab.ai_models m USING(model_id)
                JOIN cost_lab.model_providers p USING(provider_id)
                LEFT JOIN cost_lab.benchmark_combinations c USING(run_id)
                GROUP BY r.run_id,m.name,p.name ORDER BY r.created_at DESC LIMIT 200""")
                    )
                )
            }

    @app.post("/api/cost-lab/benchmarks/{run_id}/cancel")
    def cancel(run_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            status = connection.execute(
                text("""UPDATE cost_lab.benchmark_runs SET status='CANCEL_REQUESTED'
                WHERE run_id=:id AND status IN ('QUEUED','RUNNING') RETURNING status"""),
                {"id": run_id},
            ).scalar_one_or_none()
        if status is None:
            raise HTTPException(409, "Benchmark cannot be cancelled")
        return {"run_id": run_id, "status": status}

    @app.get("/api/cost-lab/results")
    def results(
        _: Auth,
        provider_id: UUID | None = None,
        model_id: UUID | None = None,
        quality: str | None = None,
        input_quality: str | None = None,
        output_quality: str | None = None,
    ) -> dict[str, Any]:
        filters = ["1=1"]
        params: dict[str, Any] = {}
        if provider_id:
            filters.append("p.provider_id=:provider")
            params["provider"] = provider_id
        if model_id:
            filters.append("m.model_id=:model")
            params["model"] = model_id
        if input_quality:
            filters.append("c.quality=:input_quality")
            params["input_quality"] = input_quality
        selected_output_quality = output_quality or quality
        if selected_output_quality:
            filters.append("c.output_quality=:output_quality")
            params["output_quality"] = selected_output_quality
        query = f"""SELECT p.name provider_name,m.name model_name,r.run_id,r.status run_status,
            c.quality input_quality,c.output_quality,c.output_quality quality,
            count(*) total_tryons,count(*) FILTER(WHERE t.status='SUCCEEDED') successful_tryons,
            coalesce(sum(u.text_input_tokens),0)+coalesce(sum(u.image_input_tokens),0)+coalesce(sum(u.cached_input_tokens),0) input_tokens,
            coalesce(sum(u.image_output_tokens),0) output_tokens,coalesce(sum(u.total_reported_tokens),0) total_reported_tokens,
            coalesce(sum(u.calculated_cost_usd),0) total_cost_usd,
            coalesce(sum(u.calculated_cost_usd),0)/nullif(count(*) FILTER(WHERE t.status='SUCCEEDED'),0) average_cost_usd,
            avg(t.latency_ms) average_latency_ms,
            count(*) FILTER(WHERE t.status='SUCCEEDED')::numeric/nullif(count(*),0) success_rate
            FROM cost_lab.tryon_runs t JOIN cost_lab.benchmark_runs r USING(run_id) JOIN cost_lab.benchmark_combinations c USING(combination_id)
            JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id) LEFT JOIN cost_lab.tryon_usage u USING(tryon_id)
            WHERE {" AND ".join(filters)}
            GROUP BY p.name,m.name,r.run_id,r.status,c.quality,c.output_quality
            ORDER BY r.created_at DESC,c.quality,c.output_quality"""
        with service.engine.begin() as connection:
            summaries = _rows(connection.execute(text(query), params))
            fx = (
                connection.execute(
                    text(
                        "SELECT * FROM cost_lab.fx_rates WHERE base_currency='USD' AND quote_currency='INR' ORDER BY fetched_at DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
        return {"summaries": summaries, "fx_rate": dict(fx) if fx else None}

    @app.delete("/api/cost-lab/results/{run_id}")
    def delete_benchmark_result(run_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            status = connection.execute(
                text("SELECT status FROM cost_lab.benchmark_runs WHERE run_id=:id FOR UPDATE"),
                {"id": run_id},
            ).scalar_one_or_none()
            if status is None:
                raise HTTPException(404, "Benchmark result not found")
            if status not in {"COMPLETED", "FAILED", "CANCEL_REQUESTED", "CANCELLED"}:
                raise HTTPException(409, "Cancel or finish the benchmark before deleting it")
            final_check = connection.execute(text("""SELECT 1
            FROM cost_lab.final_model_check_runs WHERE run_id=:id"""),
                {"id": run_id}).scalar_one_or_none()
            if final_check is not None:
                raise HTTPException(
                    409, "This benchmark belongs to a final model check and cannot be deleted"
                )
            connection.execute(
                text("DELETE FROM cost_lab.benchmark_runs WHERE run_id=:id"), {"id": run_id}
            )
            connection.execute(
                text("""INSERT INTO cost_lab.audit_events
                (event_id,action,target_type,target_id,metadata)
                VALUES(:event,'BENCHMARK_RESULT_DELETED','BENCHMARK_RUN',:run,
                  jsonb_build_object('status',CAST(:status AS text)))"""),
                {"event": uuid4(), "run": run_id, "status": status},
            )
        output_directory = (actual.storage_root / "outputs" / str(run_id)).resolve()
        outputs_root = (actual.storage_root / "outputs").resolve()
        if output_directory.parent == outputs_root and output_directory.is_dir():
            shutil.rmtree(output_directory)
        return {"run_id": run_id, "deleted": True}

    @app.post("/api/cost-lab/results/recalculate")
    def recalculate_results(_: Auth) -> dict[str, Any]:
        updated = 0
        skipped = 0
        total_cost = Decimal("0")
        with service.engine.begin() as connection:
            rows = (
                connection.execute(
                    text("""SELECT u.usage_id,u.text_input_tokens,u.image_input_tokens,
                u.cached_input_tokens,u.image_output_tokens,u.total_reported_tokens,
                u.other_units,c.output_quality,pricing.components
                FROM cost_lab.tryon_usage u
                JOIN cost_lab.tryon_runs t USING(tryon_id)
                JOIN cost_lab.benchmark_runs r USING(run_id)
                JOIN cost_lab.benchmark_combinations c USING(combination_id)
                LEFT JOIN LATERAL (
                  SELECT components FROM cost_lab.model_pricing mp
                  WHERE mp.model_id=r.model_id AND mp.effective_at <= now()
                  ORDER BY mp.effective_at DESC LIMIT 1
                ) pricing ON true""")
                )
                .mappings()
                .all()
            )
            for row in rows:
                if row["components"] is None:
                    skipped += 1
                    continue
                usage = {
                    key: row[key]
                    for key in (
                        "text_input_tokens",
                        "image_input_tokens",
                        "cached_input_tokens",
                        "image_output_tokens",
                        "total_reported_tokens",
                    )
                    if row[key] is not None
                }
                usage.update(dict(row["other_units"] or {}))
                usage["output_quality"] = row["output_quality"]
                cost = calculate_cost(usage, list(row["components"]))
                connection.execute(
                    text("""UPDATE cost_lab.tryon_usage SET calculated_cost_usd=:cost
                    WHERE usage_id=:id"""),
                    {"cost": cost, "id": row["usage_id"]},
                )
                total_cost += cost
                updated += 1
            connection.execute(
                text("""INSERT INTO cost_lab.audit_events
                (event_id,action,target_type,metadata)
                VALUES(:id,'RESULT_COSTS_RECALCULATED','TRYON_USAGE',CAST(:metadata AS jsonb))"""),
                {
                    "id": uuid4(),
                    "metadata": _json(
                        {"updated": updated, "skipped": skipped, "total_cost_usd": total_cost}
                    ),
                },
            )
        return {"updated": updated, "skipped": skipped, "total_cost_usd": total_cost}

    @app.get("/api/cost-lab/results/tryons/{tryon_id}/image")
    def result_image(tryon_id: UUID, _: Auth, download: bool = False) -> FileResponse:
        with service.engine.begin() as connection:
            path = connection.execute(
                text("SELECT output_path FROM cost_lab.tryon_runs WHERE tryon_id=:id"),
                {"id": tryon_id},
            ).scalar_one_or_none()
        if not path:
            raise HTTPException(404, "Generated image not found")
        resolved = (actual.storage_root / path).resolve()
        if actual.storage_root.resolve() not in resolved.parents or not resolved.is_file():
            raise HTTPException(404, "Generated image not found")
        return FileResponse(
            resolved,
            filename=f"wearo-tryon-{tryon_id}{resolved.suffix or '.png'}",
            content_disposition_type="attachment" if download else "inline",
        )

    @app.get("/api/cost-lab/results/person-candidates")
    def result_person_candidates(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            rows = _rows(
                connection.execute(
                    text("""SELECT t.tryon_id,c.ordinal,r.run_id,r.created_at,
                    m.name model_name,p.name provider_name
                    FROM cost_lab.tryon_runs t
                    JOIN cost_lab.benchmark_combinations c
                      ON c.combination_id=t.combination_id
                    JOIN cost_lab.benchmark_runs r ON r.run_id=t.run_id
                    JOIN cost_lab.ai_models m USING(model_id)
                    JOIN cost_lab.model_providers p USING(provider_id)
                    WHERE t.status='SUCCEEDED' AND t.output_path IS NOT NULL
                    ORDER BY t.finished_at DESC NULLS LAST LIMIT 200""")
                )
            )
        for row in rows:
            row["image_url"] = f"/api/cost-lab/results/tryons/{row['tryon_id']}/image"
        return {"images": rows}

    @app.post("/api/cost-lab/model-comparisons", status_code=202)
    def create_model_comparison(body: ModelComparisonBody, auth: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            model_ids = (
                connection.execute(
                    text("""SELECT m.model_id FROM cost_lab.ai_models m
                JOIN cost_lab.model_providers p USING(provider_id)
                JOIN cost_lab.model_quality_mapping mq USING(model_id)
                JOIN cost_lab.quality_profiles q USING(profile_id)
                WHERE m.enabled=true AND p.enabled=true AND mq.supported=true AND q.code=:quality
                ORDER BY p.name,m.name"""),
                    {"quality": body.output_quality},
                )
                .scalars()
                .all()
            )
        if not model_ids:
            raise HTTPException(422, "No enabled models support the selected quality")
        comparison_id = uuid4()
        runs: list[tuple[UUID, UUID]] = []
        for model_id in model_ids:
            result = create_benchmark(
                BenchmarkBody(
                    model_id=model_id,
                    category=body.category,
                    person_result_tryon_id=body.person_result_tryon_id,
                    product_asset_id=body.product_asset_id,
                    input_quality=body.output_quality,
                    output_quality=body.output_quality,
                    image_count=1,
                ),
                auth,
            )
            runs.append((model_id, result["run_id"]))
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.model_comparisons
                (comparison_id,person_result_tryon_id,product_asset_id,category,output_quality)
                VALUES(:id,:person,:product,:category,:quality)"""),
                {
                    "id": comparison_id,
                    "person": body.person_result_tryon_id,
                    "product": body.product_asset_id,
                    "category": body.category,
                    "quality": body.output_quality,
                },
            )
            for model_id, run_id in runs:
                connection.execute(
                    text("""INSERT INTO cost_lab.model_comparison_entries
                    (comparison_id,run_id,model_id) VALUES(:comparison,:run,:model)"""),
                    {"comparison": comparison_id, "run": run_id, "model": model_id},
                )
        return {"comparison_id": comparison_id, "model_count": len(runs), "status": "QUEUED"}

    @app.get("/api/cost-lab/model-comparisons")
    def model_comparisons(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            rows = _rows(
                connection.execute(
                    text("""SELECT c.*,
            count(e.run_id) model_count,
            count(e.run_id) FILTER (WHERE r.status IN ('COMPLETED','FAILED','CANCELLED')) finished_count,
            CASE WHEN bool_and(r.status='COMPLETED') THEN 'COMPLETED'
              WHEN bool_and(r.status IN ('COMPLETED','FAILED','CANCELLED')) THEN 'FINISHED'
              WHEN bool_or(r.status='RUNNING') THEN 'RUNNING' ELSE 'QUEUED' END status
            FROM cost_lab.model_comparisons c
            JOIN cost_lab.model_comparison_entries e USING(comparison_id)
            JOIN cost_lab.benchmark_runs r USING(run_id)
            GROUP BY c.comparison_id ORDER BY c.created_at DESC LIMIT 100""")
                )
            )
        return {"comparisons": rows}

    @app.get("/api/cost-lab/model-comparisons/{comparison_id}")
    def model_comparison_detail(comparison_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            comparison = (
                connection.execute(
                    text("SELECT * FROM cost_lab.model_comparisons WHERE comparison_id=:id"),
                    {"id": comparison_id},
                )
                .mappings()
                .one_or_none()
            )
            if comparison is None:
                raise HTTPException(404, "Model comparison not found")
            rows = _rows(
                connection.execute(
                    text("""SELECT e.run_id,m.name model_name,p.name provider_name,
            r.status,t.tryon_id,t.status tryon_status,t.error_detail,u.text_input_tokens,u.image_input_tokens,
            u.cached_input_tokens,u.image_output_tokens,u.total_reported_tokens,u.calculated_cost_usd
            FROM cost_lab.model_comparison_entries e
            JOIN cost_lab.benchmark_runs r USING(run_id)
            JOIN cost_lab.ai_models m ON m.model_id=e.model_id
            JOIN cost_lab.model_providers p USING(provider_id)
            JOIN cost_lab.tryon_runs t USING(run_id)
            LEFT JOIN cost_lab.tryon_usage u USING(tryon_id)
            WHERE e.comparison_id=:id ORDER BY p.name,m.name"""),
                    {"id": comparison_id},
                )
            )
        person_url = f"/api/cost-lab/results/tryons/{comparison['person_result_tryon_id']}/image"
        product_url = f"/api/cost-lab/assets/{comparison['product_asset_id']}/content?quality={comparison['output_quality']}"
        for row in rows:
            row["image_url"] = (
                f"/api/cost-lab/results/tryons/{row['tryon_id']}/image"
                if row["tryon_status"] == "SUCCEEDED"
                else None
            )
        return {
            "comparison": dict(comparison) | {"person_url": person_url, "product_url": product_url},
            "results": rows,
        }

    @app.get("/api/cost-lab/results/{run_id}")
    def result_detail(run_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            run = (
                connection.execute(
                    text("""SELECT r.run_id,r.status,r.created_at,r.finished_at,m.name model_name,
                p.name provider_name FROM cost_lab.benchmark_runs r
                JOIN cost_lab.ai_models m USING(model_id)
                JOIN cost_lab.model_providers p USING(provider_id) WHERE r.run_id=:id"""),
                    {"id": run_id},
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise HTTPException(404, "Benchmark result not found")
            items = _rows(
                connection.execute(
                    text("""SELECT t.*,c.ordinal,c.quality input_quality,c.output_quality,
                c.output_quality quality,c.person_asset_id,c.product_asset_id,
                person.name person_asset_name,product.name product_asset_name,u.*
                FROM cost_lab.tryon_runs t JOIN cost_lab.benchmark_combinations c USING(combination_id)
                JOIN cost_lab.benchmark_assets person ON person.asset_id=c.person_asset_id
                JOIN cost_lab.benchmark_assets product ON product.asset_id=c.product_asset_id
                LEFT JOIN cost_lab.tryon_usage u USING(tryon_id)
                WHERE t.run_id=:id ORDER BY c.ordinal"""),
                    {"id": run_id},
                )
            )
        for item in items:
            item["person_url"] = (
                f"/api/cost-lab/assets/{item['person_asset_id']}/content"
                f"?quality={item['input_quality']}"
            )
            item["product_url"] = (
                f"/api/cost-lab/assets/{item['product_asset_id']}/content"
                f"?quality={item['input_quality']}"
            )
            item["image_url"] = None
            item["download_url"] = None
            item["pixel_width"] = None
            item["pixel_height"] = None
            item["image_format"] = None
            item["file_size_bytes"] = None
            if item.get("output_path"):
                resolved = (actual.storage_root / item["output_path"]).resolve()
                if actual.storage_root.resolve() in resolved.parents and resolved.is_file():
                    try:
                        with Image.open(resolved) as generated:
                            item["pixel_width"], item["pixel_height"] = generated.size
                            item["image_format"] = generated.format
                    except Exception:
                        item["image_format"] = "UNKNOWN"
                    item["file_size_bytes"] = resolved.stat().st_size
                    item["image_url"] = f"/api/cost-lab/results/tryons/{item['tryon_id']}/image"
                    item["download_url"] = (
                        f"/api/cost-lab/results/tryons/{item['tryon_id']}/image?download=true"
                    )
        return {"run": dict(run), "tryons": items}

    @app.post("/api/cost-lab/fx/refresh")
    def refresh_fx(_: Auth) -> dict[str, Any]:
        try:
            response = requests.get(actual.fx_url, timeout=10)
            response.raise_for_status()
            payload = response.json()
            rate = Decimal(str(payload["rates"]["INR"]))
            source = actual.fx_url.split("/")[2]
            with service.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO cost_lab.fx_rates(rate_id,base_currency,quote_currency,rate,source,fetched_at) VALUES(:id,'USD','INR',:rate,:source,now())"
                    ),
                    {"id": uuid4(), "rate": rate, "source": source},
                )
            return {"base_currency": "USD", "quote_currency": "INR", "rate": rate, "source": source}
        except (requests.RequestException, KeyError, ValueError) as error:
            with service.engine.begin() as connection:
                cached = (
                    connection.execute(
                        text(
                            "SELECT * FROM cost_lab.fx_rates WHERE base_currency='USD' AND quote_currency='INR' ORDER BY fetched_at DESC LIMIT 1"
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            if cached:
                return {**dict(cached), "cached": True}
            raise HTTPException(503, "FX rate unavailable and no cached rate exists") from error

    @app.post("/api/cost-lab/final-checks", status_code=202)
    def create_final_check(body: FinalCheckBody, username: Auth) -> dict[str, Any]:
        complexities = {
            "JEWELLERY": body.jewellery_complexity,
            "SAREE": body.saree_complexity,
            "DRESS": body.dress_complexity,
        }
        with service.engine.begin() as connection:
            person = connection.execute(
                text("""SELECT 1 FROM cost_lab.benchmark_assets
                WHERE asset_id=:id AND kind='PERSON' AND replaced_at IS NULL"""),
                {"id": body.person_asset_id},
            ).scalar_one_or_none()
            previous = connection.execute(
                text("""SELECT 1 FROM cost_lab.benchmark_runs
                WHERE model_id=:model AND status='COMPLETED' LIMIT 1"""),
                {"model": body.model_id},
            ).scalar_one_or_none()
            available_inputs = {
                (row["kind"], row["complexity"]): row["item_count"]
                for row in connection.execute(text("""SELECT kind,complexity,count(*) item_count
                FROM cost_lab.benchmark_assets
                WHERE kind IN ('JEWELLERY','SAREE','DRESS') AND replaced_at IS NULL
                GROUP BY kind,complexity""")).mappings()
            }
        if person is None:
            raise HTTPException(422, "Select an active person image")
        if previous is None:
            raise HTTPException(409, "Complete a benchmark for this model before final check")
        missing = [
            f"{complexity.lower()} {category.lower()}"
            for category, complexity in complexities.items()
            if not available_inputs.get((category, complexity), 0)
        ]
        if missing:
            raise HTTPException(
                422,
                "No active dataset item is available for: " + ", ".join(missing)
                + ". Reclassify or add matching dataset images before starting the final check.",
            )

        check_id = uuid4()
        created_runs: list[dict[str, Any]] = []
        plan = [(category, quality, 2 if category == "JEWELLERY" else 1)
                for category in ("JEWELLERY", "SAREE", "DRESS")
                for quality in ("LOW", "MEDIUM", "HIGH")]
        try:
            for category, quality, count in plan:
                result = create_benchmark(
                    BenchmarkBody(
                        model_id=body.model_id,
                        category=category,
                        input_complexity=complexities[category],
                        person_asset_id=body.person_asset_id,
                        input_quality=quality,
                        output_quality=quality,
                        image_count=count,
                    ),
                    username,
                )
                created_runs.append(
                    {"run_id": result["run_id"], "category": category,
                     "quality": quality, "expected_outputs": count}
                )
        except Exception:
            if created_runs:
                with service.engine.begin() as connection:
                    connection.execute(
                        text("""UPDATE cost_lab.benchmark_runs SET status='CANCEL_REQUESTED'
                        WHERE run_id=ANY(:runs) AND status IN ('QUEUED','RUNNING')"""),
                        {"runs": [item["run_id"] for item in created_runs]},
                    )
            raise
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.final_model_checks
                (check_id,model_id,person_asset_id,status,created_by,input_complexities)
                VALUES(:id,:model,:person,'GENERATING',:username,CAST(:complexities AS jsonb))"""),
                {"id": check_id, "model": body.model_id, "person": body.person_asset_id,
                 "username": username, "complexities": _json(complexities)},
            )
            for item in created_runs:
                connection.execute(
                    text("""INSERT INTO cost_lab.final_model_check_runs
                    (check_id,run_id,category,quality,expected_outputs)
                    VALUES(:check,:run,:category,:quality,:count)"""),
                    {"check": check_id, "run": item["run_id"], "category": item["category"],
                     "quality": item["quality"], "count": item["expected_outputs"]},
                )
        return {"check_id": check_id, "status": "GENERATING", "total_outputs": 12}

    @app.get("/api/cost-lab/final-checks")
    def final_checks(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            connection.execute(text("""UPDATE cost_lab.final_model_checks f SET status='FAILED'
            WHERE f.status='GENERATING'
              AND EXISTS (SELECT 1 FROM cost_lab.final_model_check_runs x
                JOIN cost_lab.benchmark_runs r USING(run_id)
                WHERE x.check_id=f.check_id AND r.status IN ('FAILED','CANCELLED'))"""))
            connection.execute(text("""UPDATE cost_lab.final_model_checks f SET status='REVIEW_PENDING'
            WHERE f.status='GENERATING'
              AND NOT EXISTS (SELECT 1 FROM cost_lab.final_model_check_runs x
                JOIN cost_lab.benchmark_runs r USING(run_id)
                WHERE x.check_id=f.check_id AND r.status <> 'COMPLETED')"""))
            checks = _rows(connection.execute(text("""SELECT f.*,m.name model_name,p.name provider_name,
            count(DISTINCT rv.review_id) review_count,
            count(DISTINCT t.tryon_id) FILTER (WHERE t.status IN ('SUCCEEDED','FAILED','CANCELLED')) completed_outputs,
            count(DISTINCT t.tryon_id) FILTER (WHERE t.status='SUCCEEDED') successful_outputs
            FROM cost_lab.final_model_checks f JOIN cost_lab.ai_models m USING(model_id)
            JOIN cost_lab.model_providers p USING(provider_id)
            LEFT JOIN cost_lab.final_model_check_runs x USING(check_id)
            LEFT JOIN cost_lab.tryon_runs t USING(run_id)
            LEFT JOIN cost_lab.final_model_reviews rv USING(check_id)
            GROUP BY f.check_id,m.name,p.name
            ORDER BY f.created_at DESC""")))
        return {"checks": checks}

    @app.get("/api/cost-lab/final-checks/{check_id}")
    def final_check_detail(check_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            check = connection.execute(text("""SELECT f.*,m.name model_name,p.name provider_name
            FROM cost_lab.final_model_checks f JOIN cost_lab.ai_models m USING(model_id)
            JOIN cost_lab.model_providers p USING(provider_id) WHERE check_id=:id"""),
                {"id": check_id}).mappings().one_or_none()
            if check is None:
                raise HTTPException(404, "Final check not found")
            outputs = _rows(connection.execute(text("""SELECT t.tryon_id,t.status,x.category,x.quality,
            t.output_path,c.product_asset_id,product.name product_asset_name,
            rv.score,rv.comment,rv.reviewed_by,rv.reviewed_at
            FROM cost_lab.final_model_check_runs x JOIN cost_lab.tryon_runs t USING(run_id)
            JOIN cost_lab.benchmark_combinations c USING(combination_id)
            JOIN cost_lab.benchmark_assets product ON product.asset_id=c.product_asset_id
            LEFT JOIN cost_lab.final_model_reviews rv USING(tryon_id)
            WHERE x.check_id=:id ORDER BY x.category,x.quality,t.created_at"""), {"id": check_id}))
            pricing = connection.execute(text("""SELECT components,effective_at
            FROM cost_lab.model_pricing WHERE model_id=:model AND effective_at <= now()
            ORDER BY effective_at DESC LIMIT 1"""),
                {"model": check["model_id"]}).mappings().one_or_none()
        for output in outputs:
            output["image_url"] = (f"/api/cost-lab/results/tryons/{output['tryon_id']}/image"
                                   if output.get("output_path") else None)
            output["source_image_url"] = (
                f"/api/cost-lab/assets/{output['product_asset_id']}/content?quality={output['quality']}"
            )
        progress = {
            "total": 12,
            "completed": sum(item["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}
                             for item in outputs),
            "successful": sum(item["status"] == "SUCCEEDED" for item in outputs),
            "reviewed": sum(item.get("score") is not None for item in outputs),
        }
        quality_scores = {
            quality: round(
                sum(int(item["score"]) for item in outputs
                    if item["quality"] == quality and item.get("score") is not None)
                / len([item for item in outputs
                       if item["quality"] == quality and item.get("score") is not None])
                * 10,
                2,
            )
            for quality in ("LOW", "MEDIUM", "HIGH")
            if any(item["quality"] == quality and item.get("score") is not None
                   for item in outputs)
        }
        components = list(pricing["components"]) if pricing else []
        quality_prices = {
            quality: next((item.get("price_usd") for item in components
                           if item.get("unit") == "output_images"
                           and item.get("quality") == quality), None)
            for quality in ("LOW", "MEDIUM", "HIGH")
        }
        return {"check": dict(check), "outputs": outputs, "progress": progress,
                "quality_scores": quality_scores,
                "quality_prices_usd": quality_prices,
                "pricing_effective_at": pricing["effective_at"] if pricing else None}

    @app.delete("/api/cost-lab/final-checks/{check_id}")
    def delete_final_check(check_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            check = connection.execute(text("""SELECT status FROM cost_lab.final_model_checks
            WHERE check_id=:id FOR UPDATE"""), {"id": check_id}).scalar_one_or_none()
            if check is None:
                raise HTTPException(404, "Final check not found")
            promoted = connection.execute(text("""SELECT 1
            FROM cost_lab.production_model_releases WHERE final_check_id=:id"""),
                {"id": check_id}).scalar_one_or_none()
            if promoted is not None:
                raise HTTPException(
                    409, "Promoted final checks cannot be deleted from production history"
                )
            run_ids = list(connection.execute(text("""SELECT run_id
            FROM cost_lab.final_model_check_runs WHERE check_id=:id"""),
                {"id": check_id}).scalars().all())
            if run_ids:
                connection.execute(text("""UPDATE cost_lab.tryon_runs
                SET status='CANCELLED',finished_at=now(),leased_by=NULL,lease_expires_at=NULL
                WHERE run_id=ANY(:runs) AND status IN ('QUEUED','PROCESSING')"""),
                    {"runs": run_ids})
                connection.execute(text("""UPDATE cost_lab.benchmark_runs
                SET status='CANCELLED',finished_at=now() WHERE run_id=ANY(:runs)
                  AND status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')"""), {"runs": run_ids})
            connection.execute(
                text("DELETE FROM cost_lab.final_model_checks WHERE check_id=:id"),
                {"id": check_id},
            )
            if run_ids:
                connection.execute(
                    text("DELETE FROM cost_lab.benchmark_runs WHERE run_id=ANY(:runs)"),
                    {"runs": run_ids},
                )
            connection.execute(text("""INSERT INTO cost_lab.audit_events
            (event_id,action,target_type,target_id,metadata)
            VALUES(:event,'FINAL_CHECK_DELETED','FINAL_MODEL_CHECK',:id,
              CAST(:metadata AS jsonb))"""),
                {"event": uuid4(), "id": check_id,
                 "metadata": _json({"status": check})})
        outputs_root = (actual.storage_root / "outputs").resolve()
        for run_id in run_ids:
            output_directory = (outputs_root / str(run_id)).resolve()
            if output_directory.parent == outputs_root and output_directory.is_dir():
                shutil.rmtree(output_directory)
        return {"check_id": check_id, "deleted": True, "deleted_runs": len(run_ids)}

    @app.put("/api/cost-lab/final-checks/{check_id}/reviews")
    def save_final_reviews(check_id: UUID, body: FinalReviewsBody, username: Auth) -> dict[str, Any]:
        ids = [item.tryon_id for item in body.reviews]
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Each output may be reviewed only once per request")
        with service.engine.begin() as connection:
            allowed: set[UUID] = set(connection.execute(text("""SELECT t.tryon_id
            FROM cost_lab.final_model_check_runs x JOIN cost_lab.tryon_runs t USING(run_id)
            WHERE x.check_id=:id AND t.status='SUCCEEDED' AND t.tryon_id=ANY(:tryons)"""),
                {"id": check_id, "tryons": ids}).scalars().all())
            if allowed != set(ids):
                raise HTTPException(422, "Scores must reference successful outputs in this check")
            for item in body.reviews:
                connection.execute(text("""INSERT INTO cost_lab.final_model_reviews
                (review_id,check_id,tryon_id,score,comment,reviewed_by)
                VALUES(:review,:check,:tryon,:score,:comment,:username)
                ON CONFLICT(tryon_id) DO UPDATE SET score=excluded.score,comment=excluded.comment,
                reviewed_by=excluded.reviewed_by,reviewed_at=now()"""),
                    {"review": uuid4(), "check": check_id, "tryon": item.tryon_id,
                     "score": item.score, "comment": item.comment.strip(), "username": username})
            count: int = connection.execute(text("SELECT count(*) FROM cost_lab.final_model_reviews WHERE check_id=:id"),
                {"id": check_id}).scalar_one()
            if count == 12:
                connection.execute(text("""UPDATE cost_lab.final_model_checks
                SET status='SCORED',judged_at=now() WHERE check_id=:id
                  AND status <> 'PROMOTED'"""), {"id": check_id})
        return {"check_id": check_id, "review_count": count, "complete": count == 12}

    @app.post("/api/cost-lab/final-checks/{check_id}/promote")
    def promote_final_check(
        check_id: UUID, body: PromoteFinalCheckBody, username: Auth
    ) -> dict[str, Any]:
        with service.engine.begin() as connection:
            candidate = connection.execute(text("""SELECT f.model_id,p.components pricing_snapshot,
            p.effective_at pricing_effective_at FROM cost_lab.final_model_checks f
            LEFT JOIN LATERAL (SELECT components,effective_at FROM cost_lab.model_pricing
              WHERE model_id=f.model_id AND effective_at <= now()
              ORDER BY effective_at DESC LIMIT 1) p ON true
            WHERE f.check_id=:id AND f.status='SCORED'
            FOR UPDATE OF f"""), {"id": check_id}).mappings().one_or_none()
            if candidate is None:
                raise HTTPException(
                    409, "Promotion requires a completed final-check score summary"
                )
            now = datetime.now(UTC)
            existing_priority = connection.execute(text("""SELECT priority
            FROM cost_lab.production_model_releases
            WHERE model_id=:model AND retired_at IS NULL FOR UPDATE"""),
                {"model": candidate["model_id"]}).scalar_one_or_none()
            connection.execute(text("""UPDATE cost_lab.production_model_releases
            SET retired_at=:now,priority=NULL
            WHERE model_id=:model AND retired_at IS NULL"""),
                {"now": now, "model": candidate["model_id"]})
            used_priorities = set(connection.execute(text("""SELECT priority
            FROM cost_lab.production_model_releases
            WHERE retired_at IS NULL AND priority IS NOT NULL FOR UPDATE""")).scalars().all())
            available_priority = next(
                (value for value in range(1, 21) if value not in used_priorities), None
            )
            priority = existing_priority or available_priority
            if priority is None:
                raise HTTPException(409, "All 20 production model priorities are in use")
            release_id = uuid4()
            connection.execute(text("""INSERT INTO cost_lab.production_model_releases
            (release_id,model_id,final_check_id,promoted_by,promoted_at,
             pricing_snapshot,pricing_effective_at,priority)
            VALUES(:release,:model,:check,:username,:now,CAST(:pricing AS jsonb),:effective,
             :priority)"""),
                {"release": release_id, "model": candidate["model_id"], "check": check_id,
                 "pricing": _json(candidate["pricing_snapshot"] or []),
                 "effective": candidate["pricing_effective_at"],
                 "username": username, "now": now, "priority": priority})
            connection.execute(text("""UPDATE cost_lab.production_model_releases
            SET approved_quality_levels=CAST(:qualities AS jsonb) WHERE release_id=:id"""),
                {"qualities": _json(body.quality_levels), "id": release_id})
            connection.execute(text("""UPDATE cost_lab.final_model_checks
            SET status='PROMOTED',promoted_at=:now WHERE check_id=:id"""),
                {"id": check_id, "now": now})
        return {"release_id": release_id, "model_id": candidate["model_id"],
                "approved_quality_levels": body.quality_levels, "priority": priority,
                "status": "PRODUCTION"}

    @app.get("/api/cost-lab/production-models")
    def production_models(_: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            releases = _rows(connection.execute(text("""SELECT r.*,m.name model_name,m.api_identifier,
            m.version model_version,p.name provider_name,p.provider_type,p.api_base_url
            FROM cost_lab.production_model_releases r
            JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id)
            ORDER BY (r.retired_at IS NOT NULL),r.priority NULLS LAST,r.promoted_at DESC""")))
        active = [row for row in releases if row["retired_at"] is None]
        return {"active": active[0] if active else None, "active_models": active,
                "history": releases}

    @app.put("/api/cost-lab/production-models/priorities")
    def update_production_model_priorities(
        body: ProductionModelPrioritiesBody, _: Auth
    ) -> dict[str, Any]:
        requested = {item.release_id: item.priority for item in body.priorities}
        with service.engine.begin() as connection:
            active_ids = set(connection.execute(text("""SELECT release_id
            FROM cost_lab.production_model_releases WHERE retired_at IS NULL
            FOR UPDATE""")).scalars().all())
            if set(requested) != active_ids:
                raise HTTPException(409, "Priorities must include every active production model")
            # Clear first so the partial unique index permits priority swaps.
            connection.execute(text("""UPDATE cost_lab.production_model_releases
            SET priority=NULL WHERE retired_at IS NULL"""))
            for release_id, priority in requested.items():
                connection.execute(text("""UPDATE cost_lab.production_model_releases
                SET priority=:priority WHERE release_id=:release"""),
                    {"release": release_id, "priority": priority})
        return {"priorities": [item.model_dump() for item in body.priorities]}

    @app.delete("/api/cost-lab/production-models/{release_id}")
    def delete_production_model(release_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            release = connection.execute(text("""SELECT release_id,model_id,final_check_id,
            retired_at FROM cost_lab.production_model_releases
            WHERE release_id=:id FOR UPDATE"""), {"id": release_id}).mappings().one_or_none()
            if release is None:
                raise HTTPException(404, "Promoted model not found")
            connection.execute(
                text("DELETE FROM cost_lab.production_model_releases WHERE release_id=:id"),
                {"id": release_id},
            )
            connection.execute(text("""UPDATE cost_lab.final_model_checks
            SET status='SCORED',promoted_at=NULL WHERE check_id=:id AND status='PROMOTED'"""),
                {"id": release["final_check_id"]})
            connection.execute(text("""INSERT INTO cost_lab.audit_events
            (event_id,action,target_type,target_id,metadata)
            VALUES(:event,'PRODUCTION_MODEL_DELETED','PRODUCTION_MODEL_RELEASE',:release,
              jsonb_build_object('model_id',CAST(:model AS text),
                                 'final_check_id',CAST(:check AS text),
                                 'was_active',CAST(:active AS boolean)))"""),
                {"event": uuid4(), "release": release_id, "model": release["model_id"],
                 "check": release["final_check_id"], "active": release["retired_at"] is None})
        return {"release_id": release_id, "deleted": True}

    return app


def run() -> None:
    import uvicorn

    uvicorn.run("apps.cost_lab_api.app:create_app", factory=True, host="127.0.0.1", port=8011)
