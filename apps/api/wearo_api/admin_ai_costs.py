from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text


class AdminAiCostError(ValueError):
    pass


def _integer(value: object) -> int:
    return int(str(value))


class PostgresAdminAiCosts:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def dashboard(self) -> dict[str, object]:
        with self.engine.connect() as connection:
            providers = [
                dict(row)
                for row in connection.execute(
                    text("""SELECT p.*,
                COALESCE(x.purchased_minor,0) purchased_minor,
                COALESCE(u.used_usd_micros,0) used_usd_micros
              FROM ai_providers p
              LEFT JOIN (SELECT provider_id,
                                sum(amount_minor) FILTER (WHERE currency='USD') purchased_minor
                         FROM provider_purchases GROUP BY provider_id) x USING (provider_id)
              LEFT JOIN (SELECT m.provider_id, sum(u.cost_usd_micros) used_usd_micros
                         FROM model_usage_costs u JOIN ai_models m USING (model_id)
                         GROUP BY m.provider_id) u USING (provider_id)
              ORDER BY p.display_name""")
                ).mappings()
            ]
            models = [
                dict(row)
                for row in connection.execute(
                    text("""SELECT m.*, p.code provider_code,
                count(j.job_id) try_ons,
                count(j.job_id) FILTER (WHERE j.status='DELIVERED') successful_try_ons,
                COALESCE(sum(u.cost_usd_micros),0) total_cost_usd_micros,
                COALESCE(round(avg(u.cost_usd_micros)),0) average_cost_usd_micros,
                COALESCE(round(avg(extract(epoch FROM (j.updated_at-j.created_at))*1000)
                  FILTER (WHERE j.status IN ('DELIVERED','FAILED'))),0) average_generation_time_ms
              FROM ai_models m JOIN ai_providers p USING (provider_id)
              LEFT JOIN render_quotes q ON q.provider=p.code
                AND q.model_version=m.api_model_id AND q.provider_region=m.region
              LEFT JOIN render_jobs j USING (quote_id)
              LEFT JOIN model_usage_costs u ON u.job_id=j.job_id AND u.model_id=m.model_id
              GROUP BY m.model_id, p.code ORDER BY average_cost_usd_micros, m.display_name""")
                ).mappings()
            ]
            purchases = [
                dict(row)
                for row in connection.execute(
                    text("""SELECT x.*, p.display_name provider_name
              FROM provider_purchases x JOIN ai_providers p USING (provider_id)
              ORDER BY purchased_at DESC LIMIT 100""")
                ).mappings()
            ]
        for provider in providers:
            env_name = str(provider.pop("credential_env_name"))
            provider["credential_env_name"] = env_name
            provider["credential_configured"] = bool(os.environ.get(env_name))
        return {"providers": providers, "models": models, "purchases": purchases}

    def add_provider(self, values: dict[str, object]) -> dict[str, object]:
        code = str(values["code"]).strip().upper()
        env_name = str(values["credential_env_name"]).strip().upper()
        if not code or not env_name.startswith("WEARO_") or not env_name.replace("_", "").isalnum():
            raise AdminAiCostError(
                "A valid provider code and WEARO_ credential reference are required."
            )
        provider_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO ai_providers
              (provider_id,code,display_name,adapter_type,credential_env_name)
              VALUES (:id,:code,:name,:adapter,:env)"""),
                {
                    "id": provider_id,
                    "code": code,
                    "name": str(values["display_name"]).strip(),
                    "adapter": str(values["adapter_type"]).strip().upper(),
                    "env": env_name,
                },
            )
        return {"provider_id": provider_id, "status": "ACTIVE"}

    def update_provider(self, provider_id: UUID, values: dict[str, object]) -> dict[str, object]:
        code = str(values["code"]).strip().upper()
        env_name = str(values["credential_env_name"]).strip().upper()
        if not code or not env_name.startswith("WEARO_") or not env_name.replace("_", "").isalnum():
            raise AdminAiCostError(
                "A valid provider code and WEARO_ credential reference are required."
            )
        with self.engine.begin() as connection:
            existing_code = connection.execute(
                text("SELECT code FROM ai_providers WHERE provider_id=:id"), {"id": provider_id}
            ).scalar_one_or_none()
            if existing_code is None:
                raise AdminAiCostError("Provider not found.")
            if existing_code != code:
                raise AdminAiCostError("Provider code cannot change after creation.")
            changed = connection.execute(
                text("""UPDATE ai_providers SET display_name=:name,
                  adapter_type=:adapter, credential_env_name=:env, updated_at=now()
                  WHERE provider_id=:id"""),
                {
                    "id": provider_id,
                    "name": str(values["display_name"]).strip(),
                    "adapter": str(values["adapter_type"]).strip().upper(),
                    "env": env_name,
                },
            )
        if not changed.rowcount:
            raise AdminAiCostError("Provider not found.")
        return {"provider_id": provider_id}

    def add_model(self, values: dict[str, object]) -> dict[str, object]:
        model_id = uuid4()
        prices = (
            "input_unit_price_usd_micros",
            "output_unit_price_usd_micros",
            "request_price_usd_micros",
            "fallback_cost_usd_micros",
        )
        if any(_integer(values.get(key, 0)) < 0 for key in prices):
            raise AdminAiCostError("Model prices must not be negative.")
        with self.engine.begin() as connection:
            canonical = (
                connection.execute(
                    text("""INSERT INTO ai_models
              (model_id,provider_id,api_model_id,display_name,capability,region,billing_method,
               input_unit_price_usd_micros,output_unit_price_usd_micros,
               request_price_usd_micros,fallback_cost_usd_micros)
              VALUES (:id,:provider,:api_model,:name,:capability,:region,:billing,
                      :input_price,:output_price,:request_price,:fallback)
              ON CONFLICT (provider_id,api_model_id,region) DO UPDATE SET
                display_name=EXCLUDED.display_name,
                capability=EXCLUDED.capability,
                billing_method=EXCLUDED.billing_method,
                input_unit_price_usd_micros=EXCLUDED.input_unit_price_usd_micros,
                output_unit_price_usd_micros=EXCLUDED.output_unit_price_usd_micros,
                request_price_usd_micros=EXCLUDED.request_price_usd_micros,
                fallback_cost_usd_micros=EXCLUDED.fallback_cost_usd_micros,
                updated_at=now()
              RETURNING model_id,status"""),
                    {
                        "id": model_id,
                        "provider": values["provider_id"],
                        "api_model": str(values["api_model_id"]).strip(),
                        "name": str(values["display_name"]).strip(),
                        "capability": str(values.get("capability", "TRY_ON")).strip().upper(),
                        "region": str(values.get("region", "global")).strip(),
                        "billing": str(values["billing_method"]).strip().upper(),
                        "input_price": _integer(values.get(prices[0], 0)),
                        "output_price": _integer(values.get(prices[1], 0)),
                        "request_price": _integer(values.get(prices[2], 0)),
                        "fallback": _integer(values.get(prices[3], 0)),
                    },
                )
                .mappings()
                .one()
            )
            self._backfill(connection, canonical["model_id"])
        return {"model_id": canonical["model_id"], "status": canonical["status"]}

    def update_model(self, model_id: UUID, values: dict[str, object]) -> dict[str, object]:
        prices = (
            "input_unit_price_usd_micros",
            "output_unit_price_usd_micros",
            "request_price_usd_micros",
            "fallback_cost_usd_micros",
        )
        with self.engine.begin() as connection:
            changed = connection.execute(
                text("""UPDATE ai_models SET provider_id=:provider, api_model_id=:api_model,
                  display_name=:name, capability=:capability, region=:region,
                  billing_method=:billing, input_unit_price_usd_micros=:input_price,
                  output_unit_price_usd_micros=:output_price,
                  request_price_usd_micros=:request_price,
                  fallback_cost_usd_micros=:fallback, updated_at=now()
                  WHERE model_id=:id"""),
                {
                    "id": model_id,
                    "provider": values["provider_id"],
                    "api_model": str(values["api_model_id"]).strip(),
                    "name": str(values["display_name"]).strip(),
                    "capability": str(values.get("capability", "TRY_ON")).strip().upper(),
                    "region": str(values.get("region", "global")).strip(),
                    "billing": str(values["billing_method"]).strip().upper(),
                    "input_price": _integer(values.get(prices[0], 0)),
                    "output_price": _integer(values.get(prices[1], 0)),
                    "request_price": _integer(values.get(prices[2], 0)),
                    "fallback": _integer(values.get(prices[3], 0)),
                },
            )
            if changed.rowcount:
                self._backfill(connection, model_id)
        if not changed.rowcount:
            raise AdminAiCostError("Model not found.")
        return {"model_id": model_id}

    def add_purchase(self, values: dict[str, object]) -> dict[str, object]:
        purchase_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO provider_purchases
              (purchase_id,provider_id,amount_minor,currency,units_purchased,unit_type,
               reference,purchased_at)
              VALUES (:id,:provider,:amount,:currency,:units,:unit_type,:reference,
                      :purchased_at)"""),
                {
                    "id": purchase_id,
                    "provider": values["provider_id"],
                    "amount": _integer(values["amount_minor"]),
                    "currency": str(values.get("currency", "USD")).upper(),
                    "units": values.get("units_purchased"),
                    "unit_type": str(values["unit_type"]).upper(),
                    "reference": values.get("reference"),
                    "purchased_at": values.get("purchased_at") or datetime.now(UTC),
                },
            )
        return {"purchase_id": purchase_id}

    def set_status(self, entity: str, entity_id: UUID, status: str) -> dict[str, object]:
        statement, column = (
            (
                "UPDATE ai_providers SET status=:status, updated_at=now() WHERE provider_id=:id",
                "provider_id",
            )
            if entity == "providers"
            else (
                "UPDATE ai_models SET status=:status, updated_at=now() WHERE model_id=:id",
                "model_id",
            )
        )
        normalized = status.upper()
        if normalized not in {"ACTIVE", "DISABLED", "ARCHIVED"}:
            raise AdminAiCostError("Unsupported lifecycle status.")
        with self.engine.begin() as connection:
            changed = connection.execute(
                text(statement),
                {"status": normalized, "id": entity_id},
            )
        if not changed.rowcount:
            raise AdminAiCostError("Provider or model not found.")
        return {column: entity_id, "status": normalized}

    def delete_model(self, model_id: UUID) -> None:
        with self.engine.begin() as connection:
            used: bool = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM model_usage_costs WHERE model_id=:id)"),
                {"id": model_id},
            ).scalar_one()
            if used:
                raise AdminAiCostError("Used models must be archived, not deleted.")
            connection.execute(text("DELETE FROM ai_models WHERE model_id=:id"), {"id": model_id})

    def delete_provider(self, provider_id: UUID) -> None:
        with self.engine.begin() as connection:
            used: bool = connection.execute(
                text("""SELECT EXISTS (
                  SELECT 1 FROM ai_models WHERE provider_id=:id
                  UNION ALL SELECT 1 FROM provider_purchases WHERE provider_id=:id
                )"""),
                {"id": provider_id},
            ).scalar_one()
            if used:
                raise AdminAiCostError(
                    "Providers with models or purchases must be archived, not deleted."
                )
            connection.execute(
                text("DELETE FROM ai_providers WHERE provider_id=:id"), {"id": provider_id}
            )

    @staticmethod
    def _backfill(connection: Connection, model_id: UUID) -> None:
        connection.execute(
            text("""INSERT INTO model_usage_costs
          (usage_cost_id,job_id,model_id,input_units,output_units,cost_usd_micros,cost_basis)
          SELECT gen_random_uuid(), j.job_id, m.model_id,
            COALESCE((r.provider_usage->>'input_tokens')::bigint,0),
            COALESCE((r.provider_usage->>'output_tokens')::bigint,0),
            CASE WHEN m.billing_method='TOKEN' AND r.provider_usage IS NOT NULL THEN
              COALESCE((r.provider_usage->>'input_tokens')::bigint,0)
                * m.input_unit_price_usd_micros +
              COALESCE((r.provider_usage->>'output_tokens')::bigint,0)
                * m.output_unit_price_usd_micros
            WHEN m.billing_method IN ('REQUEST','IMAGE','CREDIT') THEN m.request_price_usd_micros
            ELSE m.fallback_cost_usd_micros END,
            CASE WHEN r.provider_usage IS NOT NULL THEN 'CALCULATED' ELSE 'ESTIMATED' END
          FROM ai_models m JOIN ai_providers p USING (provider_id)
          JOIN render_quotes q ON q.provider=p.code AND q.model_version=m.api_model_id
            AND q.provider_region=m.region
          JOIN render_jobs j USING (quote_id) LEFT JOIN render_results r USING (job_id)
          WHERE m.model_id=:id ON CONFLICT (job_id) DO NOTHING"""),
            {"id": model_id},
        )
