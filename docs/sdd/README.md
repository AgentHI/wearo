# Wearo.ai MVP — Spec-Driven Development Pack v1.0

**Sources:** Wearo AI MVP Product and Platform Requirements v1.0 and Wearo AI Brand Colours and UI Guidelines v1.0, provided on 17 Oct 2026.

## Contents

- `EPICS.md` — dependency-oriented implementation epics.
- `USER_STORIES.md` — user stories with original WR and QA trace links.
- `TASKS.md` — atomic, categorized developer backlog with dependencies, points, acceptance, DoD and status.
- `TASK_DEPENDENCIES.md` — execution graph, decision gates and 90-row WR-to-test traceability.
- `IMPLEMENTATION_PLAN.md` — approval state, dependency-ordered increments, execution loop and release gates.
- `Wearo_MVP_Implementation_Spec_v1.0.pdf` — human-readable consolidated frontend + backend engineering specification.
- `Wearo_MVP_Implementation_Spec_v1.0.md` — editable source of the complete specification, including 90 exact WR trace rows.
- `openapi.yaml` — proposed machine-readable REST API contract; contract-first coding reference.
- `WR_Traceability_Matrix.csv` — 90/90 selected WR IDs with source wording, original master acceptance and MVP boundary, source page and suggested test cases.
- `Acceptance_Test_Cases.csv` — 36 QA acceptance cases for development and pilot sign-off.
- `Decision_Log.md` — outstanding implementation/product decisions to confirm before development / launch.
- `Story_Template.md` — SDD-ready engineering story template.

## Source-of-truth hierarchy

1. Uploaded MVP v1.0 scope overlay — selected original WR IDs, FULL/BOUNDED boundary, non-goals.
2. Uploaded brand PDF v1.0 — exact color codes and visual behavior across phone/tablet/web.
3. This implementation spec + decision log — proposed engineering designs and contracts, not new product WR requirements.
4. Code, OpenAPI, generated clients and tests must remain synchronized with the approved spec.

**Important:** 90 selected (59 P0 / 31 P1; 29 FULL / 61 BOUNDED). Another 107 master items stay deferred. Technical recommendations do not establish real renderer fidelity, legal/tax treatment, approved vendor, specific retention interval or actual token prices. Do not ship jewellery until category fidelity validation passes.

## Engineering usage

1. Close blocking DEC-01..DEC-10, recording owner/signoff.
2. Review endpoint contracts and security/session policy in `openapi.yaml`, produce stable mock server + typed TypeScript client.
3. Split by S0...S5 slices. Each story names original WR IDs, FE view, API path, DB migration, threats, precise QA cases.
4. Run unit/contract/concurrency/tenant-isolation/E2E/quality tests in CI and preserve proof for each selected WR.
5. Reconcile implementation changes into spec + API + test CSV before code approval. Never edit master WR identifiers here.
