from __future__ import annotations

import html
import json
import re
from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import requests
from sqlalchemy import Engine, text

Channel = Literal["EMAIL", "SMS", "WHATSAPP"]
TemplateStatus = Literal["DRAFT", "ACTIVE", "ARCHIVED"]

_VARIABLE = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}")
_BRACKET_VARIABLE = re.compile(r"\[([a-zA-Z][a-zA-Z0-9_]*)\]")
_REFERENCE_IMAGE = re.compile(
    r"^data:image/(?:png|jpeg|webp|gif);base64,(?P<data>[A-Za-z0-9+/]+={0,2})$"
)
_HTML_TAG = re.compile(r"<[^>]+>")
_IMAGE_TAG = re.compile(r"<img\b[^>]*>", re.I)
_STANDALONE_WEARO_LINE = re.compile(
    r"<(?P<tag>p|div|span)\b[^>]*>\s*(?:<a\b[^>]*>)?\s*"
    r"(?:https?://)?(?:www\.)?wearo\.ai/?\s*(?:</a>)?\s*</(?P=tag)>",
    re.I,
)
_CTA_ANCHOR = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<label>[^<]*(?:sign in|dashboard|view report|pay now)[^<]*)</a>",
    re.I,
)
_TEMPLATE_KEYS = {
    "WELCOME",
    "NEW_FEATURES",
    "MONTHLY_REPORT",
    "SUPPORT_DEFAULT_RESPONSE",
    "BILLING_MONTH_START",
    "BILLING_DAY_BEFORE",
    "BILLING_DUE_DAY",
    "BILLING_PAUSE_DAY_1",
    "BILLING_PAUSE_DAY_3",
    "BILLING_ACCOUNT_PAUSED_DAY_7",
}
TEMPLATE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "WELCOME": ("NOTIFICATION", "Welcome"),
    "NEW_FEATURES": ("NOTIFICATION", "New features"),
    "MONTHLY_REPORT": ("NOTIFICATION", "Monthly report"),
    "SUPPORT_DEFAULT_RESPONSE": ("SUPPORT", "Default support response"),
    "BILLING_MONTH_START": ("BILLING", "Monthly first billing notification"),
    "BILLING_DAY_BEFORE": ("BILLING", "Day before billing notification"),
    "BILLING_DUE_DAY": ("BILLING", "Due-day billing notification"),
    "BILLING_PAUSE_DAY_1": ("BILLING", "One day after due date"),
    "BILLING_PAUSE_DAY_3": ("BILLING", "Three days after due date"),
    "BILLING_ACCOUNT_PAUSED_DAY_7": ("BILLING", "Account paused after seven days"),
}


class NotificationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EmailSender(Protocol):
    def send(
        self, *, to_address: str, subject: str, body: str, signature: str, category: str
    ) -> str: ...


@dataclass(frozen=True)
class ClaimedNotification:
    job_id: UUID
    channel: Channel
    template_key: str
    recipient: str
    variables: dict[str, object]
    attempt_count: int
    max_attempts: int
    metadata: dict[str, object] = field(default_factory=dict)


