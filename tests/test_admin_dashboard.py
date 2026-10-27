from apps.api.wearo_api.admin_dashboard import OrganizationUsage, combine_organization_usage


def test_two_business_totals_match_combined_usage_for_same_date_range() -> None:
    first = OrganizationUsage(3, 2, 1, 40)
    second = OrganizationUsage(4, 4, 0, 80)

    assert combine_organization_usage((first, second)) == {
        "total_try_ons": 7,
        "successful_try_ons": 6,
        "failed_try_ons": 1,
        "total_tokens_consumed": 120,
        "average_try_ons_per_organization": 3.5,
    }
