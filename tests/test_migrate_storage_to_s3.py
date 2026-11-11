from pathlib import Path

import pytest

from scripts.migrate_storage_to_s3 import _safe_relative, load_config, variant_target


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


def test_env_file_profile_and_buckets_are_loaded(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "WEARO_DATABASE_URL=postgresql://user:pass@localhost/wearo\n"
        "WEARO_PRIVATE_STORAGE_BUCKET=wearo-prod-private\n"
        "COST_LAB_STORAGE_BUCKET=wearo-prod-cost\n"
        "AWS_REGION=ap-south-1\n"
        "AWS_PROFILE=wearo-prod\n",
        encoding="utf-8",
    )

    config = load_config(env_file)

    assert config.private_bucket == "wearo-prod-private"
    assert config.cost_bucket == "wearo-prod-cost"
    assert config.region == "ap-south-1"
    assert config.aws_profile == "wearo-prod"
