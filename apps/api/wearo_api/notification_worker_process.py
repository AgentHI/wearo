from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

import boto3
from botocore.config import Config
from sqlalchemy import create_engine

from .database import normalize_database_url
from .environment import load_wearo_environment
from .notification_delivery import NotificationWorker, PostgresNotificationService, SesEmailSender


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def customer_origin() -> str:
    configured = os.environ.get("WEARO_CONSUMER_ORIGIN", "").strip().rstrip("/")
    if configured:
        return configured
    environment = os.environ.get("WEARO_ENVIRONMENT", "development").strip().casefold()
    return "https://wearo.ai" if environment in {"production", "prod"} else "http://127.0.0.1:5173"


def build_notification_worker() -> NotificationWorker:
    load_wearo_environment()
    engine = create_engine(
        normalize_database_url(_required("WEARO_DATABASE_URL")), pool_pre_ping=True
    )
    ses = boto3.client(
        "sesv2",
        region_name=_required("WEARO_SES_REGION"),
        config=Config(
            retries={"total_max_attempts": 4, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=15,
        ),
    )
    public_assets = Path(__file__).resolve().parents[2] / "web" / "public"
    sender = SesEmailSender(
        ses,
        from_address=_required("SES_NOTIFICATIONS_EMAIL"),
        support_address=os.environ.get("SES_SUPPORT_EMAIL"),
        billing_address=os.environ.get("SES_BILLING_EMAIL"),
        reply_to=os.environ.get("SES_SUPPORT_EMAIL"),
        asset_origin=customer_origin(),
        logo_bytes=(public_assets / "wearo-brand_white_bg.png").read_bytes(),
        campaign_bytes=(public_assets / "wearo-hero-campaign.webp").read_bytes(),
    )
    worker_id = os.environ.get("WEARO_NOTIFICATION_WORKER_ID") or (
        f"{socket.gethostname()}-{os.getpid()}"
    )
    origin = customer_origin()
    return NotificationWorker(
        PostgresNotificationService(engine),
        sender,
        worker_id,
        standard_variables={
            "customer_login_url": f"{origin}/business/sign-in",
            "dashboard_url": f"{origin}/business/sign-in",
            "help_center_url": f"{origin}/business/support",
            "support_email": os.environ.get("SES_SUPPORT_EMAIL", "support@wearo.ai"),
            "lady_image_url": f"{origin}/wearo-hero-campaign.webp",
            "wearo_logo_url": f"{origin}/wearo-brand_white_bg.png?v=20261114-email-2",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Wearo durable notification worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 30:
        raise SystemExit("--poll-seconds must be between 0.1 and 30")
    worker = build_notification_worker()
    while True:
        claimed = worker.run_once()
        if args.once:
            print(f"claimed={str(claimed).lower()}")
            return
        if not claimed:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
