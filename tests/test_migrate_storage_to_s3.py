from pathlib import Path

import pytest

from scripts.migrate_storage_to_s3 import _safe_relative, variant_target


def test_safe_relative_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        _safe_relative("../secret")


def test_variant_target_uses_dataset_variants_folder() -> None:
    assert (
        variant_target("datasets/id/original.jpg", {}, "MEDIUM")
        == "datasets/id/variants/medium.jpg"
    )


def test_variant_target_follows_existing_layout() -> None:
    assert variant_target("people/a.jpg", {"LOW": "people/a/low.jpg"}, "HIGH") == (
        "people/a/high.jpg"
    )


def test_script_is_inside_repository() -> None:
    assert Path("scripts/migrate_storage_to_s3.py").is_file()
