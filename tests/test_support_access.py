from apps.api.wearo_api.support_access import required_admin_scope


def test_support_scope_maps_to_one_explicit_admin_permission() -> None:
    assert required_admin_scope("CASE_METADATA") == "support:case_metadata"
    assert required_admin_scope("BILLING") == "support:billing"
    assert required_admin_scope("RENDER_METADATA") == "support:render_metadata"
    assert required_admin_scope("PRIVATE_MEDIA") == "support:private_media"
