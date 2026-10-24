import pytest

from apps.api.wearo_api.business_onboarding import (
    BusinessOnboardingError,
    InvoiceDetails,
    normalized_slug,
    validate_invoice_details,
)


def test_business_name_produces_stable_url_slug() -> None:
    assert normalized_slug("  Madhu's Boutique  ") == "madhu-s-boutique"


@pytest.mark.parametrize("name", ["", "!!", "ab"])
def test_invalid_business_name_is_rejected(name: str) -> None:
    with pytest.raises(BusinessOnboardingError) as error:
        normalized_slug(name)
    assert error.value.code == "INVALID_BUSINESS_NAME"


def test_non_invoice_onboarding_does_not_collect_unnecessary_details() -> None:
    assert validate_invoice_details("IN", InvoiceDetails()) == InvoiceDetails()


def test_indian_tax_invoice_requires_gstin_and_address() -> None:
    details = InvoiceDetails(
        requested=True,
        legal_name="Wearo Retail Private Limited",
        tax_identifier="29abcde1234f1z5",
        billing_address={"line1": "1 Market Road", "city": "Bengaluru", "postal_code": "560001"},
    )
    validated = validate_invoice_details("IN", details)
    assert validated.tax_identifier == "29ABCDE1234F1Z5"


def test_invoice_request_without_required_details_is_rejected() -> None:
    with pytest.raises(BusinessOnboardingError) as error:
        validate_invoice_details("IN", InvoiceDetails(requested=True))
    assert error.value.code == "INVOICE_DETAILS_REQUIRED"
