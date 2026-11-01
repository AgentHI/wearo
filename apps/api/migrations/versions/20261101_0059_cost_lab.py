"""Create the isolated Model Cost Lab schema.

Revision ID: 20261101_0059
Revises: 20261101_0058
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261101_0059"
down_revision: str | None = "20261101_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DDL = """
CREATE SCHEMA cost_lab;
CREATE TABLE cost_lab.login_sessions (
  session_id uuid PRIMARY KEY, token_hash bytea NOT NULL UNIQUE, username text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);
CREATE TABLE cost_lab.login_attempts (
  attempt_id uuid PRIMARY KEY, username text NOT NULL, ip_hash bytea NOT NULL,
  succeeded boolean NOT NULL, attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_cost_lab_login_attempts ON cost_lab.login_attempts(username, attempted_at DESC);
CREATE TABLE cost_lab.model_providers (
  provider_id uuid PRIMARY KEY, name text NOT NULL UNIQUE, provider_type text NOT NULL,
  api_base_url text, secret_ciphertext bytea, secret_reference text,
  enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_provider_secret CHECK (secret_ciphertext IS NOT NULL OR secret_reference IS NOT NULL)
);
CREATE TABLE cost_lab.ai_models (
  model_id uuid PRIMARY KEY, provider_id uuid NOT NULL REFERENCES cost_lab.model_providers(provider_id),
  name text NOT NULL, api_identifier text NOT NULL, version text,
  input_formats jsonb NOT NULL DEFAULT '[]', output_formats jsonb NOT NULL DEFAULT '[]',
  quality_levels jsonb NOT NULL DEFAULT '[]', enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(provider_id, api_identifier, version)
);
CREATE TABLE cost_lab.model_pricing (
  pricing_id uuid PRIMARY KEY, model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
  effective_at timestamptz NOT NULL, components jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT ck_pricing_components CHECK (jsonb_typeof(components)='array')
);
CREATE INDEX ix_cost_lab_pricing_model_effective ON cost_lab.model_pricing(model_id, effective_at DESC);
CREATE TABLE cost_lab.quality_profiles (
  profile_id uuid PRIMARY KEY, code text NOT NULL UNIQUE CHECK (code IN ('LOW','MEDIUM','HIGH')),
  width integer NOT NULL CHECK (width > 0), height integer NOT NULL CHECK (height > 0),
  compression_quality integer NOT NULL CHECK (compression_quality BETWEEN 1 AND 100),
  output_resolution text NOT NULL, settings jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO cost_lab.quality_profiles(profile_id,code,width,height,compression_quality,output_resolution) VALUES
  (gen_random_uuid(),'LOW',512,512,70,'512x512'),
  (gen_random_uuid(),'MEDIUM',1024,1024,82,'1024x1024'),
  (gen_random_uuid(),'HIGH',1536,1536,92,'1536x1536');
CREATE TABLE cost_lab.model_quality_mapping (
  mapping_id uuid PRIMARY KEY, model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
  profile_id uuid NOT NULL REFERENCES cost_lab.quality_profiles(profile_id), supported boolean NOT NULL DEFAULT true,
  provider_quality text, request_parameters jsonb NOT NULL DEFAULT '{}', UNIQUE(model_id, profile_id)
);
CREATE TABLE cost_lab.benchmark_assets (
  asset_id uuid PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('PERSON','JEWELLERY','BLOUSE','SAREE','DRESS')),
  name text NOT NULL, original_path text NOT NULL, variants jsonb NOT NULL DEFAULT '{}',
  content_hash text NOT NULL, authorized boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(), replaced_at timestamptz
);
CREATE INDEX ix_cost_lab_assets_kind ON cost_lab.benchmark_assets(kind) WHERE replaced_at IS NULL;
CREATE TABLE cost_lab.benchmark_runs (
  run_id uuid PRIMARY KEY, model_id uuid NOT NULL REFERENCES cost_lab.ai_models(model_id),
  category text NOT NULL, qualities jsonb NOT NULL, tryons_per_quality integer NOT NULL CHECK (tryons_per_quality BETWEEN 1 AND 100),
  random_seed bigint NOT NULL, prompt text NOT NULL, prompt_version text NOT NULL,
  dataset_fingerprint text NOT NULL, pricing_snapshot jsonb NOT NULL, quality_snapshot jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCEL_REQUESTED','CANCELLED')),
  estimated_max_usd numeric(18,8), spending_limit_usd numeric(18,8), confirmed_at timestamptz NOT NULL,
  total_jobs integer NOT NULL, completed_jobs integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz
);
CREATE INDEX ix_cost_lab_runs_status ON cost_lab.benchmark_runs(status, created_at);
CREATE TABLE cost_lab.benchmark_combinations (
  combination_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES cost_lab.benchmark_runs(run_id) ON DELETE CASCADE,
  ordinal integer NOT NULL, quality text NOT NULL, person_asset_id uuid NOT NULL REFERENCES cost_lab.benchmark_assets(asset_id),
  product_asset_id uuid NOT NULL REFERENCES cost_lab.benchmark_assets(asset_id), UNIQUE(run_id, ordinal)
);
CREATE TABLE cost_lab.tryon_runs (
  tryon_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES cost_lab.benchmark_runs(run_id) ON DELETE CASCADE,
  combination_id uuid NOT NULL REFERENCES cost_lab.benchmark_combinations(combination_id),
  status text NOT NULL CHECK (status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED','CANCELLED')),
  attempts integer NOT NULL DEFAULT 0, leased_by text, lease_expires_at timestamptz,
  provider_request_id text, latency_ms integer, output_path text, error_code text, error_detail text,
  billable boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX ix_cost_lab_tryon_claim ON cost_lab.tryon_runs(status, created_at);
CREATE TABLE cost_lab.tryon_usage (
  usage_id uuid PRIMARY KEY, tryon_id uuid NOT NULL UNIQUE REFERENCES cost_lab.tryon_runs(tryon_id) ON DELETE CASCADE,
  text_input_tokens bigint, image_input_tokens bigint, cached_input_tokens bigint, image_output_tokens bigint,
  total_reported_tokens bigint, other_units jsonb NOT NULL DEFAULT '{}', calculated_cost_usd numeric(18,8) NOT NULL DEFAULT 0,
  provider_cost_usd numeric(18,8), usage_source text NOT NULL CHECK (usage_source IN ('PROVIDER_REPORTED','WEARO_ESTIMATED')),
  raw_metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE cost_lab.fx_rates (
  rate_id uuid PRIMARY KEY, base_currency text NOT NULL, quote_currency text NOT NULL,
  rate numeric(20,8) NOT NULL CHECK (rate > 0), source text NOT NULL, fetched_at timestamptz NOT NULL,
  UNIQUE(base_currency, quote_currency, fetched_at)
);
CREATE TABLE cost_lab.audit_events (
  event_id uuid PRIMARY KEY, action text NOT NULL, target_type text, target_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}', occurred_at timestamptz NOT NULL DEFAULT now()
);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP SCHEMA cost_lab CASCADE")
