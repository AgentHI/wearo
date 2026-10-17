# Wearo.ai MVP implementation epics

**Backlog baseline:** SDD v1.0, 17 October 2026  
**Scope authority:** 90 selected requirements in `WR_Traceability_Matrix.csv`  
**Status vocabulary:** `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`

This backlog does not add product requirements. `FULL` and `BOUNDED` retain the meanings in the source traceability matrix. Open decisions are gates; placeholder values in the OpenAPI or implementation specification are not approved commercial or operational policy.

Range shorthand in epic summaries means **selected source IDs within the shown endpoints only**; it never pulls deferred/omitted IDs into scope. The exact 90-row mapping in `TASK_DEPENDENCIES.md` is authoritative.

| Epic | Outcome | Requirement coverage | Depends on | Initial status |
|---|---|---|---|---|
| EP-01 — Specification, contracts, and delivery foundation | Freeze approved choices, contract boundaries, repository/CI foundations, and traceability before feature code. | Cross-cutting support for all 90 WRs | DEC-01..DEC-10 for affected configuration | TODO |
| EP-02 — Identity, tenancy, and access control | Establish consumer, merchant, associate, worker, and independent admin identities with server-enforced ownership. | WR-133–136, WR-140–150, WR-152–153, WR-175, WR-192 | EP-01; DEC-05, DEC-06, DEC-09 | TODO |
| EP-03 — Privacy, consent, media, and customer protection | Keep images private, consented, validated, revocable, and subject to explicit retention/deletion workflows. | WR-003–007, WR-120–130, WR-187–188, WR-193 | EP-01, EP-02; DEC-04, DEC-06, DEC-07 | TODO |
| EP-04 — Catalogue, offerings, and merchant operations | Support gated categories, real merchant inventory, truthful source attribution, staff administration, and responsive shells. | WR-001–002, WR-011, WR-013–021, WR-043, WR-075, WR-077, WR-079, WR-083, WR-110, WR-133–136, WR-144–150 | EP-01, EP-02; DEC-01, DEC-02, DEC-10 | TODO |
| EP-05 — Wallet, pricing, payments, and invoices | Implement an exactly-once prepaid ledger, transparent packs/prices, secure Indian gateway integration, receipts, and reconciliation. | WR-129, WR-153, WR-157–173, WR-178, WR-189 | EP-01, EP-02; DEC-03, DEC-05 | TODO |
| EP-06 — AI render orchestration and quality | Quote, reserve, enqueue, render, quality-check, deliver, settle/recredit, and expose safe progress using approved model routes. | WR-014–015, WR-024–030, WR-040, WR-043, WR-075–077, WR-083, WR-120–121, WR-128, WR-158–161, WR-181–182, WR-191 | EP-02–EP-05; DEC-01–03, DEC-07–09 | TODO |
| EP-07 — Consumer Shop and result lifecycle | Deliver guest discovery and authenticated mobile try-on, recent results, comparison, feedback, deletion, and wallet experience. | WR-001–002, WR-007, WR-010–011, WR-013, WR-017, WR-021, WR-024–030, WR-039–040, WR-120–122, WR-127, WR-129, WR-140–142, WR-157–167 | EP-02–EP-06; DEC-10 | TODO |
| EP-08 — Mirror-lite, enquiries, and merchant insights | Run private temporary in-store sessions, exact-item enquiries, cleanup, and bounded aggregate merchant metrics. | WR-075–096, WR-110, WR-113, WR-119, WR-123–126, WR-150, WR-152–153 | EP-02–EP-06; DEC-02, DEC-04 | TODO |
| EP-09 — Administration, governance, and operations | Operate tenants, packs, model routes, audit, support/data cases, abuse review, service states, and aggregate dashboards. | WR-175–193 | EP-02–EP-06; DEC-03–05, DEC-07–09 | TODO |
| EP-10 — Verification, release, and pilot gates | Prove all 90 selected requirements and 36 acceptance scenarios across contracts, security, concurrency, responsive UX, AI quality, and deployment. | All 90 selected WRs | EP-01–EP-09; all applicable decisions signed | TODO |

## Epic completion rule

An epic is complete only when every child story and task is `DONE`, its mapped acceptance tests pass with retained evidence, contracts and migrations are synchronized, and no unresolved decision is being represented as implemented policy. Jewellery remains disabled unless DEC-02 and its quality evidence are approved.
