from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.api.wearo_api.notification_delivery import (
    ClaimedNotification,
    NotificationError,
    NotificationWorker,
    OpenAITemplateGenerator,
    SesEmailSender,
    _render,
)


class FakeSes:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def send_email(self, **request: object) -> dict[str, str]:
        self.request = request
        return {"MessageId": "ses-message-1"}


def test_ses_sender_uses_billing_identity_and_escapes_html() -> None:
    client = FakeSes()
    sender = SesEmailSender(
        client,
        from_address="notify@example.com",
        support_address="support@example.com",
        billing_address="billing@example.com",
        reply_to="support@example.com",
        asset_origin="https://wearo.example",
    )

    message_id = sender.send(
        to_address="customer@example.com",
        subject="Payment due",
        body="Amount < INR 100",
        signature="Wearo Billing",
        category="BILLING",
    )

    assert message_id == "ses-message-1"
    assert client.request is not None
    assert client.request["FromEmailAddress"] == "billing@example.com"
    assert client.request["ReplyToAddresses"] == ["support@example.com"]
    html_body = client.request["Content"]["Simple"]["Body"]["Html"]["Data"]
    assert "Amount &lt; INR 100" in html_body
    assert "https://wearo.example/wearo-hero-campaign.webp" in html_body


def test_ses_sender_uses_campaign_background_for_support_email() -> None:
    client = FakeSes()
    sender = SesEmailSender(
        client,
        from_address="notify@example.com",
        support_address="support@example.com",
        asset_origin="https://wearo.example",
    )

    sender.send(
        to_address="customer@example.com",
        subject="Support request",
        body="We received your request.",
        signature="Team Wearo.ai",
        category="SUPPORT",
    )

    assert client.request is not None
    html_body = client.request["Content"]["Simple"]["Body"]["Html"]["Data"]
    assert "https://wearo.example/wearo-hero-campaign.webp" in html_body
    assert html_body.count("wearo-brand_white_bg.png") == 1


def test_template_render_requires_every_placeholder() -> None:
    assert _render("Hello {{ name }}", {"name": "Madhu"}) == "Hello Madhu"
    assert _render("Hello [first_name]", {"first_name": "Ananya"}) == "Hello Ananya"
    with pytest.raises(NotificationError, match="Missing template variable"):
        _render("Due {{due_date}}", {})


def test_template_generator_builds_optional_multimodal_input() -> None:
    prompt = "Create a premium welcome email."
    reference = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    assert OpenAITemplateGenerator._input(prompt, None) == prompt
    multimodal = OpenAITemplateGenerator._input(prompt, reference)
    assert multimodal[0]["content"][0] == {"type": "input_text", "text": prompt}
    assert multimodal[0]["content"][1] == {
        "type": "input_image",
        "image_url": reference,
        "detail": "high",
    }


def test_template_generator_rejects_invalid_reference_image() -> None:
    with pytest.raises(NotificationError, match="PNG, JPEG, WEBP, or non-animated GIF"):
        OpenAITemplateGenerator._input("Create an email", "data:text/plain;base64,SGVsbG8=")


def test_ses_sender_renders_authored_html_instead_of_showing_tags() -> None:
    client = FakeSes()
    sender = SesEmailSender(
        client, from_address="notify@example.com", asset_origin="https://wearo.example"
    )

    sender.send(
        to_address="customer@example.com",
        subject="Welcome",
        body='<p>Hello</p><img src="https://example.com/welcome.png" alt="Welcome">',
        signature="<p>Wearo.ai</p>",
        category="NOTIFICATION",
    )

    assert client.request is not None
    content = client.request["Content"]["Simple"]["Body"]
    assert "<p>Hello</p>" in content["Html"]["Data"]
    assert "&lt;p&gt;" not in content["Html"]["Data"]
    assert (
        "https://wearo.example/wearo-brand_white_bg.png?v=20261114-email-2"
        in content["Html"]["Data"]
    )
    assert content["Html"]["Data"].count("wearo-brand_white_bg.png") == 1
    assert "https://wearo.example/wearo-hero-campaign.webp" in content["Html"]["Data"]
    assert "Hello" in content["Text"]["Data"]


