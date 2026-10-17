# SDD story template

**Story ID:** `STORY-<DOMAIN>-###`  
**User outcome:** <observable behavior>  
**Source scope IDs:** `WR-###` (original)  
**Master priority / pilot treatment:** P0/P1; FULL or BOUNDED (quote exact pilot treatment)  
**Non-goals:** link deferred master items / no feature creep.  
**Design views:** `FE-S##`, device widths 360/768/1200, brand contrast + accessibility states.  
**Domain modules:** BE-##, data tables, states, error codes.  
**Contract:** OpenAPI operation IDs, request/response examples, permissions, idempotency, compatibility.  
**Privacy/security review:** access context, consent, asset retention, rate limits, audit.  
**Money:** price lock/reservation/settlement/recredit if applicable.  
**Monitoring:** events, trace IDs, alerts with no personal images/OTP.  
**Acceptance proof:** QA-### tests in Given/When/Then form; negative tenant and replay cases.  
**Dependencies:** blocking DEC items, other stories and migrations.  
**Definition of Done:** implementation + contract sync + tests + code review + screenshots if UI + evidence link + documentation + no out-of-scope changes.
