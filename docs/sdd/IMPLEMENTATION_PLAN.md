# Wearo.ai MVP implementation plan

## Plan state

**Backlog status:** Execution authorized; semantic validation exceptions remain gated as recorded in `VALIDATION_REPORT.md`.  
**Application-code status:** Phase 0 foundations in progress; no product feature code started.  
**Execution policy after approval:** one unblocked atomic task at a time; test it; update task/story/epic state and trace evidence; report completed work and the new ready queue.

## Execution evidence

| Task | Result | Evidence | Commit |
|---|---|---|---|
| T-001 | DONE | `npm run validate:backlog`; 90/90 WR, 36/36 QA, complete fields, acyclic graph, decision/deferred guards | Pending: workspace policy prevents creation of `.git` |
| T-002 | DONE | `pnpm lint:openapi`; 55 paths, 61 operations, 47 schemas; `pnpm check:contracts` synchronized | Pending: workspace policy prevents creation of `.git` |
| T-003 | IN_PROGRESS | Migration policy, offline PostgreSQL SQL, Ruff, mypy and 2 pytest tests pass; live PostgreSQL rehearsal pending | Not eligible until live rehearsal passes |

## Delivery principles

1. The 90 rows in `WR_Traceability_Matrix.csv` are the scope authority. FULL and BOUNDED treatment is preserved; the 107 deferred master requirements remain out of scope.
2. Dependencies and invariants determine order. UI screens do not determine architecture or sprint sequence.
3. Open decisions are gates, not invitations to invent defaults. Example API values are never commercial policy.
4. Contract, migration, security, observability, and test changes ship with the feature they govern.
5. Every completed requirement must have the path `WR → Epic → Story → Task → QA evidence` in `TASK_DEPENDENCIES.md`.
6. Jewellery stays disabled unless the representative golden set and DEC-02 pass. A mock renderer cannot satisfy real fidelity acceptance.

## Dependency-ordered increments

| Increment | Entry criteria | Tasks | Deliverable / exit evidence |
|---|---|---|---|
| I0 — Backlog approval | SDD source pack available | This document set | Principal/Product approval of epics, stories, tasks, dependencies, trace coverage, and explicit blockers. |
| I1 — Contract and delivery baseline | Backlog approved | T-001–T-005 | 90-row trace validator; OpenAPI/client and migration conventions; CI; approved visual primitives. |
| I2 — Secure identity and tenancy | I1 foundations done; DEC-05/06/09 where used | T-006–T-015 | Phone/email OTP contracts, secure sessions, one-tenant onboarding, roles, tenant isolation, separate admin MFA; QA-001/011–013/018/034/035 evidence. |
| I3 — Private media and catalogue | I2 authorization done; DEC-01/02/04/06/07/10 where used | T-016–T-030 | Private media, image validation, consent, lifecycle requests, category gates, merchant catalogue, truthful discovery; QA-002–004/013/016/019/021/025/026/028–030/032. |
| I4 — Money foundation | Effective account context done; DEC-03/05 | T-031–T-039 | Append-only wallet, immutable prices, packs, gateway/webhook, invoices, history and concurrency proof; QA-006–011/022/033/036. |
| I5 — Render vertical slice | I2–I4 done; DEC-01–03/07–09 | T-040–T-049 | Quote→hold→queue→approved provider→quality→private delivery→settlement/recredit; QA-004–008/013/017/020/024/032. |
| I6 — Consumer pilot experience | Render slice and mobile shell done | T-050–T-053 | Mobile guest discovery through paid result, feedback/deletion/recent results, and wallet; applicable consumer E2E suite. |
| I7 — Merchant and Mirror pilot | Catalogue, tenant wallet, render, retention policy done; DEC-02/04 | T-054–T-062 | Temporary private in-store flow, cleanup, consented exact-item enquiry, bounded merchant insights; QA-007/012/014/015/019/020/023/032. |
| I8 — Admin and operations | Money/render/merchant event sources done; DEC-09 | T-063–T-070 | Audited controls, reconcilable dashboard, cases/anomalies, redacted observability and runbooks; QA-009/016–018/023/024. |
| I9 — Release and category gates | All applicable implementation tasks done | T-071–T-075 | 36-case suite, security review, real golden evaluation, staged deployment rehearsal, signed capability-level go/no-go. |

## Critical path

`T-001 → T-002/T-003 → T-004 → T-006 → T-010/T-011 → T-017/T-025/T-031 → T-032/T-034 → T-040/T-041 → T-043/T-044 → T-046/T-047 → T-050 and T-055 → T-071 → T-074 → T-075`

Decision-sensitive branches rejoin the critical path at category gating, price configuration, provider execution, payment confirmation, retention cleanup, and pilot sign-off.

## Initial ready and blocked queues

### Ready after backlog approval

- `T-001` — build the executable trace inventory.

### Explicitly decision-blocked

