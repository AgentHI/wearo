from __future__ import annotations

from decimal import Decimal
from typing import Any

PER_MILLION = {
    "text_input_tokens",
    "image_input_tokens",
    "cached_input_tokens",
    "image_output_tokens",
}


def calculate_cost(usage: dict[str, Any], components: list[dict[str, Any]]) -> Decimal:
    """Price disjoint billable usage. Aggregate tokens are informational only."""
    total = Decimal("0")
    for component in components:
        unit = str(component["unit"])
        component_quality = component.get("quality")
        if component_quality is not None and str(component_quality).upper() != str(
            usage.get("output_quality", "")
        ).upper():
            continue
        quantity = Decimal(str(usage.get(unit, 0) or 0))
        price = Decimal(str(component["price_usd"]))
        if unit in PER_MILLION:
            total += quantity * price / Decimal(1_000_000)
        elif unit == "megapixels":
            total += quantity * price
        elif unit in {"runtime_seconds", "requests", "output_images"}:
            total += quantity * price
        elif unit.startswith("custom:"):
            total += quantity * price
    return total.quantize(Decimal("0.00000001"))


def normalized_total_tokens(usage: dict[str, Any]) -> int | None:
    """Never add aggregate tokens to their component fields."""
    reported = usage.get("total_reported_tokens")
    if reported is not None:
        return int(reported)
    values = [usage.get(name) for name in PER_MILLION]
    known = [int(value) for value in values if value is not None]
    return sum(known) if known else None
