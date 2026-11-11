# AWS private image storage

Wearo stores customer and business images in one private S3 bucket. S3 has object-key
prefixes rather than real folders; the application creates these prefixes automatically when
the first object of each type is uploaded.

## Layout

```text
private/
├── accounts/<account-id>/
│   ├── person-sources/<asset-id>
│   ├── product-sources/<asset-id>
│   ├── render-results/<asset-id>
│   ├── business-logos/<asset-id>
│   └── advertisements/<asset-id>
│       └── (prepared derivatives use an object-name suffix)
└── previews/<render-job-id>
```

All objects remain private. The browser receives images through authenticated Wearo API
routes; the bucket needs no public access and no CORS configuration. Database retention is
authoritative: product sources, results, and advertisements expire after 30 days; person
sources are retained until deletion, account closure, or 12 months of inactivity; requested
deletions and temporary store-session media are purged within 24 hours. The S3 lifecycle rule
is only a safety net for previews and abandoned multipart uploads.

## Create it in the AWS console

1. Choose the AWS region used by the API and worker (for India, normally `ap-south-1`).
2. Open **IAM > Roles > Create role**. Choose the compute service that runs Wearo (for
   example ECS task), finish creating the role, and copy its ARN. Use the same role for the API
   and render worker, or deploy the template once per role after extending its principals.
3. Open **CloudFormation > Create stack > With new resources**.
4. Upload `infra/aws/private-media.yaml`.
5. Enter a globally unique bucket name such as `wearo-prod-private-media-<account-id>` and the
   application role ARN. Create the stack.
6. In the new S3 bucket, verify **Block all public access** is on, **Object ownership** is
   bucket-owner enforced, and default encryption shows SSE-S3. Do not enable ACLs, public
   access, static website hosting, or versioning; versioning would retain deleted customer
   image versions beyond the application deletion workflow.
7. In **Management > Lifecycle rules**, verify the preview and incomplete-upload rules created
   by the stack. Do not add a blanket expiry rule to `private/accounts/`; the database applies
   different retention periods by image purpose.
8. Configure the API, worker, and scheduled purge process with:

   ```dotenv
   WEARO_PRIVATE_STORAGE_BACKEND=S3
   WEARO_PRIVATE_STORAGE_BUCKET=wearo-prod-private-media-<account-id>
   AWS_REGION=ap-south-1
   ```

   On AWS compute, use the IAM role; do not put long-lived AWS access keys in `.env`.
9. Restart the API and worker. Upload one image of each supported kind; the prefixes will
   appear in the S3 console automatically.
10. Run the scheduled purge command at least hourly so database-driven deletion deadlines are
    honored: `python -m apps.api.wearo_api.operations purge --limit 100`.

## Create it with the AWS CLI

After configuring the AWS CLI for the target account, replace both placeholders:

```bash
aws cloudformation deploy \
  --region ap-south-1 \
  --stack-name wearo-private-media \
  --template-file infra/aws/private-media.yaml \
  --parameter-overrides \
    BucketName=wearo-prod-private-media-ACCOUNT_ID \
    ApplicationRoleArn=arn:aws:iam::ACCOUNT_ID:role/wearo-app
```

Check the result without downloading private objects:

```bash
aws cloudformation describe-stacks \
  --region ap-south-1 \
  --stack-name wearo-private-media \
  --query 'Stacks[0].Outputs'

aws s3api get-public-access-block \
  --bucket wearo-prod-private-media-ACCOUNT_ID
```

Use separate buckets and IAM roles for development, staging, and production. Enable CloudTrail
S3 data events and access alerts in production if the additional audit cost is acceptable.

## Production Cost Lab storage

Cost Lab must use a bucket and execution role that are separate from customer-media storage.
Complete this checklist when the Cost Lab API and worker are ready for production deployment.

### 1. Create the production execution role

1. In **IAM > Roles**, create or select the execution role used by the production Cost Lab API
   and worker. For ECS, use the task role, not the task execution role that only pulls images and
   sends logs.
2. Prefer one shared application role when both processes have the same storage permissions. If
   they use separate roles, add both role ARNs to the bucket policy or deploy one policy statement
   per role.