class SesEmailSender:
    """Amazon SES v2 adapter. The boto3 client is created once and reused."""

    def __init__(
        self,
        client: Any,
        *,
        from_address: str,
        support_address: str | None = None,
        billing_address: str | None = None,
        reply_to: str | None = None,
        asset_origin: str | None = None,
        logo_bytes: bytes | None = None,
        campaign_bytes: bytes | None = None,
    ) -> None:
        if not from_address.strip():
            raise ValueError("SES from address is required")
        self.client = client
        self.from_address = from_address.strip()
        self.support_address = (support_address or from_address).strip()
        self.billing_address = (billing_address or from_address).strip()
        self.reply_to = reply_to.strip() if reply_to else None
        self.asset_origin = (asset_origin or "").rstrip("/")
        self.logo_bytes = logo_bytes
        self.campaign_bytes = campaign_bytes

    def send(
        self, *, to_address: str, subject: str, body: str, signature: str, category: str
    ) -> str:
        clean_body = _IMAGE_TAG.sub("", body).strip()
        clean_signature = _IMAGE_TAG.sub("", signature).strip()
        if re.search(r"\bteam\s+wearo(?:\.ai)?\b", clean_signature, re.I):
            clean_signature = _STANDALONE_WEARO_LINE.sub("", clean_signature).strip()
        body_has_signature = bool(
            re.search(
                r"\b(from the (?:wearo\.ai )?team|team wearo(?:\.ai)?)\b", clean_body, re.I
            )
        )
        rendered_signature = "" if body_has_signature else clean_signature
        full_body = clean_body.rstrip() + (
            f"\n\n{rendered_signature}" if rendered_signature else ""
        )
        contains_html = bool(_HTML_TAG.search(full_body))
        body_html = (
            clean_body
            if _HTML_TAG.search(clean_body)
            else html.escape(clean_body).replace("\n", "<br>")
        )
        signature_html = (
            rendered_signature
            if _HTML_TAG.search(rendered_signature)
            else html.escape(rendered_signature).replace("\n", "<br>")
        )

        def style_cta(match: re.Match[str]) -> str:
            attrs = re.sub(r"\sstyle=(?:\"[^\"]*\"|'[^']*')", "", match.group("attrs"), flags=re.I)
            return (
                f'<a{attrs} style="display:inline-block;padding:12px 20px;border-radius:8px;'
                'color:#ffffff;background:#6f3d82;text-decoration:none;font-weight:700">'
                f'{match.group("label")}</a>'
            )

        body_html = _CTA_ANCHOR.sub(style_cta, body_html)
        text_body = html.unescape(_HTML_TAG.sub("", full_body)) if contains_html else full_body
        signature_block = (
            '<div style="max-width:520px;margin-top:32px;padding-top:20px;'
            'border-top:1px solid rgba(255,255,255,0.35);font-size:16px;font-weight:700">'
            f"{signature_html}</div>"
            if rendered_signature
            else ""
        )
        email_content = (
            '<div style="max-width:520px;font-size:17px;line-height:1.6;text-align:left">'
            f"{body_html}{signature_block}</div>"
        )
        logo_source = (
            "cid:wearo-logo"
            if self.logo_bytes
            else f"{html.escape(self.asset_origin)}/wearo-brand_white_bg.png?v=20261114-email-2"
        )
        logo = (
            f'<img src="{logo_source}" '
            'alt="Wearo.ai" width="150" style="display:block;max-width:150px;height:auto;'
            'margin:0 0 32px">'
            if self.asset_origin or self.logo_bytes
            else '<strong style="display:block;text-align:center;font-size:22px">Wearo.ai</strong>'
        )
        if self.asset_origin or self.campaign_bytes:
            campaign_url = (
                "cid:wearo-campaign"
                if self.campaign_bytes
                else f"{html.escape(self.asset_origin)}/wearo-hero-campaign.webp"
            )
            message = (
                f'<div background="{campaign_url}" style="background-color:#321d32;'
                f"background-image:url('{campaign_url}');background-position:center;"
                'background-size:cover;border-radius:12px;overflow:hidden">'
                '<div style="padding:48px 36px;color:#ffffff;'
                'background:rgba(28,12,29,0.72)">'
                f"{logo}{email_content}</div></div>"
            )
        else:
            message = f"{logo}{email_content}"
        branded_html = (
            '<div style="max-width:640px;margin:0 auto;font-family:Arial,sans-serif;'
            'color:#2d2430;line-height:1.65">'
            f'<div style="padding:24px 0">{message}</div></div>'
        )
        request: dict[str, object] = {
            "FromEmailAddress": {
                "SUPPORT": self.support_address,
                "BILLING": self.billing_address,
            }.get(category, self.from_address),
            "Destination": {"ToAddresses": [to_address]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {
                            "Data": branded_html,
                            "Charset": "UTF-8",
                        },
                    },
                }
            },
        }
        if self.reply_to:
            request["ReplyToAddresses"] = [self.reply_to]
        if self.logo_bytes or self.campaign_bytes:
            message = EmailMessage()
            message["From"] = str(request["FromEmailAddress"])
            message["To"] = to_address
            message["Subject"] = subject
            if self.reply_to:
                message["Reply-To"] = self.reply_to
            message.set_content(text_body)
            message.add_alternative(branded_html, subtype="html")
            html_part = message.get_payload()[-1]
            if self.logo_bytes:
                html_part.add_related(
                    self.logo_bytes,
                    maintype="image",
                    subtype="png",
                    cid="<wearo-logo>",
                    filename="wearo-brand_white_bg.png",
                    disposition="inline",
                )
            if self.campaign_bytes:
                html_part.add_related(
                    self.campaign_bytes,
                    maintype="image",
                    subtype="webp",
                    cid="<wearo-campaign>",
                    filename="wearo-campaign.webp",
                    disposition="inline",
                )
            request = {"Content": {"Raw": {"Data": message.as_bytes()}}}
        response = self.client.send_email(**request)
        return str(response["MessageId"])


