# ruff: noqa: E501
"""Add managed communication templates and durable delivery queue.

Revision ID: 20261114_0082
Revises: 20261107_0081
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261114_0082"
down_revision: str | None = "20261107_0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE communication_templates (
      template_id uuid PRIMARY KEY,
      channel text NOT NULL CHECK (channel IN ('EMAIL','SMS','WHATSAPP')),
      template_key text NOT NULL,
      category text NOT NULL CHECK (category IN ('NOTIFICATION','SUPPORT','BILLING')),
      display_name text NOT NULL,
      subject text,
      body text NOT NULL,
      signature text,
      generation_prompt text,
      status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','ARCHIVED')),
      version integer NOT NULL DEFAULT 1 CHECK (version > 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (channel, template_key, version)
    );
    CREATE UNIQUE INDEX uq_active_communication_template
      ON communication_templates(channel, template_key) WHERE status='ACTIVE';

    CREATE TABLE communication_jobs (
      job_id uuid PRIMARY KEY,
      channel text NOT NULL CHECK (channel IN ('EMAIL','SMS','WHATSAPP')),
      template_key text NOT NULL,
      recipient text NOT NULL,
      variables jsonb NOT NULL DEFAULT '{}'::jsonb,
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      deduplication_key text,
      status text NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED','PROCESSING','DELIVERED','RETRY','FAILED','CANCELLED')),
      scheduled_at timestamptz NOT NULL DEFAULT now(),
      attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
      max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
      leased_by text,
      lease_expires_at timestamptz,
      provider_message_id text,
      last_error_code text,
      delivered_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX uq_communication_job_deduplication
      ON communication_jobs(deduplication_key) WHERE deduplication_key IS NOT NULL;
    CREATE INDEX ix_communication_jobs_claim
      ON communication_jobs(status, scheduled_at, created_at)
      WHERE status IN ('QUEUED','RETRY');

    CREATE TABLE inbound_support_messages (
      inbound_message_id uuid PRIMARY KEY,
      provider_message_id text NOT NULL UNIQUE,
      sender_email text NOT NULL,
      recipient_email text NOT NULL,
      subject text NOT NULL,
      body_text text NOT NULL,
      received_at timestamptz NOT NULL,
      response_job_id uuid REFERENCES communication_jobs(job_id),
      created_at timestamptz NOT NULL DEFAULT now()
    );

    INSERT INTO communication_templates
      (template_id, channel, template_key, category, display_name, subject, body,
       signature, status)
    VALUES
      (gen_random_uuid(),'EMAIL','WELCOME','NOTIFICATION','Welcome',
       'Welcome to Wearo.ai, {{name}}',
       'Welcome to Wearo.ai. We are glad to have you with us.',
       'The Wearo.ai team','ACTIVE'),
      (gen_random_uuid(),'EMAIL','NEW_FEATURES','NOTIFICATION','New features',
       'What is new at Wearo.ai',
       'Here are the latest Wearo.ai features available to your business: {{features}}',
       'The Wearo.ai team','ACTIVE'),
      (gen_random_uuid(),'EMAIL','MONTHLY_REPORT','NOTIFICATION','Monthly report',
       'Your Wearo.ai monthly report for {{report_month}}',
       'Your monthly report is ready. {{report_summary}}',
       'The Wearo.ai team','ACTIVE'),
      (gen_random_uuid(),'EMAIL','SUPPORT_DEFAULT_RESPONSE','SUPPORT','Default support response',
       'We received your support request: {{original_subject}}',
       'Hello,\n\nWe received your request and our support team will review it. Reference: {{support_reference}}.',
       'Wearo.ai Support','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_MONTH_START','BILLING','Monthly first billing notification',
       'Wearo.ai billing notice for {{billing_month}}',
       'Your Wearo.ai billing cycle details are available. Amount due: {{amount_due}}. Due date: {{due_date}}.',
       'Wearo.ai Billing','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_DAY_BEFORE','BILLING','Day before billing notification',
       'Wearo.ai payment is due tomorrow',
       'Your payment of {{amount_due}} is due on {{due_date}}. Please ignore this message if you have already paid.',
       'Wearo.ai Billing','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_DUE_DAY','BILLING','Due-day billing notification',
       'Wearo.ai payment is due today',
       'Your payment of {{amount_due}} is due today. Please ignore this message if you have already paid.',
       'Wearo.ai Billing','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_PAUSE_DAY_1','BILLING','One day after due date',
       'Action required to avoid a Wearo.ai service pause',
       'Your payment is one day overdue. Please pay {{amount_due}} to avoid interruption to your service.',
       'Wearo.ai Billing','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_PAUSE_DAY_3','BILLING','Three days after due date',
       'Final reminder before Wearo.ai service pause',
       'Your payment is three days overdue. Service may be paused if payment is not completed.',
       'Wearo.ai Billing','ACTIVE'),
      (gen_random_uuid(),'EMAIL','BILLING_ACCOUNT_PAUSED_DAY_7','BILLING','Account paused after seven days',
       'Your Wearo.ai account has been paused',
       'Your account has been paused because payment remains overdue. Complete payment to begin restoration.',
       'Wearo.ai Billing','ACTIVE');
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE inbound_support_messages;
    DROP TABLE communication_jobs;
    DROP TABLE communication_templates;
    """)