3. Do not create IAM users or long-lived access keys for production. AWS compute must obtain
   temporary credentials through its attached role.

### 2. Deploy the production bucket

Use the supplied CloudFormation template, replacing the account ID and role name:

```bash
aws cloudformation deploy \
  --region ap-south-1 \
  --stack-name wearo-prod-cost-lab-storage \
  --template-file infra/aws/cost-lab-storage.yaml \
  --parameter-overrides \
    BucketName=wearo-prod-cost-lab-ACCOUNT_ID-aps1 \
    CostLabRoleArn=arn:aws:iam::ACCOUNT_ID:role/wearo-prod-cost-lab
```

The stack creates a retained, private, bucket-owner-enforced bucket with SSE-S3 encryption,
TLS-only access, and an incomplete multipart-upload lifecycle rule. It grants the supplied role
only `ListBucket` for `cost-lab/*` and `GetObject`, `PutObject`, and `DeleteObject` below that
prefix. Retaining the bucket protects production evaluation history if the stack is deleted.

After deployment, verify:

```bash
aws cloudformation describe-stacks \
  --region ap-south-1 \
  --stack-name wearo-prod-cost-lab-storage \
  --query 'Stacks[0].Outputs'

aws s3api get-public-access-block \
  --bucket wearo-prod-cost-lab-ACCOUNT_ID-aps1

aws s3api get-bucket-encryption \
  --bucket wearo-prod-cost-lab-ACCOUNT_ID-aps1

aws s3api get-bucket-policy-status \
  --bucket wearo-prod-cost-lab-ACCOUNT_ID-aps1
```

The policy status must report that the bucket is not public. Keep all four S3 Block Public Access
settings enabled, keep ACLs disabled, and do not enable static website hosting or CORS.

### 3. Review the execution-role policy

If the role is managed outside the CloudFormation stack, embed or attach this least-privilege
identity policy after replacing the bucket name:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListWearoCostLabPrefix",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::wearo-prod-cost-lab-ACCOUNT_ID-aps1",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "cost-lab",
            "cost-lab/*"
          ]
        }
      }
    },
    {
      "Sid": "ManageWearoCostLabObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::wearo-prod-cost-lab-ACCOUNT_ID-aps1/cost-lab/*"
    }
  ]
}
```

This is an IAM identity policy and must not contain `Principal`. A bucket policy is a resource
policy and must contain `Principal`; do not paste one policy type into the other editor.

### 4. Configure production observability

1. Enable CloudTrail S3 object-level data events for the production bucket. Encrypt the trail and
   its CloudWatch Logs group and restrict access to the operations/security roles.
2. Configure S3 server access logging to a separate encrypted logging bucket when request-level
   access records are required. Never deliver access logs back into the Cost Lab data prefix.
3. Enable S3 Storage Lens or equivalent inventory monitoring for object counts, bytes, incomplete
   uploads, and unusual growth.
4. Add CloudWatch alarms for API/worker errors and the scheduled job that verifies database paths
   against S3 objects. Alert on repeated `AccessDenied`, missing objects, and deletion failures.
5. Record the bucket and CloudTrail data-event costs in the production budget. S3 charges include
   storage, requests, data transfer, lifecycle operations, inventory/analytics, and optional audit
   logging; audit events can be material for request-heavy workloads.

### 5. Decide production retention and recovery

Do not add a blanket expiration rule to `cost-lab/datasets/` or `cost-lab/benchmarks/`. Historical
benchmarks, promoted final checks, and audit evidence can depend on those objects. Define the
approved retention period before adding purpose-specific rules.

Bucket versioning is intentionally off by default because application deletion should remove the
object rather than leave recoverable noncurrent versions indefinitely. If production recovery
requirements justify versioning, also define noncurrent-version expiration, deletion governance,
and the extra storage cost before enabling it. Use a separate backup or replication design when
the required recovery point includes accidental application deletion or regional failure.

### 6. Migrate existing Cost Lab objects

The repository includes a non-destructive one-time migration tool for both customer private media
and Cost Lab data. It preserves every relative object key, verifies the AWS account and buckets,
uploads with SSE-S3 and SHA-256 metadata, reconciles database references, and writes an audit
manifest. It never deletes local files or S3 objects.

First take a database backup, configure the production bucket names and local source roots in a
protected environment file, authenticate with the production deployment role/profile, and run the
default dry-run:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/migrate_storage_to_s3.py \
  --env-file .env.prod
```

