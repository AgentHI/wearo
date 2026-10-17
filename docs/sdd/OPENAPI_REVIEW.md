# Wearo.ai MVP OpenAPI baseline review

**Canonical contract:** `docs/sdd/openapi.yaml`  
**Version:** OpenAPI 3.1.0  
**Scope at freeze:** 55 paths, 61 operations, 47 schemas

## Contract controls

- `pnpm lint:openapi` applies Redocly's recommended rules plus errors for duplicate/unsafe operation IDs, missing 4xx responses, undefined security, unresolved references, query strings in paths, and non-strict references.
- `pnpm generate:contracts` deterministically produces TypeScript declarations in `packages/contracts/src/generated/openapi.ts`.
- `pnpm check:contracts` regenerates to a temporary directory and fails if the committed declaration differs.
- `docs/sdd/openapi.yaml` is canonical. `Wearo_AI_MVP_OpenAPI_v1.0.yaml` is retained as the original named snapshot and must not be used by generators.

## Review boundary

The contract is a proposed implementation surface governed by the original WR matrix and decision log. Example prices, TTLs, provider names, quotas, tax treatment, or quality thresholds do not become approved policy through this contract. Unresolved integrations remain adapter boundaries.

## Compatibility rule

Before implementation begins for an operation, its security context, effective account/tenant resolution, error schema, idempotency behavior, and applicable decision gate must be reviewed. Any contract change must update the generated declarations and pass lint/drift checks in the same task.
