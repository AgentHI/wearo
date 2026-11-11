#!/usr/bin/env python3
"""One-time, non-destructive migration of Wearo local media to S3.

Dry-run is the default. Use --apply with --expected-account to upload. Database
references remain relative keys; only missing Cost Lab variant mappings are
updated when --repair-missing-variants is explicitly supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from dotenv import dotenv_values
from PIL import Image, ImageOps
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.wearo_api.database import normalize_database_url  # noqa: E402

COST_PREFIX = "cost-lab/"
QUALITY_CODES = ("LOW", "MEDIUM", "HIGH")


@dataclass(frozen=True)
class Config:
    database_url: str
    private_root: Path
    private_bucket: str
    cost_root: Path
    cost_bucket: str
    region: str | None
    aws_profile: str | None


@dataclass
class Report:
    mode: str
    started_at: str
    aws_account: str = ""
    aws_arn: str = ""
    private_bucket: str = ""
    cost_bucket: str = ""
    local_private_files: int = 0
    local_cost_files: int = 0
    planned_uploads: int = 0
    uploaded: int = 0
    unchanged: int = 0
    repaired_variants: int = 0
    database_references: int = 0
    missing_local_references: list[str] = field(default_factory=list)
    missing_s3_references: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    finished_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe storage key: {value!r}")
    return str(path)


def load_config(env_file: Path | None) -> Config:
    values: dict[str, str] = dict(os.environ)
    if env_file:
        if not env_file.is_file():
            raise ValueError(f"Environment file does not exist: {env_file}")
        values.update({key: value for key, value in dotenv_values(env_file).items() if value})
    required = (
        "WEARO_DATABASE_URL",
        "WEARO_PRIVATE_STORAGE_BUCKET",
        "COST_LAB_STORAGE_BUCKET",
    )
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ValueError(f"Missing configuration: {', '.join(missing)}")
    private_bucket = values["WEARO_PRIVATE_STORAGE_BUCKET"]
    cost_bucket = values["COST_LAB_STORAGE_BUCKET"]
    if private_bucket == cost_bucket:
        raise ValueError("Private media and Cost Lab must use separate S3 buckets")
    return Config(
        database_url=normalize_database_url(values["WEARO_DATABASE_URL"]).render_as_string(
            hide_password=False
        ),
        private_root=Path(values.get("WEARO_PRIVATE_STORAGE_ROOT", ".wearo-storage")).resolve(),
        private_bucket=private_bucket,
        cost_root=Path(values.get("COST_LAB_STORAGE_ROOT", ".wearo-storage/cost-lab")).resolve(),
        cost_bucket=cost_bucket,
        region=values.get("AWS_REGION") or values.get("AWS_DEFAULT_REGION"),
        aws_profile=values.get("AWS_PROFILE"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _head(s3: Any, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return dict(s3.head_object(Bucket=bucket, Key=key))
    except s3.exceptions.ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def upload_file(
    s3: Any, bucket: str, key: str, path: Path, apply: bool, report: Report
) -> None:
    digest = sha256_file(path)
    remote = _head(s3, bucket, key)
    if remote and remote.get("ContentLength") == path.stat().st_size:
        if remote.get("Metadata", {}).get("sha256") == digest:
            report.unchanged += 1
            return
    report.planned_uploads += 1
    if not apply:
        return
    s3.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={
            "ContentType": _content_type(path),
            "ServerSideEncryption": "AES256",
            "Metadata": {"sha256": digest},
        },
    )
    verified = _head(s3, bucket, key)
    if not verified or verified.get("ContentLength") != path.stat().st_size:
        raise OSError(f"S3 verification failed for s3://{bucket}/{key}")
    report.uploaded += 1


def database_references(connection: Any) -> tuple[set[str], set[str]]:
    private = {
        row[0]
        for row in connection.execute(
            text(
                "SELECT object_key FROM media_assets "
                "WHERE object_key IS NOT NULL AND deletion_state <> 'DELETED'"
            )
        )
    }
    cost: set[str] = set()
    for row in connection.execute(
        text("SELECT original_path, variants FROM cost_lab.benchmark_assets")
    ).mappings():
        cost.add(row["original_path"])
        cost.update((row["variants"] or {}).values())
    for query in (
        "SELECT output_path FROM cost_lab.tryon_runs WHERE output_path IS NOT NULL",
        "SELECT test_output_path FROM cost_lab.ai_models WHERE test_output_path IS NOT NULL",
        "SELECT file_path FROM cost_lab.knowledge_items WHERE file_path IS NOT NULL",
    ):
        cost.update(row[0] for row in connection.execute(text(query)))
    for row in connection.execute(text("SELECT test_input_paths FROM cost_lab.ai_models")):
        cost.update(row[0] or [])
    return private, cost


def variant_target(original: str, variants: dict[str, str], quality: str) -> str:
    if variants:
        parent = PurePosixPath(next(iter(variants.values()))).parent
    else:
        original_path = PurePosixPath(_safe_relative(original))
        parent = original_path.parent / "variants"
    return str(parent / f"{quality.lower()}.jpg")


def repair_variants(connection: Any, config: Config, s3: Any, report: Report) -> None:
    profiles = {
        row["code"]: row
        for row in connection.execute(
            text("SELECT code,width,height,compression_quality FROM cost_lab.quality_profiles")
        ).mappings()
    }
    assets = connection.execute(
        text(
            "SELECT asset_id,original_path,variants FROM cost_lab.benchmark_assets "
            "WHERE replaced_at IS NULL"
        )
    ).mappings()
    for asset in assets:
        variants = dict(asset["variants"] or {})
        missing = [code for code in QUALITY_CODES if not variants.get(code)]
        if not missing:
            continue
        original = config.cost_root / _safe_relative(asset["original_path"])
        if not original.is_file():
            report.errors.append(f"Cannot repair {asset['asset_id']}: missing {original}")
            continue
        with Image.open(original) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
        for code in missing:
            profile = profiles.get(code)
            if not profile:
                report.errors.append(f"Missing quality profile {code}")
                continue
            target_key = variant_target(asset["original_path"], variants, code)
            target = config.cost_root / _safe_relative(target_key)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            image = source.copy()
            image.thumbnail((profile["width"], profile["height"]), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, "JPEG", quality=profile["compression_quality"], optimize=True)
            target.write_bytes(buffer.getvalue())
            target.chmod(0o600)
            upload_file(s3, config.cost_bucket, COST_PREFIX + target_key, target, True, report)
            variants[code] = target_key
            report.repaired_variants += 1
        connection.execute(
            text(
                "UPDATE cost_lab.benchmark_assets SET variants=CAST(:variants AS jsonb) "
                "WHERE asset_id=:asset_id"
            ),
            {"variants": json.dumps(variants), "asset_id": asset["asset_id"]},
        )


def run(args: argparse.Namespace) -> tuple[Report, Path]:
    import boto3

    config = load_config(args.env_file)
    report = Report(
        mode="apply" if args.apply else "dry-run",
        started_at=_now(),
        private_bucket=config.private_bucket,
        cost_bucket=config.cost_bucket,
    )
    session = boto3.Session(profile_name=config.aws_profile, region_name=config.region)
    identity = session.client("sts").get_caller_identity()
    report.aws_account = identity["Account"]
    report.aws_arn = identity["Arn"]
    if args.apply and not args.expected_account:
        raise ValueError("--expected-account is required with --apply")
    if args.expected_account and identity["Account"] != args.expected_account:
        raise ValueError(
            f"AWS account mismatch: expected {args.expected_account}, got {identity['Account']}"
        )
    s3 = session.client("s3")
    for bucket in (config.private_bucket, config.cost_bucket):
        s3.head_bucket(Bucket=bucket)

    private_files = iter_files(config.private_root / "private")
    cost_files = iter_files(config.cost_root)
    report.local_private_files = len(private_files)
    report.local_cost_files = len(cost_files)
    for path in private_files:
        key = path.relative_to(config.private_root).as_posix()
        upload_file(s3, config.private_bucket, key, path, args.apply, report)
    for path in cost_files:
        key = COST_PREFIX + path.relative_to(config.cost_root).as_posix()
        upload_file(s3, config.cost_bucket, key, path, args.apply, report)

    engine = create_engine(config.database_url, pool_pre_ping=True)
    transaction = engine.begin() if args.apply else engine.connect()
    with transaction as connection:
        if args.repair_missing_variants:
            if not args.apply:
                raise ValueError("--repair-missing-variants requires --apply")
            repair_variants(connection, config, s3, report)
        private_refs, cost_refs = database_references(connection)
        report.database_references = len(private_refs) + len(cost_refs)
        for key in sorted(private_refs):
            safe = _safe_relative(key)
            if not (config.private_root / safe).is_file():
                report.missing_local_references.append(f"private:{safe}")
            if _head(s3, config.private_bucket, safe) is None:
                report.missing_s3_references.append(f"private:{safe}")
        for key in sorted(cost_refs):
            safe = _safe_relative(key)
            if not (config.cost_root / safe).is_file():
                report.missing_local_references.append(f"cost-lab:{safe}")
            if _head(s3, config.cost_bucket, COST_PREFIX + safe) is None:
                report.missing_s3_references.append(f"cost-lab:{safe}")
    engine.dispose()
    report.finished_at = _now()
    manifest_dir = args.manifest_dir or config.private_root / "migration-manifests"
    manifest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    manifest = manifest_dir / f"s3-migration-{stamp}.json"
    manifest.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    manifest.chmod(0o600)
    return report, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Environment file (for example .env.prod)")
    parser.add_argument(
        "--apply", action="store_true", help="Perform uploads and approved DB repair"
    )
    parser.add_argument("--expected-account", help="Required AWS account ID guard for --apply")
    parser.add_argument(
        "--repair-missing-variants",
        action="store_true",
        help="Generate/upload missing LOW/MEDIUM/HIGH variants and update their DB mappings",
    )
    parser.add_argument("--manifest-dir", type=Path, help="Override audit manifest directory")
    return parser.parse_args()


def main() -> int:
    try:
        report, manifest = run(parse_args())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(report), indent=2))
    print(f"Manifest: {manifest}")
    if report.errors or (report.mode == "apply" and report.missing_s3_references):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
