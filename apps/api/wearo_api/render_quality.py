from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QualitySignals:
    identity_similarity: float
    product_similarity: float
    color_preserved: bool
    print_preserved: bool
    anatomy_valid: bool
    safe_content: bool
    fabricated_detail: bool


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    hard_failure: bool
    reasons: tuple[str, ...]


class QualityAnalyzer(Protocol):
    def analyze(self, person: bytes, item: bytes, result: bytes) -> QualitySignals: ...


class RenderQualityGate:
    def __init__(
        self,
        analyzer: QualityAnalyzer,
        *,
        identity_minimum: float = 0.90,
        product_minimum: float = 0.90,
    ) -> None:
        self.analyzer = analyzer
        self.identity_minimum = identity_minimum
        self.product_minimum = product_minimum

    def evaluate(self, person: bytes, item: bytes, result: bytes) -> QualityDecision:
        signals = self.analyzer.analyze(person, item, result)
        reasons: list[str] = []
        if signals.identity_similarity < self.identity_minimum:
            reasons.append("IDENTITY_CHANGED")
        if signals.product_similarity < self.product_minimum:
            reasons.append("PRODUCT_CHANGED")
        if not signals.color_preserved:
            reasons.append("COLOR_CHANGED")
        if not signals.print_preserved:
            reasons.append("PRINT_CHANGED")
        if not signals.anatomy_valid:
            reasons.append("ANATOMY_INVALID")
        if not signals.safe_content:
            reasons.append("UNSAFE_OUTPUT")
        if signals.fabricated_detail:
            reasons.append("FABRICATED_DETAIL")
        return QualityDecision(not reasons, bool(reasons), tuple(reasons))


def route_should_disable(latest_hard_failures: tuple[bool, ...]) -> bool:
    window = latest_hard_failures[-20:]
    return len(window) >= 3 and sum(window) >= 3