class OpenAITemplateGenerator:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str, *, timeout_seconds: int = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _input(prompt: str, reference_image: str | None) -> object:
        if reference_image is None:
            return prompt
        match = _REFERENCE_IMAGE.fullmatch(reference_image)
        if match is None:
            raise NotificationError(
                "INVALID_REFERENCE_IMAGE", "Use a PNG, JPEG, WEBP, or non-animated GIF image."
            )
        try:
            image_bytes = b64decode(match.group("data"), validate=True)
        except (Base64Error, ValueError):
            raise NotificationError(
                "INVALID_REFERENCE_IMAGE", "The reference image could not be read."
            ) from None
        if not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
            raise NotificationError(
                "INVALID_REFERENCE_IMAGE", "The reference image must be 5 MB or smaller."
            )
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": reference_image, "detail": "high"},
                ],
            }
        ]

    def generate(
        self,
        *,
        channel: Channel,
        template_key: str,
        prompt: str,
        reference_image: str | None = None,
    ) -> dict[str, str]:
        if not self.api_key or not self.model:
            raise NotificationError(
                "TEMPLATE_AI_UNAVAILABLE", "AI template generation is unavailable."
            )
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": self._input((
                    "Create a concise Wearo.ai customer communication template. "
                    "Return JSON matching the schema. Preserve useful "
                    "{{variable_name}} placeholders. "
                    "For every EMAIL template, write body and signature HTML that is suitable "
                    "for display over the standard Wearo campaign background image: use "
                    "high-contrast light text, short paragraphs, email-safe inline styles, and no "
                    "body-level "
                    "background image because the Wearo renderer supplies and dims it. "
                    "The renderer also supplies exactly one Wearo logo at the top of the email, "
                    "so never add a logo, logo placeholder, image, or brand header to body or "
                    "signature. Body must contain message content only and must never contain "
                    "a sign-off, sender name, 'From the team', or signature. Put the sign-off "
                    "only in the signature field so it appears exactly once. The signature must "
                    "be one simple text line: 'Team Wearo.ai'. Do not repeat Wearo.ai as a second "
                    "line, URL, label, image, or logo, and do not include an email address in the "
                    "signature. Use "
                    "{{customer_login_url}} for customer sign-in links and "
                    "{{support_email}} for support contact details. Use concise paragraphs, keep "
                    "content left aligned, and make the single primary "
                    "action a clearly labelled link; the renderer styles it as a button. "
                    "These layout rules are mandatory and the admin prompt may only control "
                    "content, audience, and tone. "
                    "Do not invent discounts, policies, dates, payment status, or commitments. "
                    "When a reference image is supplied, use it only for visual inspiration such "
                    "as hierarchy, spacing, tone, and color contrast. Do not identify people, copy "
                    "visible personal information, reproduce logos, or insert the reference image "
                    "into the email. "
                    f"Channel: {channel}. Template purpose: {template_key}. Admin prompt: {prompt}"
                ), reference_image),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "communication_template",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                                "signature": {"type": "string"},
                            },
                            "required": ["subject", "body", "signature"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise NotificationError("TEMPLATE_AI_FAILED", "The template could not be generated.")
        try:
            data = response.json()
            output_text = next(
                part["text"]
                for item in data["output"]
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            generated = json.loads(output_text)
            return {name: str(generated[name]).strip() for name in ("subject", "body", "signature")}
        except (KeyError, StopIteration, TypeError, ValueError, requests.JSONDecodeError):
            raise NotificationError(
                "TEMPLATE_AI_FAILED", "The template response was invalid."
            ) from None

    def generate_all(
        self, *, channel: Channel, prompt: str, reference_image: str | None = None
    ) -> tuple[dict[str, str], ...]:
        if not self.api_key or not self.model:
            raise NotificationError(
                "TEMPLATE_AI_UNAVAILABLE", "AI template generation is unavailable."
            )
        keys = list(TEMPLATE_DEFINITIONS)
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "max_output_tokens": 16000,
                "input": self._input((
                    "Create one concise Wearo.ai customer communication template for every "
                    "purpose listed below, applying the same admin creative brief consistently. "
                    "Preserve useful {{variable_name}} placeholders. For every EMAIL template, "
                    "use high-contrast light text, short paragraphs, and email-safe "
                    "inline HTML suitable for a dimmed campaign background. Never add a logo, "
                    "image, background, brand header, or signature to body. Body contains message "
                    "content only. Put the sign-off only in signature so it appears exactly once. "
                    "The signature must be one simple text line: 'Team Wearo.ai'. Never put an "
                    "image, logo, URL, email address, or second Wearo.ai line in the signature. "
                    "Use {{customer_login_url}} for sign-in and {{support_email}} for support. "
                    "Keep content left aligned with concise paragraphs and include no more than "
                    "one primary action link; the renderer styles that action as a button. "
                    "For SMS and WHATSAPP use plain text and return an empty subject. "
                    "Do not invent "
                    "discounts, policies, dates, payment status, or commitments. "
                    "When a reference image is supplied, use it only for consistent visual "
                    "inspiration such as hierarchy, spacing, tone, and contrast. Do not identify "
                    "people, copy personal information, reproduce logos, or insert the reference "
                    "image into any email. "
                    f"Channel: {channel}. Purposes: {', '.join(keys)}. Admin brief: {prompt}"
                ), reference_image),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "communication_template_batch",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "templates": {
                                    "type": "array",
                                    "minItems": len(keys),
                                    "maxItems": len(keys),
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "template_key": {"type": "string", "enum": keys},
                                            "subject": {"type": "string"},
                                            "body": {"type": "string"},
                                            "signature": {"type": "string"},
                                        },
                                        "required": [
                                            "template_key",
                                            "subject",
                                            "body",
                                            "signature",
                                        ],
                                        "additionalProperties": False,
                                    },
                                }
                            },
                            "required": ["templates"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
            timeout=max(self.timeout_seconds, 120),
        )
        if response.status_code != 200:
            raise NotificationError("TEMPLATE_AI_FAILED", "The templates could not be generated.")
        try:
            data = response.json()
            output_text = next(
                part["text"]
                for item in data["output"]
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            generated = json.loads(output_text)["templates"]
            by_key = {str(item["template_key"]): item for item in generated}
            if set(by_key) != set(keys):
                raise ValueError("incomplete template batch")
            return tuple(
                {
                    "template_key": key,
                    "subject": str(by_key[key]["subject"]).strip(),
                    "body": str(by_key[key]["body"]).strip(),
                    "signature": str(by_key[key]["signature"]).strip(),
                }
                for key in keys
            )
        except (KeyError, StopIteration, TypeError, ValueError, requests.JSONDecodeError):
            raise NotificationError(
                "TEMPLATE_AI_FAILED", "The template batch response was invalid."
            ) from None


def _render(value: str | None, variables: dict[str, object]) -> str:
    source = value or ""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise NotificationError(
                "MISSING_TEMPLATE_VARIABLE", f"Missing template variable: {key}."
            )
        return str(variables[key])

    return _BRACKET_VARIABLE.sub(replace, _VARIABLE.sub(replace, source))


def template_variable_names(*values: str | None) -> set[str]:
    """Return every supported placeholder name used by template content."""
    names: set[str] = set()
    for value in values:
        source = value or ""
        names.update(_VARIABLE.findall(source))
        names.update(_BRACKET_VARIABLE.findall(source))
    return names


class PostgresNotificationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_templates(self, channel: Channel | None = None) -> tuple[dict[str, object], ...]:
        where_clause = "WHERE channel=:channel" if channel is not None else ""
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(f"""SELECT template_id, channel, template_key, category, display_name,
                    subject, body, signature, generation_prompt, status, version, updated_at
                  FROM communication_templates
                  {where_clause}
                  ORDER BY channel, category, display_name, version DESC"""),  # noqa: S608
                {"channel": channel} if channel is not None else {},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def save_template(
        self,
        *,
        channel: Channel,
        template_key: str,
        category: str,
        display_name: str,
        subject: str | None,
        body: str,
        signature: str | None,
        prompt: str | None,
        status: TemplateStatus,
    ) -> dict[str, object]:
        key = template_key.strip().upper()
        if key not in _TEMPLATE_KEYS:
            raise NotificationError("INVALID_TEMPLATE_KEY", "Select a supported template purpose.")
        if channel == "EMAIL" and not (subject or "").strip():
            raise NotificationError("SUBJECT_REQUIRED", "Email templates require a subject.")
        if not body.strip() or len(body) > 20_000:
            raise NotificationError("INVALID_TEMPLATE_BODY", "Template body is required.")
        if "\r" in (subject or "") or "\n" in (subject or ""):
            raise NotificationError("INVALID_TEMPLATE_SUBJECT", "Subject must be one line.")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            version = connection.execute(
                text("""SELECT COALESCE(MAX(version),0)+1 FROM communication_templates
                  WHERE channel=:channel AND template_key=:key"""),
                {"channel": channel, "key": key},
            ).scalar_one()
            if status == "ACTIVE":
                connection.execute(
                    text("""UPDATE communication_templates SET status='DRAFT', updated_at=:now
                      WHERE channel=:channel AND template_key=:key AND status='ACTIVE'"""),
                    {"channel": channel, "key": key, "now": now},
                )
            row = (
                connection.execute(
                    text("""INSERT INTO communication_templates
                  (template_id,channel,template_key,category,display_name,subject,body,
                   signature,generation_prompt,status,version,created_at,updated_at)
                  VALUES (:id,:channel,:key,:category,:name,:subject,:body,:signature,
                          :prompt,:status,:version,:now,:now)
                  RETURNING template_id,channel,template_key,category,display_name,subject,
                            body,signature,generation_prompt,status,version,updated_at"""),
                    {
                        "id": uuid4(),
                        "channel": channel,
                        "key": key,
                        "category": category,
                        "name": display_name.strip(),
                        "subject": (subject or "").strip() or None,
                        "body": body.strip(),
                        "signature": (signature or "").strip() or None,
                        "prompt": (prompt or "").strip() or None,
                        "status": status,
                        "version": version,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            return dict(row)

    def activate_template(self, template_id: UUID) -> dict[str, object]:
        """Activate one draft and demote the current version in the same transaction."""
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            selected = (
                connection.execute(
                    text("""SELECT template_id,channel,template_key,status
                      FROM communication_templates WHERE template_id=:id"""),
                    {"id": template_id},
                )
                .mappings()
                .one_or_none()
            )
            if selected is None:
                raise NotificationError("TEMPLATE_NOT_FOUND", "Template version was not found.")
            if selected["status"] == "ACTIVE":
                return self.template_version(template_id)
            if selected["status"] != "DRAFT":
                raise NotificationError(
                    "TEMPLATE_NOT_DRAFT", "Only a draft template can be made active."
                )

            # Lock every version for this purpose so concurrent activation requests cannot
            # violate the partial unique index that permits only one active version.
            connection.execute(
                text("""SELECT template_id FROM communication_templates
                  WHERE channel=:channel AND template_key=:key
                  ORDER BY template_id FOR UPDATE"""),
                {"channel": selected["channel"], "key": selected["template_key"]},
            ).all()
            connection.execute(
                text("""UPDATE communication_templates SET status='DRAFT',updated_at=:now
                  WHERE channel=:channel AND template_key=:key AND status='ACTIVE'"""),
                {
                    "channel": selected["channel"],
                    "key": selected["template_key"],
                    "now": now,
                },
            )
            row = (
                connection.execute(
                    text("""UPDATE communication_templates SET status='ACTIVE',updated_at=:now
                      WHERE template_id=:id
                      RETURNING template_id,channel,template_key,category,display_name,subject,
                                body,signature,generation_prompt,status,version,updated_at"""),
                    {"id": template_id, "now": now},
                )
                .mappings()
                .one()
            )
            return dict(row)

    def delete_template(self, template_id: UUID) -> None:
        with self.engine.begin() as connection:
            template = (
                connection.execute(
                    text("""SELECT channel,template_key,status FROM communication_templates
                      WHERE template_id=:id FOR UPDATE"""),
                    {"id": template_id},
                )
                .mappings()
                .one_or_none()
            )
            if template is None:
                raise NotificationError("TEMPLATE_NOT_FOUND", "Template version was not found.")
            processing = connection.execute(
                text("""SELECT 1 FROM communication_jobs
                  WHERE channel=:channel AND template_key=:key AND status='PROCESSING'
                  LIMIT 1"""),
                {"channel": template["channel"], "key": template["template_key"]},
            ).scalar_one_or_none()
            if processing is not None and template["status"] == "ACTIVE":
                raise NotificationError(
                    "TEMPLATE_IN_USE",
                    "Wait for the notification currently using this template to finish.",
                )
            if template["status"] == "ACTIVE":
                connection.execute(
                    text("""UPDATE communication_jobs
                      SET status='CANCELLED',last_error_code='TEMPLATE_DELETED',updated_at=now()
                      WHERE channel=:channel AND template_key=:key
                        AND status IN ('QUEUED','RETRY')"""),
                    {"channel": template["channel"], "key": template["template_key"]},
                )
            connection.execute(
                text("DELETE FROM communication_templates WHERE template_id=:id"),
                {"id": template_id},
            )

    def delete_all_templates(self, channel: Channel) -> int:
        with self.engine.begin() as connection:
            processing = connection.execute(
                text("""SELECT 1 FROM communication_jobs
                  WHERE channel=:channel AND status='PROCESSING' LIMIT 1"""),
                {"channel": channel},
            ).scalar_one_or_none()
            if processing is not None:
                raise NotificationError(
                    "TEMPLATE_IN_USE",
                    "Wait for notifications currently being delivered to finish.",
                )
            connection.execute(
                text("""UPDATE communication_jobs
                  SET status='CANCELLED',last_error_code='TEMPLATES_DELETED',updated_at=now()
                  WHERE channel=:channel AND status IN ('QUEUED','RETRY')"""),
                {"channel": channel},
            )
            result = connection.execute(
                text("DELETE FROM communication_templates WHERE channel=:channel"),
                {"channel": channel},
            )
            return result.rowcount

    def enqueue(
        self,
        *,
        channel: Channel,
        template_key: str,
        recipient: str,
        variables: dict[str, object],
        metadata: dict[str, object] | None = None,
        deduplication_key: str | None = None,
        scheduled_at: datetime | None = None,
    ) -> UUID:
        key, target = template_key.strip().upper(), recipient.strip()
        if key not in _TEMPLATE_KEYS or not target:
            raise NotificationError("INVALID_NOTIFICATION", "Recipient and template are required.")
        job_id, now = uuid4(), datetime.now(UTC)
        with self.engine.begin() as connection:
            result = connection.execute(
                text("""INSERT INTO communication_jobs
                  (job_id,channel,template_key,recipient,variables,metadata,deduplication_key,
                   scheduled_at,created_at,updated_at)
                  VALUES (:id,:channel,:key,:recipient,CAST(:variables AS jsonb),
                          CAST(:metadata AS jsonb),
                          :dedupe,:scheduled,:now,:now)
                  ON CONFLICT (deduplication_key) WHERE deduplication_key IS NOT NULL DO NOTHING
                  RETURNING job_id"""),
                {
                    "id": job_id,
                    "channel": channel,
                    "key": key,
                    "recipient": target,
                    "variables": json.dumps(variables, default=str),
                    "metadata": json.dumps(metadata or {}, default=str),
                    "dedupe": deduplication_key,
                    "scheduled": scheduled_at or now,
                    "now": now,
                },
            ).scalar_one_or_none()
            if result is not None:
                return result
            return connection.execute(
                text("SELECT job_id FROM communication_jobs WHERE deduplication_key=:key"),
                {"key": deduplication_key},
            ).scalar_one()

    def claim(self, worker_id: str, *, now: datetime | None = None) -> ClaimedNotification | None:
        current = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                text("""UPDATE communication_jobs SET status='RETRY', leased_by=NULL,
                    lease_expires_at=NULL, updated_at=:now
                  WHERE status='PROCESSING' AND lease_expires_at < :now"""),
                {"now": current},
            )
            row = (
                connection.execute(
                    text("""WITH candidate AS (
                    SELECT job_id FROM communication_jobs
                    WHERE status IN ('QUEUED','RETRY') AND scheduled_at <= :now
                    ORDER BY scheduled_at, created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                  UPDATE communication_jobs j SET status='PROCESSING', leased_by=:worker,
                    lease_expires_at=:lease, attempt_count=j.attempt_count+1, updated_at=:now
                  FROM candidate WHERE j.job_id=candidate.job_id
                  RETURNING j.job_id,j.channel,j.template_key,j.recipient,j.variables,
                            j.metadata,j.attempt_count,j.max_attempts"""),
                    {"now": current, "worker": worker_id, "lease": current + timedelta(minutes=2)},
                )
                .mappings()
                .one_or_none()
            )
        return ClaimedNotification(**dict(row)) if row else None

    def template_for(self, channel: Channel, key: str) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT category,subject,body,signature FROM communication_templates
                  WHERE channel=:channel AND template_key=:key AND status='ACTIVE'
                  ORDER BY version DESC LIMIT 1"""),
                    {"channel": channel, "key": key},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise NotificationError(
                "ACTIVE_TEMPLATE_NOT_FOUND", "No active template is configured."
            )
        return dict(row)

    def template_version(self, template_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("""SELECT template_id,channel,template_key,category,subject,body,signature
                      FROM communication_templates WHERE template_id=:id"""),
                    {"id": template_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise NotificationError("TEMPLATE_NOT_FOUND", "Template version was not found.")
        return dict(row)

    def delivered(self, job_id: UUID, provider_message_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text("""UPDATE communication_jobs SET status='DELIVERED',
                provider_message_id=:provider, delivered_at=now(), leased_by=NULL,
                lease_expires_at=NULL, updated_at=now() WHERE job_id=:id"""),
                {"id": job_id, "provider": provider_message_id},
            )

    def failed(self, job: ClaimedNotification, code: str) -> None:
        terminal = job.attempt_count >= job.max_attempts
        delay = min(3600, 30 * (2 ** max(0, job.attempt_count - 1)))
        with self.engine.begin() as connection:
            connection.execute(
                text("""UPDATE communication_jobs
                SET status=:status,last_error_code=:code,scheduled_at=:scheduled,
                    leased_by=NULL,lease_expires_at=NULL,updated_at=:now WHERE job_id=:id"""),
                {
                    "status": "FAILED" if terminal else "RETRY",
                    "code": code,
                    "scheduled": datetime.now(UTC) + timedelta(seconds=delay),
                    "now": datetime.now(UTC),
                    "id": job.job_id,
                },
            )

    def ingest_support(
        self,
        *,
        provider_message_id: str,
        sender: str,
        recipient: str,
        subject: str,
        body_text: str,
        received_at: datetime,
    ) -> dict[str, object]:
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    text("""SELECT inbound_message_id,response_job_id
                FROM inbound_support_messages WHERE provider_message_id=:provider"""),
                    {"provider": provider_message_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return dict(existing)
            inbound_id = uuid4()
            response_id = self.enqueue(
                channel="EMAIL",
                template_key="SUPPORT_DEFAULT_RESPONSE",
                recipient=sender,
                variables={"original_subject": subject, "support_reference": str(inbound_id)},
                metadata={"inbound_provider_message_id": provider_message_id},
                deduplication_key=f"support-response:{provider_message_id}",
            )
            connection.execute(
                text("""INSERT INTO inbound_support_messages
                (inbound_message_id,provider_message_id,sender_email,recipient_email,subject,
                 body_text,received_at,response_job_id) VALUES
                (:id,:provider,:sender,:recipient,:subject,:body,:received,:job)"""),
                {
                    "id": inbound_id,
                    "provider": provider_message_id,
                    "sender": sender,
                    "recipient": recipient,
                    "subject": subject[:998],
                    "body": body_text[:100000],
                    "received": received_at,
                    "job": response_id,
                },
            )
            return {"inbound_message_id": inbound_id, "response_job_id": response_id}

    def schedule_billing(self, run_date: date) -> int:
        offsets = {
            1: "BILLING_DAY_BEFORE",
            0: "BILLING_DUE_DAY",
            -1: "BILLING_PAUSE_DAY_1",
            -3: "BILLING_PAUSE_DAY_3",
            -7: "BILLING_ACCOUNT_PAUSED_DAY_7",
        }
        count = 0
        with self.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    text("""SELECT s.subscription_id,s.next_billing_at,
                p.billing_email,p.legal_name FROM business_subscriptions s
                JOIN business_profiles p ON p.tenant_id=s.tenant_id AND p.account_id=s.account_id
                WHERE s.next_billing_at IS NOT NULL AND s.state NOT IN ('CANCELLED','EXPIRED')
                  AND (:month_start OR s.next_billing_at::date BETWEEN :start AND :end)"""),
                    {
                        "start": run_date - timedelta(days=7),
                        "end": run_date + timedelta(days=1),
                        "month_start": run_date.day == 1,
                    },
                ).mappings()
            )
        for row in rows:
            if run_date.day == 1:
                self.enqueue(
                    channel="EMAIL",
                    template_key="BILLING_MONTH_START",
                    recipient=row["billing_email"],
                    variables={
                        "name": row["legal_name"],
                        "billing_month": run_date.strftime("%B %Y"),
                        "amount_due": "the amount shown on your invoice",
                        "due_date": row["next_billing_at"].date().isoformat(),
                    },
                    deduplication_key=(
                        f"billing:{row['subscription_id']}:BILLING_MONTH_START:"
                        f"{run_date.isoformat()}"
                    ),
                )
                count += 1
            delta = (row["next_billing_at"].date() - run_date).days
            key = offsets.get(delta)
            if key:
                self.enqueue(
                    channel="EMAIL",
                    template_key=key,
                    recipient=row["billing_email"],
                    variables={
                        "name": row["legal_name"],
                        "amount_due": "the amount shown on your invoice",
                        "due_date": row["next_billing_at"].date().isoformat(),
                    },
                    deduplication_key=f"billing:{row['subscription_id']}:{key}:{run_date.isoformat()}",
                )
                count += 1
        return count


class NotificationWorker:
    def __init__(
        self,
        service: PostgresNotificationService,
        email: EmailSender,
        worker_id: str,
        *,
        standard_variables: dict[str, object] | None = None,
    ) -> None:
        self.service, self.email, self.worker_id = service, email, worker_id
        self.standard_variables = standard_variables or {}

    def run_once(self) -> bool:
        job = self.service.claim(self.worker_id)
        if job is None:
            return False
        try:
            template_id = job.metadata.get("template_id")
            template = (
                self.service.template_version(UUID(str(template_id)))
                if template_id
                else self.service.template_for(job.channel, job.template_key)
            )
            if job.channel != "EMAIL":
                raise NotificationError(
                    "CHANNEL_NOT_CONFIGURED", "Channel delivery is not configured."
                )
            variables = {**self.standard_variables, **job.variables}
            provider_id = self.email.send(
                to_address=job.recipient,
                subject=_render(str(template.get("subject") or ""), variables),
                body=_render(str(template["body"]), variables),
                signature=_render(str(template.get("signature") or ""), variables),
                category=str(template["category"]),
            )
            self.service.delivered(job.job_id, provider_id)
        except Exception as error:
            code = error.code if isinstance(error, NotificationError) else type(error).__name__
            self.service.failed(job, code[:100])
        return True