Review `planned_uploads`, `missing_local_references`, `missing_s3_references`, the AWS caller ARN,
and the manifest path. Stop API and worker writes for the final pass, then apply using the expected
12-digit production account ID. Include variant repair if legacy Cost Lab dataset/person records
do not contain all LOW, MEDIUM, and HIGH mappings:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/migrate_storage_to_s3.py \
  --env-file .env.prod \
  --apply \
  --expected-account ACCOUNT_ID \
  --repair-missing-variants
```

An apply exits nonzero if an upload/repair fails or a database-referenced S3 object is still
missing. Re-run the dry-run after the apply; `planned_uploads` and `missing_s3_references` should
both be zero. The database continues to store relative keys, so a successful migration does not
rewrite them to S3 URLs. Keep the generated manifest, database backup, and local source for the
rollback window. Do not put AWS access keys in `.env.prod`; use temporary role credentials or an
AWS CLI profile on the migration workstation.

The manual equivalent is retained below for incident recovery and independent verification.

1. Export database manifests for `cost_lab.benchmark_assets.original_path`, every value in
   `variants`, `cost_lab.tryon_runs.output_path`, model-test paths, and knowledge-file paths.
2. Compute a local file inventory and SHA-256 manifest.
3. Copy the existing local tree while preserving every relative path:

   ```bash
   aws s3 sync \
     .wearo-storage/cost-lab/ \
     s3://wearo-prod-cost-lab-ACCOUNT_ID-aps1/cost-lab/ \
     --region ap-south-1 \
     --sse AES256 \
     --no-follow-symlinks
   ```

4. Do not use `--delete` during migration. Compare local and S3 object counts, total bytes, and
   hashes, then verify every database-referenced path exists.
5. Stop Cost Lab writes, run a final incremental sync, repeat reconciliation, and only then switch
   the API and worker to S3.

Database paths remain relative and must not be rewritten when the same keys are preserved. Legacy
`assets/` and `outputs/` keys can coexist with new `datasets/` and `benchmarks/` keys below the
`cost-lab/` prefix.

### 7. Configure and deploy the production services

Set these variables on both the production Cost Lab API and worker:

```dotenv
COST_LAB_STORAGE_BACKEND=S3
COST_LAB_STORAGE_BUCKET=wearo-prod-cost-lab-ACCOUNT_ID-aps1
AWS_REGION=ap-south-1
```

Do not set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_PROFILE` on AWS compute. Confirm
that the API and worker receive the intended execution role, then restart both processes.

### 8. Production verification and rollback

Verify one item from every category: dataset original, Low/Medium/High variants, historical
benchmark output, final-check output, model-test input/output, and knowledge PDF. Then create a new
dataset image and benchmark, verify their S3 keys, and test an allowed deletion.

Keep the pre-migration storage and database backup for the approved rollback window. If validation
fails, stop writes, restore `COST_LAB_STORAGE_BACKEND=FILESYSTEM`, restart both services, and
investigate the manifest differences. Do not delete the local source or production bucket until
the complete reconciliation and rollback window have passed.

## Scope

This bucket backs the customer-facing API, render worker, advertisements, and scheduled media
purge. Images under `apps/web/public` are versioned build assets and remain in the web deploy.
Cost Lab uses a separate bucket and IAM role because its retention and access model differs from
customer media. Deploy `infra/aws/cost-lab-storage.yaml`, then configure both the Cost Lab API and
worker with `COST_LAB_STORAGE_BACKEND=S3`, `COST_LAB_STORAGE_BUCKET=<bucket>`, and the same AWS
region. Objects are stored below `cost-lab/` with `datasets/`, `benchmarks/`, `model-tests/`, and
`knowledge/` prefixes. Existing local Cost Lab files must be copied with their current relative
paths before switching the backend; database paths remain relative and continue to resolve.