def test_ses_sender_removes_template_images_and_duplicate_wearo_signature_line() -> None:
    client = FakeSes()
    sender = SesEmailSender(
        client, from_address="notify@example.com", asset_origin="https://wearo.example"
    )

    sender.send(
        to_address="customer@example.com",
        subject="Welcome",
        body='<p>Welcome</p><img src="https://broken.example/extra.png" alt="Extra logo">',
        signature=(
            '<div><img src="https://broken.example/logo.png" alt="Wearo logo">'
            "Team Wearo.ai</div><p>wearo.ai</p>"
        ),
        category="NOTIFICATION",
    )

    assert client.request is not None
    html_body = client.request["Content"]["Simple"]["Body"]["Html"]["Data"]
    assert "broken.example" not in html_body
    assert html_body.count("wearo-brand_white_bg.png") == 1
    assert html_body.count("Team Wearo.ai") == 1
    assert "<p>wearo.ai</p>" not in html_body


def test_ses_sender_embeds_brand_assets_in_raw_email() -> None:
    client = FakeSes()
    sender = SesEmailSender(
        client,
        from_address="notify@example.com",
        logo_bytes=b"logo-png",
        campaign_bytes=b"campaign-webp",
    )

    sender.send(
        to_address="customer@example.com",
        subject="Welcome",
        body="Welcome to Wearo.ai",
        signature="Team Wearo.ai",
        category="NOTIFICATION",
    )

    assert client.request is not None
    raw = client.request["Content"]["Raw"]["Data"]
    assert b"cid:wearo-logo" in raw
    assert b"cid:wearo-campaign" in raw
    assert b"Content-ID: <wearo-logo>" in raw
    assert b"Content-ID: <wearo-campaign>" in raw


def test_ses_sender_does_not_repeat_legacy_body_signature() -> None:
    client = FakeSes()
    sender = SesEmailSender(client, from_address="notify@example.com")

    sender.send(
        to_address="customer@example.com",
        subject="Welcome",
        body="Welcome.\n\nFrom the team,\nWearo.ai",
        signature="The Wearo.ai team",
        category="NOTIFICATION",
    )

    assert client.request is not None
    text_body = client.request["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert text_body.count("team") == 1


class FakeService:
    def __init__(self) -> None:
        self.job = ClaimedNotification(
            uuid4(), "EMAIL", "WELCOME", "person@example.com", {"name": "A"}, 1, 5
        )
        self.delivery: tuple[object, ...] | None = None

    def claim(self, worker_id: str) -> ClaimedNotification:
        assert worker_id == "worker-1"
        return self.job

    def template_for(self, channel: str, key: str) -> dict[str, object]:
        return {
            "category": "NOTIFICATION",
            "subject": "Welcome {{name}}",
            "body": "Hello {{name}}",
            "signature": "Wearo",
        }

    def delivered(self, job_id: object, provider_message_id: str) -> None:
        self.delivery = (job_id, provider_message_id)

    def failed(self, job: object, code: str) -> None:
        raise AssertionError((job, code))


class FakeEmail:
    def send(self, **message: object) -> str:
        assert message["subject"] == "Welcome A"
        assert message["body"] == "Hello A"
        assert message["category"] == "NOTIFICATION"
        return "provider-1"


def test_worker_renders_active_template_and_marks_delivery() -> None:
    service = FakeService()
    worker = NotificationWorker(service, FakeEmail(), "worker-1")

    assert worker.run_once() is True
    assert service.delivery == (service.job.job_id, "provider-1")


def test_worker_uses_exact_saved_version_for_test_email() -> None:
    template_id = uuid4()
    service = FakeService()
    service.job = ClaimedNotification(
        uuid4(),
        "EMAIL",
        "WELCOME",
        "Wearo Admin <admin@wearo.ai>",
        {"name": "Wearo Admin"},
        1,
        5,
        {"template_id": str(template_id), "test_email": True},
    )
    def template_version(selected: object) -> dict[str, object]:
        assert selected == template_id
        return {
            "category": "NOTIFICATION",
            "subject": "Welcome {{name}}",
            "body": "Hello {{name}}",
            "signature": "Wearo",
        }

    class TestEmail:
        message: dict[str, object] | None = None

        def send(self, **message: object) -> str:
            self.message = message
            return "provider-test"

    service.template_version = template_version
    email = TestEmail()

    worker = NotificationWorker(service, email, "worker-1")

    assert worker.run_once() is True
    assert service.delivery == (service.job.job_id, "provider-test")
    assert email.message is not None
    assert email.message["to_address"] == "Wearo Admin <admin@wearo.ai>"
    assert email.message["subject"] == "Welcome Wearo Admin"


def test_claimed_notification_accepts_json_variables() -> None:
    claimed = ClaimedNotification(
        uuid4(), "EMAIL", "WELCOME", "a@example.com", {"at": datetime.now(UTC)}, 1, 5
    )
    assert "at" in claimed.variables
