from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

from PIL import Image, ImageOps
from sqlalchemy import Engine, create_engine, text

from apps.cost_lab_api.adapters import BFLAdapter, BytePlusAdapter, OpenAICompatibleAdapter
from apps.cost_lab_api.app import CostLab, _provider_quality_parameters
from apps.cost_lab_api.config import Settings
from apps.cost_lab_api.pricing import calculate_cost, normalized_total_tokens


class CostLabWorker:
    def __init__(self, service: CostLab, worker_id: str | None = None) -> None:
        self.service = service
        self.engine: Engine = service.engine
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.max_retries = int(os.getenv("COST_LAB_MAX_RETRIES", "1"))

    @staticmethod
    def _adapter(provider: dict[str, Any]) -> type:
        provider_type = provider.get("provider_type")
        base_url = str(provider.get("api_base_url") or "").casefold()
        if provider_type == "BFL" or (provider_type == "SECRET_REFERENCE" and "bfl.ai" in base_url):
            return BFLAdapter
        adapters = {
            "OPENAI_COMPATIBLE": OpenAICompatibleAdapter,
            "BYTEPLUS": BytePlusAdapter,
        }
        if provider_type not in adapters:
            raise ValueError(f"No worker adapter for {provider_type}")
        return adapters[provider_type]

    def claim(self) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                text("""SELECT t.tryon_id FROM cost_lab.tryon_runs t
                JOIN cost_lab.benchmark_runs r USING(run_id)
                WHERE t.status='QUEUED' AND r.status IN ('QUEUED','RUNNING')
                ORDER BY t.created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            ).scalar_one_or_none()
            if row is None:
                return None
            connection.execute(
                text("""UPDATE cost_lab.tryon_runs SET status='PROCESSING',attempts=attempts+1,
                leased_by=:worker,lease_expires_at=now()+interval '3 minutes' WHERE tryon_id=:id"""),
                {"worker": self.worker_id, "id": row},
            )
            connection.execute(
                text("""UPDATE cost_lab.benchmark_runs SET status='RUNNING',started_at=coalesce(started_at,now())
                WHERE run_id=(SELECT run_id FROM cost_lab.tryon_runs WHERE tryon_id=:id)"""),
                {"id": row},
            )
            return dict(
                connection.execute(
                    text("""SELECT t.*,r.model_id,r.prompt,r.pricing_snapshot,r.quality_snapshot,r.spending_limit_usd,
                c.quality,c.output_quality,c.person_asset_id,c.product_asset_id,m.api_identifier,p.* FROM cost_lab.tryon_runs t
                JOIN cost_lab.benchmark_runs r USING(run_id) JOIN cost_lab.benchmark_combinations c USING(combination_id)
                JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id) WHERE t.tryon_id=:id"""),
                    {"id": row},
                )
                .mappings()
                .one()
            )

    def _asset(self, asset_id: UUID, quality: str) -> bytes:
        with self.engine.begin() as connection:
            asset = (
                connection.execute(
                    text(
                        "SELECT original_path,variants FROM cost_lab.benchmark_assets WHERE asset_id=:id"
                    ),
                    {"id": asset_id},
                )
                .mappings()
                .one()
            )
        relative = str(asset["variants"].get(quality) or asset["original_path"])
        content = self.service.storage.get(relative)
        if content is None:
            raise FileNotFoundError(relative)
        return content

    def process_one(self) -> bool:
        job = self.claim()
        if job is None:
            return False
        with self.engine.begin() as connection:
            cancelled: bool = (
                connection.execute(
                    text("SELECT status FROM cost_lab.benchmark_runs WHERE run_id=:id"),
                    {"id": job["run_id"]},
                ).scalar_one()
                == "CANCEL_REQUESTED"
            )
        if cancelled:
            self._finish(job, "CANCELLED", None)
            return True
        try:
            adapter_type = self._adapter(job)
            settings: dict[str, Any] = next(
                (item for item in job["quality_snapshot"] if item["code"] == job["output_quality"]),
                {},
            )
            parameters = dict(settings.get("settings") or {}) | dict(
                settings.get("request_parameters") or {}
            )
            if settings.get("provider_quality"):
                parameters["quality"] = settings["provider_quality"]
            parameters |= _provider_quality_parameters(
                job, job["api_identifier"], job["output_quality"]
            )
            adapter = adapter_type(
                job["api_base_url"],
                self.service.secret_for(job),
                int(os.getenv("COST_LAB_REQUEST_TIMEOUT_SECONDS", "120")),
            )
            result = adapter.generate(
                model=job["api_identifier"],
                prompt=job["prompt"],
                images=[
                    self._asset(job["person_asset_id"], job["quality"]),
                    self._asset(job["product_asset_id"], job["quality"]),
                ],
                parameters=parameters,
            )
            try:
                with Image.open(BytesIO(result.image_bytes)) as generated:
                    extension = ".png" if generated.format == "PNG" else ".jpg"
            except Exception:
                extension = ".bin"
            path = f"benchmarks/{job['run_id']}/{job['tryon_id']}{extension}"
            self.service.storage.put(
                path,
                result.image_bytes,
                "image/png" if extension == ".png" else "image/jpeg",
            )
            usage = dict(result.usage)
            usage.setdefault("requests", 1)
            usage.setdefault("output_images", 1)
            usage["output_quality"] = job["output_quality"]
            cost = calculate_cost(usage, list(job["pricing_snapshot"]))
            self._finish(
                job,
                "SUCCEEDED",
                {
                    "path": path,
                    "result": result,
                    "usage": usage,
                    "cost": cost,
                },
            )
        except Exception as error:
            retry = job["attempts"] <= self.max_retries
            self._finish(job, "QUEUED" if retry else "FAILED", {"error": str(error)[:2000]})
        return True

    def process_dataset_one(self) -> bool:
        with self.engine.begin() as connection:
            item_id = connection.execute(
                text("""SELECT i.item_id FROM cost_lab.dataset_generation_items i
                JOIN cost_lab.dataset_generation_jobs j USING(job_id)
                WHERE i.status='QUEUED' AND j.status IN ('QUEUED','RUNNING')
                ORDER BY i.created_at,i.ordinal FOR UPDATE SKIP LOCKED LIMIT 1""")
            ).scalar_one_or_none()
            if item_id is None:
                return False
            connection.execute(
                text("""UPDATE cost_lab.dataset_generation_items SET status='PROCESSING',
                attempts=attempts+1 WHERE item_id=:id"""),
                {"id": item_id},
            )
            connection.execute(
                text("""UPDATE cost_lab.dataset_generation_jobs SET status='RUNNING',
                started_at=coalesce(started_at,now()) WHERE job_id=(SELECT job_id FROM
                cost_lab.dataset_generation_items WHERE item_id=:id)"""),
                {"id": item_id},
            )
            item = dict(
                connection.execute(
                    text("""SELECT i.*,j.generation_quality,j.complexity,m.api_identifier,p.*,
                    q.settings quality_settings,mapping.provider_quality,mapping.request_parameters,
                    coalesce((SELECT components FROM cost_lab.model_pricing x WHERE x.model_id=j.model_id
                    AND x.effective_at <= now() ORDER BY x.effective_at DESC LIMIT 1),'[]'::jsonb) pricing
                    FROM cost_lab.dataset_generation_items i JOIN cost_lab.dataset_generation_jobs j USING(job_id)
                    JOIN cost_lab.ai_models m USING(model_id) JOIN cost_lab.model_providers p USING(provider_id)
                    JOIN cost_lab.quality_profiles q ON q.code=j.generation_quality
                    LEFT JOIN cost_lab.model_quality_mapping mapping
                      ON mapping.model_id=j.model_id AND mapping.profile_id=q.profile_id
                    WHERE i.item_id=:id"""),
                    {"id": item_id},
                )
                .mappings()
                .one()
            )
        try:
            adapter = self._adapter(item)(
                item["api_base_url"],
                self.service.secret_for(item),
                int(os.getenv("COST_LAB_REQUEST_TIMEOUT_SECONDS", "120")),
            )
            parameters = dict(item.get("quality_settings") or {}) | dict(
                item.get("request_parameters") or {}
            )
            if item.get("provider_quality"):
                parameters["quality"] = item["provider_quality"]
            parameters |= _provider_quality_parameters(
                item, item["api_identifier"], item["generation_quality"]
            )
            result = adapter.generate_from_prompt(
                model=item["api_identifier"], prompt=item["prompt"], parameters=parameters
            )
            source = ImageOps.exif_transpose(Image.open(BytesIO(result.image_bytes))).convert("RGB")
            asset_id = uuid4()
            folder = f"datasets/{asset_id}"
            original = f"{folder}/original.jpg"
            original_buffer = BytesIO()
            source.save(original_buffer, "JPEG", quality=96)
            self.service.storage.put(original, original_buffer.getvalue(), "image/jpeg")
            variants: dict[str, str] = {}
            with self.engine.begin() as connection:
                profiles = (
                    connection.execute(
                        text("""SELECT code,width,height,compression_quality
                    FROM cost_lab.quality_profiles""")
                    )
                    .mappings()
                    .all()
                )
            for profile in profiles:
                target = f"{folder}/variants/{str(profile['code']).lower()}.jpg"
                image = source.copy()
                image.thumbnail((profile["width"], profile["height"]), Image.Resampling.LANCZOS)
                target_buffer = BytesIO()
                image.save(
                    target_buffer,
                    "JPEG",
                    quality=profile["compression_quality"],
                    optimize=True,
                )
                self.service.storage.put(target, target_buffer.getvalue(), "image/jpeg")
                variants[str(profile["code"])] = target
            usage = dict(result.usage)
            usage.setdefault("output_images", 1)
            usage["output_quality"] = item["generation_quality"]
            cost = calculate_cost(usage, list(item["pricing"]))
            digest = hashlib.sha256(result.image_bytes).hexdigest()
            with self.engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO cost_lab.benchmark_assets
                    (asset_id,kind,name,original_path,variants,content_hash,authorized,complexity)
                    VALUES(:id,:kind,:name,:path,CAST(:variants AS jsonb),:hash,true,:complexity)"""),
                    {
                        "id": asset_id,
                        "kind": item["kind"],
                        "name": f"AI generated {str(item['kind']).title()} {item['ordinal'] + 1}",
                        "path": original,
                        "variants": json.dumps(variants),
                        "hash": digest,
                        "complexity": item["complexity"],
                    },
                )
                connection.execute(
                    text("""UPDATE cost_lab.dataset_generation_items SET
                    status='SUCCEEDED',provider_request_id=:request,asset_id=:asset,
                    usage=CAST(:usage AS jsonb),cost_usd=:cost,finished_at=now() WHERE item_id=:id"""),
                    {
                        "request": result.request_id,
                        "asset": asset_id,
                        "usage": json.dumps(usage),
                        "cost": cost,
                        "id": item_id,
                    },
                )
                self._update_dataset_job(connection, item["job_id"])
        except Exception as error:
            with self.engine.begin() as connection:
                connection.execute(
                    text("""UPDATE cost_lab.dataset_generation_items SET status='FAILED',
                    error_detail=:error,finished_at=now() WHERE item_id=:id"""),
                    {"error": str(error)[:2000], "id": item_id},
                )
                self._update_dataset_job(connection, item["job_id"])
        return True

    @staticmethod
    def _update_dataset_job(connection: Any, job_id: UUID) -> None:
        connection.execute(
            text("""UPDATE cost_lab.dataset_generation_jobs j SET
            completed_items=(SELECT count(*) FROM cost_lab.dataset_generation_items i
                WHERE i.job_id=j.job_id AND i.status='SUCCEEDED'),
            failed_items=(SELECT count(*) FROM cost_lab.dataset_generation_items i
                WHERE i.job_id=j.job_id AND i.status='FAILED'),
            cancelled_items=(SELECT count(*) FROM cost_lab.dataset_generation_items i
                WHERE i.job_id=j.job_id AND i.status='CANCELLED'),
            total_cost_usd=(SELECT coalesce(sum(cost_usd),0) FROM cost_lab.dataset_generation_items i
                WHERE i.job_id=j.job_id)
            WHERE job_id=:job"""),
            {"job": job_id},
        )
        connection.execute(
            text("""UPDATE cost_lab.dataset_generation_jobs j SET
            status=CASE WHEN status='CANCEL_REQUESTED' THEN 'CANCELLED'
                WHEN failed_items > 0 THEN 'FAILED' ELSE 'COMPLETED' END,finished_at=now()
            WHERE job_id=:job AND NOT EXISTS(SELECT 1 FROM cost_lab.dataset_generation_items i
                WHERE i.job_id=j.job_id AND i.status IN ('QUEUED','PROCESSING'))"""),
            {"job": job_id},
        )

    def _finish(self, job: dict[str, Any], status: str, outcome: dict[str, Any] | None) -> None:
        with self.engine.begin() as connection:
            still_exists = connection.execute(
                text("SELECT 1 FROM cost_lab.tryon_runs WHERE tryon_id=:id"),
                {"id": job["tryon_id"]},
            ).scalar_one_or_none()
            if still_exists is None:
                if outcome and outcome.get("path"):
                    self.service.storage.delete(outcome["path"])
                return
            if status == "SUCCEEDED" and outcome:
                result = outcome["result"]
                usage = outcome["usage"]
                connection.execute(
                    text("""UPDATE cost_lab.tryon_runs SET status='SUCCEEDED',provider_request_id=:request,latency_ms=:latency,
                    output_path=:path,billable=true,finished_at=now(),leased_by=NULL,lease_expires_at=NULL WHERE tryon_id=:id"""),
                    {
                        "request": result.request_id,
                        "latency": result.latency_ms,
                        "path": outcome["path"],
                        "id": job["tryon_id"],
                    },
                )
                connection.execute(
                    text("""INSERT INTO cost_lab.tryon_usage(usage_id,tryon_id,text_input_tokens,image_input_tokens,cached_input_tokens,
                    image_output_tokens,total_reported_tokens,other_units,calculated_cost_usd,provider_cost_usd,usage_source,raw_metadata)
                    VALUES(:usage_id,:tryon,:text,:image,:cached,:output,:total,CAST(:other AS jsonb),:cost,:provider_cost,:source,CAST(:raw AS jsonb))"""),
                    {
                        "usage_id": uuid4(),
                        "tryon": job["tryon_id"],
                        "text": usage.get("text_input_tokens"),
                        "image": usage.get("image_input_tokens"),
                        "cached": usage.get("cached_input_tokens"),
                        "output": usage.get("image_output_tokens"),
                        "total": normalized_total_tokens(usage),
                        "other": json.dumps(
                            {
                                k: v
                                for k, v in usage.items()
                                if k
                                not in {
                                    "text_input_tokens",
                                    "image_input_tokens",
                                    "cached_input_tokens",
                                    "image_output_tokens",
                                    "total_reported_tokens",
                                }
                            }
                        ),
                        "cost": outcome["cost"],
                        "provider_cost": usage.get("cost_usd"),
                        "source": "PROVIDER_REPORTED" if result.usage else "WEARO_ESTIMATED",
                        "raw": json.dumps(result.raw_metadata),
                    },
                )
            else:
                connection.execute(
                    text("""UPDATE cost_lab.tryon_runs SET status=:status,error_code=:code,error_detail=:detail,
                    finished_at=CASE WHEN :status='QUEUED' THEN NULL ELSE now() END,leased_by=NULL,lease_expires_at=NULL WHERE tryon_id=:id"""),
                    {
                        "status": status,
                        "code": "PROVIDER_ERROR" if outcome else None,
                        "detail": outcome.get("error") if outcome else None,
                        "id": job["tryon_id"],
                    },
                )
            connection.execute(
                text("""UPDATE cost_lab.benchmark_runs r SET completed_jobs=(SELECT count(*) FROM cost_lab.tryon_runs t
                WHERE t.run_id=r.run_id AND t.status IN ('SUCCEEDED','FAILED','CANCELLED')) WHERE run_id=:run"""),
                {"run": job["run_id"]},
            )
            connection.execute(
                text("""UPDATE cost_lab.benchmark_runs r SET status=CASE WHEN status='CANCEL_REQUESTED' THEN 'CANCELLED'
                WHEN EXISTS(SELECT 1 FROM cost_lab.tryon_runs t WHERE t.run_id=r.run_id AND t.status='FAILED') THEN 'FAILED' ELSE 'COMPLETED' END,
                finished_at=now() WHERE run_id=:run AND NOT EXISTS(SELECT 1 FROM cost_lab.tryon_runs t WHERE t.run_id=r.run_id AND t.status IN ('QUEUED','PROCESSING'))"""),
                {"run": job["run_id"]},
            )


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    worker = CostLabWorker(
        CostLab(settings, create_engine(settings.database_url, pool_pre_ping=True))
    )
    while True:
        worked = worker.process_dataset_one() or worker.process_one()
        if args.once:
            return
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    run()