- `T-005` by DEC-10.
- `T-007`, `T-008` by DEC-05/09.
- `T-019`, `T-021` by DEC-04/06/07 as applicable.
- `T-023`, `T-057` by DEC-04.
- `T-026`, `T-045`, `T-073` by DEC-01/02/08 and provider approval.
- `T-033` by DEC-03.
- `T-035`, `T-037` by DEC-05.
- `T-042` by DEC-07/09.
- `T-043`, `T-070` by DEC-09.
- `T-075` until all capability-specific decision gates have signed evidence.

`TODO` tasks downstream of a blocked dependency remain TODO until selected; their readiness calculation will still exclude them.

## Unresolved decisions — no inferred requirements

| ID | Required decision | Accountable reviewers | Implementation consequence |
|---|---|---|---|
| DEC-01 | Exactly 2–3 first-pilot apparel categories | Product + AI quality | Controls catalogue eligibility and golden-set coverage. |
| DEC-02 | Necklace/earring dataset acceptance and launch | Product + AI quality + pilot merchant | Jewellery remains disabled if not explicitly approved. |
| DEC-03 | Per-action prices, two pack values/discount, promo value/expiry/spend order | Product + Finance | Blocks production price seeds, quote semantics, and checkout assertions. |
| DEC-04 | B2C result and store-session retention/TTL | Privacy + Product | Blocks published lifecycle copy and scheduled purge timing. |
| DEC-05 | India OTP/payment providers and GST/invoice legal outcome | Finance + Engineering + Legal | Blocks live adapters, enabled rails, and final invoice fields. |
| DEC-06 | Adult-only controls or approved guardian route | Legal + Product | Blocks final consent/eligibility behavior. |
| DEC-07 | Renderer, region, DPA/training/retention terms, model costs | AI + Security | Blocks sending real customer assets and production model routing. |
| DEC-08 | Golden set, hard thresholds, review sampling | Product + AI quality | Blocks category enablement and fidelity sign-off. |
| DEC-09 | Performance SLOs, provider timeouts, quotas, alert ownership | Engineering + Ops | Blocks final rate/time/retry configuration and operational acceptance. |
| DEC-10 | Font/logo rights and typography tokens | Design | Blocks production visual-asset completion, not semantic component contracts. |

## Per-task execution loop after approval

1. Recompute the ready queue from `TASKS.md`; select exactly one TODO task whose task and decision dependencies are complete.
2. Change only that task to `IN_PROGRESS`; note owner/start/evidence link in the task change or work log.
3. Implement the smallest contract/data/code/configuration change satisfying its acceptance criteria.
4. Run the named unit/contract/integration/security/E2E checks proportional to the task. Never substitute a mock result for a live provider/legal/quality gate.
5. Synchronize OpenAPI, migrations, generated client, documentation, and trace links when impacted.
6. If acceptance and DoD pass, set the task `DONE`; otherwise return it to TODO or set BLOCKED with a concrete dependency/decision.
7. Update parent story/epic only when all children qualify; report completed work, tests/evidence, changed files, blockers, and remaining ready tasks.

## Release gates

- **Coverage:** exactly 90/90 selected WR IDs, no unknown WR ID, every WR linked to an epic/story/task/QA test.
- **Scope:** FULL outcomes retained; BOUNDED outcomes tested only to their documented pilot boundary; deferred work not surfaced as enabled.
- **Security/privacy:** tenant isolation, secure OTP/sessions, admin realm separation, explicit consent, private media, retention/deletion, and audit pass.
- **Money:** duplicate/replay/concurrency/failure tests show no double credit/debit, negative balance, orphan hold, wrong-wallet activity, or invoice mismatch.
- **AI quality:** real approved provider/category/version passes golden evidence; unsafe output blocks delivery/category.
- **Experience:** phone/tablet/desktop, keyboard/screen reader, recovery, and next-customer privacy pass.
- **Operations:** redacted telemetry, cost/usage reconciliation, backups/restore, rollback, incident/case procedures, and capability flags are rehearsed.
- **Approval:** Product, Engineering, Security/Privacy, Finance/Legal, AI quality, Design, and Ops sign only their accountable decisions/gates.

## Backlog validation record

Validation must be rerun whenever these planning files change. The expected baseline is:

- Source WR rows: **90 unique**.
- Priorities/treatments: **59 P0 / 31 P1; 29 FULL / 61 BOUNDED**.
- Source acceptance tests: **36 unique (QA-001 through QA-036)**.
- Planning artifacts: **10 epics, 38 stories, 75 atomic tasks**.
- Allowed task categories: Frontend, Backend, Database, API Integration, AI/LLM Integration, Security, Testing, DevOps.
- Allowed story points: 1, 2, 3, 5.
- Allowed statuses: TODO, IN_PROGRESS, BLOCKED, DONE.

Any mismatch blocks backlog approval or later release until reconciled against the source-of-truth hierarchy.
