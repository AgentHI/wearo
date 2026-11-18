from datetime import UTC, datetime

from apps.api.wearo_api.billing_history_pdf import billing_history_pdf


def test_billing_history_pdf_contains_every_row_across_multiple_pages() -> None:
    rows = [
        {
            "created_at": datetime(2026, 11, 18, 8, index, tzinfo=UTC),
            "package_name": f"Package {index + 1}",
            "amount_minor": 1000 + index,
            "currency": "INR",
            "tokens": 50,
            "state": "CONFIRMED",
            "receipt_number": f"WR-{index + 1:04d}",
        }
        for index in range(30)
    ]

    report = billing_history_pdf(rows, generated_at=datetime(2026, 11, 18, 10, tzinfo=UTC))

    assert report.startswith(b"%PDF-1.4")
    assert report.endswith(b"%%EOF\n")
    assert report.count(b"/Type /Page ") == 2
    assert b"Package 1" in report
    assert b"Package 30" in report


def test_empty_billing_history_still_produces_a_valid_pdf() -> None:
    report = billing_history_pdf([], generated_at=datetime(2026, 11, 18, 10, tzinfo=UTC))

    assert report.startswith(b"%PDF-1.4")
    assert b"No payment records are available." in report
