from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import monotonic

import requests

SERVICES = (
    (
        "render-worker",
        "Render worker",
        "WEARO_RENDER_WORKER_HEALTH_URL",
        "http://127.0.0.1:8021/health",
    ),
    (
        "notification-worker",
        "Notification worker",
        "WEARO_NOTIFICATION_WORKER_HEALTH_URL",
        "http://127.0.0.1:8022/health",
    ),
    ("cost-lab-api", "Cost Lab API", "WEARO_COST_LAB_HEALTH_URL", "http://127.0.0.1:8011/health"),
    (
        "cost-lab-worker",
        "Cost Lab worker",
        "WEARO_COST_LAB_WORKER_HEALTH_URL",
        "http://127.0.0.1:8023/health",
    ),
)


def _check(service: tuple[str, str, str, str]) -> dict[str, object]:
    key, name, variable, default_url = service
    url = os.environ.get(variable, default_url).strip()
    started = monotonic()
    try:
        response = requests.get(
            url,
            timeout=2,
            headers={"Accept": "application/json", "User-Agent": "Wearo-Service-Health/1.0"},
        )
        body = response.json()
        healthy = response.status_code == 200 and body.get("status") in {"ok", "ready"}
        detail = (
            "Health check passed."
            if healthy
            else f"Health endpoint returned HTTP {response.status_code}."
        )
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        healthy, detail = False, "Health endpoint could not be reached."
    return {
        "key": key,
        "name": name,
        "healthy": healthy,
        "status": "HEALTHY" if healthy else "UNHEALTHY",
        "detail": detail,
        "response_time_ms": round((monotonic() - started) * 1000),
    }


def current_service_health() -> dict[str, object]:
    with ThreadPoolExecutor(max_workers=len(SERVICES)) as executor:
        services = [
            {
                "key": "wearo-api",
                "name": "Wearo API",
                "healthy": True,
                "status": "HEALTHY",
                "detail": "Admin health API is responding.",
                "response_time_ms": 0,
            },
            *executor.map(_check, SERVICES),
        ]
    return {
        "checked_at": datetime.now(UTC),
        "overall_status": (
            "HEALTHY" if all(item["healthy"] for item in services) else "ISSUES_DETECTED"
        ),
        "services": services,
    }
