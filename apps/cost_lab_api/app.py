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
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.admin_auth import verify_password

from .adapters import BytePlusAdapter, OpenAICompatibleAdapter
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
    provider_type: Literal["OPENAI_COMPATIBLE", "BYTEPLUS", "SECRET_REFERENCE"]
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
    image_input_price_usd_per_million: Decimal = Field(ge=0)
    image_output_price_usd_per_million: Decimal = Field(ge=0)


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


class DatasetGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: UUID


class KnowledgeTextBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=1_000_000)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


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
            blocks.append(f"<{list_kind}>{''.join(f'<li>{item}</li>' for item in list_items)}</{list_kind}>")
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
        items = [html.escape(str(item).strip()) for item in raw_items] if isinstance(raw_items, list) else []
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
                    raise HTTPException(502, "Knowledge formatting returned invalid content") from error
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
            existing = connection.execute(
                text("""SELECT secret_ciphertext,secret_reference FROM cost_lab.model_providers
                WHERE provider_id=:id"""),
                {"id": provider_id},
            ).mappings().one_or_none()
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
        if provider["provider_type"] not in {"OPENAI_COMPATIBLE", "BYTEPLUS"} or not provider[
            "api_base_url"
        ]:
            raise HTTPException(400, "This provider type has no connection validator")
        try:
            adapter_type = (
                BytePlusAdapter
                if provider["provider_type"] == "BYTEPLUS"
                else OpenAICompatibleAdapter
            )
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
        components = [
            {
                "unit": "image_input_tokens",
                "price_usd": str(body.image_input_price_usd_per_million),
            },
            {
                "unit": "image_output_tokens",
                "price_usd": str(body.image_output_price_usd_per_million),
            },
        ]
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
        components = [
            {
                "unit": "image_input_tokens",
                "price_usd": str(body.image_input_price_usd_per_million),
            },
            {
                "unit": "image_output_tokens",
                "price_usd": str(body.image_output_price_usd_per_million),
            },
        ]
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
            item = connection.execute(
                text("""SELECT source_type,title,content_text,formatted_html,file_path,
                original_filename,created_at
                FROM cost_lab.knowledge_items WHERE knowledge_id=:id"""),
                {"id": knowledge_id},
            ).mappings().one_or_none()
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
                text("""INSERT INTO cost_lab.benchmark_assets(asset_id,kind,name,original_path,variants,content_hash,authorized)
                VALUES(:id,:kind,:name,:path,CAST(:variants AS jsonb),:hash,true)"""),
                {
                    "id": asset_id,
                    "kind": kind,
                    "name": name,
                    "path": str(original.relative_to(actual.storage_root)),
                    "variants": _json(variants),
                    "hash": digest,
                },
            )
        return {"asset_id": asset_id, "variants": variants}

    @app.get("/api/cost-lab/assets/{asset_id}/content")
    def asset_content(asset_id: UUID, _: Auth) -> FileResponse:
        with service.engine.begin() as connection:
            path = connection.execute(
                text("SELECT original_path FROM cost_lab.benchmark_assets WHERE asset_id=:id"),
                {"id": asset_id},
            ).scalar_one_or_none()
        if not path:
            raise HTTPException(404, "Asset not found")
        resolved = (actual.storage_root / path).resolve()
        if actual.storage_root.resolve() not in resolved.parents:
            raise HTTPException(400, "Invalid asset path")
        return FileResponse(resolved)

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
        prompts: list[tuple[str, str]] = [
            (
                "PERSON",
                "Create a photorealistic full-body studio portrait of one adult Indian woman, "
                "standing naturally, front-facing, neutral fitted base clothing, hands visible, "
                "plain warm-grey background, even soft lighting, no jewellery, no text or logo. "
                "This is a synthetic reference person for authorized virtual try-on testing.",
            )
        ]
        prompts.extend(
            (
                "JEWELLERY",
                f"Create a photorealistic isolated Indian jewellery product image, design {index + 1} "
                "of 10, visually distinct in metal, stones and silhouette, centered on a clean neutral "
                "background, ecommerce studio lighting, no person, no text, no logo.",
            )
            for index in range(10)
        )
        prompts.extend(
            (
                "SAREE",
                f"Create a photorealistic isolated Indian saree product image, design {index + 1} of "
                "10, uniquely varied fabric, colour, weave and border, neatly draped on a neutral "
                "invisible form, clean ecommerce background, no person, no text, no logo.",
            )
            for index in range(10)
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
        prompts.extend(
            (
                "DRESS",
                f"Create a photorealistic isolated women's {style} product image, design {index + 1} "
                "of 10, with a distinct colour and fabric, front view on a neutral invisible form, "
                "clean ecommerce studio background, no person, no text, no logo.",
            )
            for index, style in enumerate(dress_styles)
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
                (job_id,model_id,status,total_items) VALUES(:id,:model,'QUEUED',:total)"""),
                {"id": job_id, "model": body.model_id, "total": len(prompts)},
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
        return {"job_id": job_id, "status": "QUEUED", "total_items": len(prompts)}

    @app.post("/api/cost-lab/benchmarks", status_code=202)
    def create_benchmark(body: BenchmarkBody, _: Auth) -> dict[str, Any]:
        qualities = ["LOW", "MEDIUM", "HIGH"]
        categories = ["JEWELLERY", "SAREE", "DRESS"]
        tryons_per_quality = 10
        prompt_version = "wearo-mixed-tryon-v2"
        prompt = (
            "Create exactly one photorealistic virtual try-on from two supplied reference images. "
            "Image 1 is the target person and must remain the output canvas. Image 2 is the product "
            "reference. Determine from Image 2 whether the primary product is jewellery, a saree, "
            "or a dress, then follow only the matching instruction below within this same generation. "
            "For jewellery: extract only the jewellery product from Image 2 and place exactly one of "
            "it naturally on the anatomically correct location of the person in Image 1. Ignore and "
            "never copy any reference person, face, skin, hair, hands, arms, legs, feet, mannequin, "
            "display stand, support, clothing, or background from Image 2. For a saree: dress the "
            "person in the referenced saree with realistic pleats, pallu, drape, scale, and fabric "
            "behaviour while preserving the person's anatomy. For a dress: replace only the relevant "
            "clothing with the referenced dress, fitted naturally to the person's existing pose and "
            "body proportions. In every case preserve the exact product colour, stones, pendant, "
            "chain, design, pattern, texture, material, construction, and visible branding as "
            "applicable. Preserve the target person's identity, face, expression, hairstyle, skin "
            "tone, body, pose, hands, feet, camera framing, lighting, and background. Do not create "
            "another person, miniature person, mannequin, extra or missing body parts, duplicate "
            "products, black shapes, text, logos not present in the product, or unrelated objects. "
            "Keep all unrelated areas of Image 1 unchanged and return only the final try-on image."
        )
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
                        "SELECT asset_id,content_hash FROM cost_lab.benchmark_assets WHERE kind='PERSON' AND replaced_at IS NULL ORDER BY asset_id"
                    )
                )
            )
            products = _rows(
                connection.execute(
                    text(
                        "SELECT asset_id,kind,content_hash FROM cost_lab.benchmark_assets WHERE kind=ANY(:categories) AND replaced_at IS NULL ORDER BY kind,asset_id"
                    ),
                    {"categories": categories},
                )
            )
        if model is None:
            raise HTTPException(404, "Enabled model not found")
        if any(item["supported"] is not True for item in mappings) or len(mappings) != len(
            qualities
        ):
            raise HTTPException(422, "One or more model/quality combinations are unsupported")
        if not people or not products:
            raise HTTPException(422, "Dataset needs person and product assets")
        components = list(pricing["components"]) if pricing else []
        fixed_components = [
            item for item in components if item.get("unit") in {"requests", "output_images"}
        ]
        total_jobs = len(qualities) * tryons_per_quality
        estimated = (
            calculate_cost({"requests": 1, "output_images": 1}, fixed_components) * total_jobs
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
                people, products, qualities, tryons_per_quality, seed
            )
        ]
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO cost_lab.benchmark_runs(run_id,model_id,category,qualities,tryons_per_quality,random_seed,prompt,prompt_version,
                dataset_fingerprint,pricing_snapshot,quality_snapshot,status,estimated_max_usd,spending_limit_usd,confirmed_at,total_jobs)
                VALUES(:id,:model,:category,CAST(:qualities AS jsonb),:count,:seed,:prompt,:version,:fingerprint,CAST(:pricing AS jsonb),CAST(:quality AS jsonb),
                'QUEUED',:estimated,:limit,now(),:total)"""),
                {
                    "id": run_id,
                    "model": body.model_id,
                    "category": "MIXED",
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
                },
            )
            for ordinal, (combination_id, quality, person, product) in enumerate(combinations):
                connection.execute(
                    text(
                        "INSERT INTO cost_lab.benchmark_combinations(combination_id,run_id,ordinal,quality,person_asset_id,product_asset_id) VALUES(:id,:run,:ordinal,:quality,:person,:product)"
                    ),
                    {
                        "id": combination_id,
                        "run": run_id,
                        "ordinal": ordinal,
                        "quality": quality,
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
                        text("""SELECT r.*,m.name model_name,p.name provider_name FROM cost_lab.benchmark_runs r
                JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id) ORDER BY r.created_at DESC LIMIT 200""")
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
    ) -> dict[str, Any]:
        filters = ["1=1"]
        params: dict[str, Any] = {}
        if provider_id:
            filters.append("p.provider_id=:provider")
            params["provider"] = provider_id
        if model_id:
            filters.append("m.model_id=:model")
            params["model"] = model_id
        if quality:
            filters.append("c.quality=:quality")
            params["quality"] = quality
        query = f"""SELECT p.name provider_name,m.name model_name,r.run_id,r.status run_status,c.quality,
            count(*) total_tryons,count(*) FILTER(WHERE t.status='SUCCEEDED') successful_tryons,
            coalesce(sum(u.text_input_tokens),0)+coalesce(sum(u.image_input_tokens),0)+coalesce(sum(u.cached_input_tokens),0) input_tokens,
            coalesce(sum(u.image_output_tokens),0) output_tokens,coalesce(sum(u.total_reported_tokens),0) total_reported_tokens,
            coalesce(sum(u.calculated_cost_usd),0) total_cost_usd,
            coalesce(sum(u.calculated_cost_usd),0)/nullif(count(*) FILTER(WHERE t.status='SUCCEEDED'),0) average_cost_usd,
            avg(t.latency_ms) average_latency_ms,
            count(*) FILTER(WHERE t.status='SUCCEEDED')::numeric/nullif(count(*),0) success_rate
            FROM cost_lab.tryon_runs t JOIN cost_lab.benchmark_runs r USING(run_id) JOIN cost_lab.benchmark_combinations c USING(combination_id)
            JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id) LEFT JOIN cost_lab.tryon_usage u USING(tryon_id)
            WHERE {" AND ".join(filters)} GROUP BY p.name,m.name,r.run_id,r.status,c.quality ORDER BY r.created_at DESC,c.quality"""
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
    def delete_failed_result(run_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            status = connection.execute(
                text("SELECT status FROM cost_lab.benchmark_runs WHERE run_id=:id FOR UPDATE"),
                {"id": run_id},
            ).scalar_one_or_none()
            if status is None:
                raise HTTPException(404, "Benchmark result not found")
            if status != "FAILED":
                raise HTTPException(409, "Only failed benchmark results can be deleted")
            connection.execute(
                text("DELETE FROM cost_lab.benchmark_runs WHERE run_id=:id"), {"id": run_id}
            )
            connection.execute(
                text("""INSERT INTO cost_lab.audit_events
                (event_id,action,target_type,target_id,metadata)
                VALUES(:event,'FAILED_RESULT_DELETED','BENCHMARK_RUN',:run,'{}'::jsonb)"""),
                {"event": uuid4(), "run": run_id},
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
            rows = connection.execute(
                text("""SELECT u.usage_id,u.text_input_tokens,u.image_input_tokens,
                u.cached_input_tokens,u.image_output_tokens,u.total_reported_tokens,
                u.other_units,pricing.components
                FROM cost_lab.tryon_usage u
                JOIN cost_lab.tryon_runs t USING(tryon_id)
                JOIN cost_lab.benchmark_runs r USING(run_id)
                LEFT JOIN LATERAL (
                  SELECT components FROM cost_lab.model_pricing mp
                  WHERE mp.model_id=r.model_id AND mp.effective_at <= now()
                  ORDER BY mp.effective_at DESC LIMIT 1
                ) pricing ON true""")
            ).mappings().all()
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

    @app.get("/api/cost-lab/results/{run_id}")
    def result_detail(run_id: UUID, _: Auth) -> dict[str, Any]:
        with service.engine.begin() as connection:
            run = connection.execute(
                text("""SELECT r.run_id,r.status,r.created_at,r.finished_at,m.name model_name,
                p.name provider_name FROM cost_lab.benchmark_runs r
                JOIN cost_lab.ai_models m USING(model_id)
                JOIN cost_lab.model_providers p USING(provider_id) WHERE r.run_id=:id"""),
                {"id": run_id},
            ).mappings().one_or_none()
            if run is None:
                raise HTTPException(404, "Benchmark result not found")
            items = _rows(
                connection.execute(
                    text("""SELECT t.*,c.ordinal,c.quality,c.person_asset_id,c.product_asset_id,
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
            item["person_url"] = f"/api/cost-lab/assets/{item['person_asset_id']}/content"
            item["product_url"] = f"/api/cost-lab/assets/{item['product_asset_id']}/content"
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

    return app


def run() -> None:
    import uvicorn

    uvicorn.run("apps.cost_lab_api.app:create_app", factory=True, host="127.0.0.1", port=8011)
