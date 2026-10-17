# Wearo.ai MVP backlog validation report

**Validated:** 17 October 2026  
**Validator:** `npm run validate:backlog`  
**Scope:** structural traceability, task completeness, dependency integrity, decision gates, and deferred-scope guardrails

## Automated result

- 90/90 unique selected WR IDs are present.
- Source distribution remains 59 P0 / 31 P1 and 29 FULL / 61 BOUNDED.
- All 36 QA IDs are present and every WR-to-QA mapping exactly matches `WR_Traceability_Matrix.csv`.
- Every trace row resolves to an existing epic, story, and primary task that cites the WR.
- Every development task has a unique ID, required category, description, original WR IDs, dependencies, allowed story points, acceptance criteria, Definition of Done, and allowed status.
- All eight task categories are represented.
- Task dependencies reference existing earlier tasks and the graph is acyclic.
- Tasks with unresolved DEC dependencies are marked `BLOCKED`; no task is blocked without a named decision.
- Automated positive-scope guards detect no implementation commitment for the documented deferred feature families.

## Principal-engineer semantic review exceptions

These are backlog corrections, not new requirements. They must be resolved before their affected implementation slice starts:

1. `WR-013`: make the single user product-reference upload path explicit in API/backend/frontend tasks.
2. `WR-039`: add persistence/API behavior that attaches feedback to the authorized render.
3. `WR-167`: add idempotent one-time first-preview promotional credit issuance.
4. `WR-010`: make the owner-scoped recent-results list contract explicit.
5. `WR-025`: make face, skin tone, hair, apparent proportions, background, and identity-drift quality evidence explicit.
6. `WR-096`: explicitly include temporary-session count in merchant aggregates.
7. `WR-110`: correct its primary trace from enquiry-only tasks to exact verified seller-link behavior.
8. `WR-188` and `WR-193`: add an explicit customer-facing request/support submission and status surface.
9. Add `T-056` to `WR-079` result-detail trace and `T-067` to `WR-127` moderation trace.

Dependency refinements required before affected slices begin:

- Split final DEC-10 asset approval from the reusable semantic frontend foundation so it does not block all UI work.
- Avoid coupling the shared session implementation to completion of both phone and email provider adapters.
- Separate generic category-gate implementation from DEC-01/DEC-02 production category selection.
- Separate queue/worker infrastructure from final DEC-09 production tuning.
- Add tenant-isolation verification as a prerequisite of invoice delivery.

## Deferred-scope review

No positive implementation task was found for native apps, customizable/3D avatars, AR/live video, rings/bangles, inventory or branch synchronization, booking/deposit engines, subscriptions, advanced promotions, wallet-history export, a public status portal, provider fine-tuning, multi-country billing, or sophisticated fraud analytics.

The manual data export in `T-022` is the bounded data-rights workflow required by `WR-188`; it is not the deferred wallet-history export from `WR-165`.

## Approval consequence

Phase 0 contract, traceability, migration-convention, and CI work may proceed. Affected feature slices may not start until their semantic trace correction is made in the backlog without changing the underlying WR requirement or MVP boundary.
