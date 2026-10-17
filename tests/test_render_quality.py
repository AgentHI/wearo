from apps.api.wearo_api.render_quality import (
    QualitySignals,
    RenderQualityGate,
    route_should_disable,
)


class Analyzer:
    def __init__(self, signals: QualitySignals) -> None:
        self.signals = signals

    def analyze(self, person: bytes, item: bytes, result: bytes) -> QualitySignals:
        return self.signals


def passing() -> QualitySignals:
    return QualitySignals(0.95, 0.94, True, True, True, True, False)


def test_passing_result_is_deliverable() -> None:
    decision = RenderQualityGate(Analyzer(passing())).evaluate(b"p", b"i", b"r")
    assert decision.accepted and not decision.hard_failure and decision.reasons == ()


def test_every_material_failure_blocks_delivery() -> None:
    cases = (
        (QualitySignals(0.2, 0.94, True, True, True, True, False), "IDENTITY_CHANGED"),
        (QualitySignals(0.95, 0.2, True, True, True, True, False), "PRODUCT_CHANGED"),
        (QualitySignals(0.95, 0.94, False, True, True, True, False), "COLOR_CHANGED"),
        (QualitySignals(0.95, 0.94, True, False, True, True, False), "PRINT_CHANGED"),
        (QualitySignals(0.95, 0.94, True, True, False, True, False), "ANATOMY_INVALID"),
        (QualitySignals(0.95, 0.94, True, True, True, False, False), "UNSAFE_OUTPUT"),
        (QualitySignals(0.95, 0.94, True, True, True, True, True), "FABRICATED_DETAIL"),
    )
    for signals, expected in cases:
        decision = RenderQualityGate(Analyzer(signals)).evaluate(b"p", b"i", b"r")
        assert not decision.accepted and decision.hard_failure and expected in decision.reasons


def test_three_confirmed_hard_failures_in_latest_twenty_disable_route() -> None:
    assert route_should_disable((False,) * 17 + (True, True, True))
    assert not route_should_disable((False,) * 18 + (True, True))
