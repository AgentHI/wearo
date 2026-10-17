# Wearo.ai MVP user stories

Stories are sequenced by prerequisites. Requirement IDs refer to the original WR identifiers; QA IDs refer to `Acceptance_Test_Cases.csv`.

Range shorthand means only IDs selected by `WR_Traceability_Matrix.csv` within those endpoints. It does not add intervening deferred IDs; consult the exact row-per-WR trace in `TASK_DEPENDENCIES.md`.

| Story | Epic | User story / observable outcome | Original WR IDs | Acceptance tests | Depends on | Status |
|---|---|---|---|---|---|---|
| ST-01.1 | EP-01 | As an engineering team, we need approved scope, decisions, and machine-checkable traceability so implementation cannot silently invent policy. | All selected WRs | QA-001–036 (mapping) | — | DONE |
| ST-01.2 | EP-01 | As a delivery team, we need versioned API/schema/client and CI foundations so all later slices share enforceable contracts. | WR-133, WR-134, WR-135, WR-136 | QA-025, QA-034 | ST-01.1 | TODO |
| ST-02.1 | EP-02 | As a consumer, I can verify by phone OTP with safe expiry, resend, retry, and guest-to-account boundaries. | WR-140, WR-141, WR-142, WR-192 | QA-001, QA-035 | ST-01.2 | TODO |
| ST-02.2 | EP-02 | As a business user, I can verify by email OTP and access only my tenant and role. | WR-144, WR-149, WR-150, WR-152, WR-153 | QA-011–013 | ST-01.2 | TODO |
| ST-02.3 | EP-02 | As a merchant owner, I can self-register one pilot business with only bounded India invoice data. | WR-144, WR-145, WR-146, WR-147 | QA-011 | ST-02.2 | TODO |
| ST-02.4 | EP-02 | As a platform administrator, I use a separate password-and-MFA realm that merchant/consumer credentials cannot enter. | WR-175, WR-189, WR-192 | QA-018 | ST-01.2 | TODO |
| ST-02.5 | EP-02 | As a user with entitlements, I see one core identity/billing platform but only the allowed B2C/B2B shell and offerings. | WR-133, WR-134, WR-136, WR-152, WR-153 | QA-013, QA-034 | ST-02.1–02.4 | TODO |
| ST-03.1 | EP-03 | As a customer, I receive capture guidance and actionable rejection for invalid images before any charge. | WR-003, WR-004, WR-125 | QA-002 | ST-02.5 | TODO |
| ST-03.2 | EP-03 | As a customer, I explicitly consent to permitted image use and see AI, limitation, retention, and training disclosures. | WR-006, WR-120, WR-121, WR-124, WR-125, WR-130, WR-187 | QA-003, QA-005, QA-021 | ST-02.5 | TODO |
| ST-03.3 | EP-03 | As an asset owner, I can privately access, report, remove, or request action on my data without cross-account leakage. | WR-122, WR-126, WR-127, WR-130, WR-187, WR-188, WR-193 | QA-013, QA-016, QA-021 | ST-03.2 | TODO |
| ST-03.4 | EP-03 | As an operator, I can enforce retention/temporary-session cleanup while retaining only legally necessary audit evidence. | WR-123, WR-130, WR-187, WR-188 | QA-014, QA-021 | ST-03.3 | BLOCKED |
| ST-04.1 | EP-04 | As a shopper, I can browse only enabled categories and distinguish retailer products from user concepts and AI output. | WR-001, WR-002, WR-013, WR-014, WR-015, WR-021, WR-043 | QA-001, QA-004, QA-028, QA-030 | ST-02.5 | BLOCKED |
| ST-04.2 | EP-04 | As a merchant owner, I can add, update, and unpublish 10–30 genuine pilot items with truthful links/attributes. | WR-017, WR-020, WR-075, WR-077, WR-079, WR-083, WR-110 | QA-019, QA-029, QA-032 | ST-02.3 | TODO |
| ST-04.3 | EP-04 | As a merchant owner, I can invite/revoke one associate whose permissions end immediately. | WR-150, WR-152 | QA-012 | ST-02.2 | TODO |
| ST-04.4 | EP-04 | As a user, I get accessible, responsive Shop, Business, Mirror, and Admin shells using the approved brand tokens. | WR-011, WR-133, WR-134, WR-135, WR-136 | QA-025, QA-034 | ST-01.2 | BLOCKED |
| ST-05.1 | EP-05 | As an account holder, I have an isolated personal or tenant wallet backed by an append-only, attributable ledger. | WR-153, WR-157, WR-160, WR-165, WR-167 | QA-006, QA-007, QA-022 | ST-02.5 | TODO |
| ST-05.2 | EP-05 | As a buyer, I see immutable action prices and transparent standard/bulk packs before approving spend. | WR-158, WR-159, WR-163, WR-166, WR-178 | QA-010, QA-017, QA-033 | ST-05.1 | BLOCKED |
| ST-05.3 | EP-05 | As a buyer, I can purchase a pack through enabled Indian payment methods and be credited exactly once. | WR-162, WR-170, WR-171, WR-173 | QA-009, QA-036 | ST-05.2 | BLOCKED |
| ST-05.4 | EP-05 | As a business buyer, I can download a legally reviewed invoice for the correct confirmed purchase. | WR-145, WR-146, WR-172, WR-173 | QA-011 | ST-05.3 | BLOCKED |
| ST-05.5 | EP-05 | As an account holder, I can see top-ups, promo credits, debits, recredits, expiry rules, and insufficient-balance guidance. | WR-129, WR-161, WR-165, WR-166, WR-167 | QA-008, QA-022, QA-033 | ST-05.1, ST-05.2 | TODO |
| ST-06.1 | EP-06 | As a user, I receive a preflight-validated, price-locked quote only for an enabled category/model and valid consent. | WR-014, WR-015, WR-027, WR-043, WR-075, WR-158, WR-159, WR-181, WR-182 | QA-003–005, QA-017 | ST-03.1, ST-03.2, ST-04.1, ST-05.2 | BLOCKED |
| ST-06.2 | EP-06 | As a payer, my render is idempotently reserved and queued without duplicate jobs or overspending. | WR-024, WR-153, WR-157, WR-160 | QA-006, QA-007 | ST-05.1, ST-06.1 | TODO |
| ST-06.3 | EP-06 | As a user, I see a truthful render state and receive one labelled result only after quality acceptance. | WR-024–030, WR-040, WR-120, WR-121, WR-128, WR-191 | QA-005, QA-008, QA-024 | ST-06.2 | TODO |
| ST-06.4 | EP-06 | As an operator, I can route approved versioned models and stop unsafe garment/jewellery outputs at a golden-set quality gate. | WR-026, WR-043, WR-075, WR-076, WR-077, WR-083, WR-181, WR-182 | QA-004, QA-017, QA-020, QA-032 | ST-04.2, ST-06.3 | BLOCKED |
| ST-06.5 | EP-06 | As a payer, successful delivery settles once while failed/cancelled/non-delivered work releases or recredits funds. | WR-040, WR-128, WR-160, WR-161, WR-191 | QA-006, QA-008, QA-024 | ST-06.2, ST-06.3 | TODO |
| ST-07.1 | EP-07 | As a mobile shopper, I can progress from discovery/photo/mannequin through consent, authentication, quote, and render. | WR-001–007, WR-013–015, WR-017, WR-021, WR-024, WR-027, WR-040, WR-043, WR-129, WR-140–142 | QA-001–005, QA-019, QA-026, QA-028, QA-030, QA-033, QA-035 | ST-02.1, ST-03.1–03.2, ST-04.1, ST-06.1–06.3 | TODO |
| ST-07.2 | EP-07 | As a shopper, I can compare/zoom a labelled preview, understand approximation, give feedback, report/delete, and explicitly buy another render. | WR-010, WR-025–030, WR-039, WR-120–122, WR-127, WR-158 | QA-005, QA-016, QA-027, QA-031 | ST-03.3, ST-06.3, ST-06.5 | TODO |
| ST-07.3 | EP-07 | As a consumer, I can top up and review my purchased/promo token balance in the mobile experience. | WR-157–167, WR-170–171 | QA-009–010, QA-022, QA-033, QA-036 | ST-05.1–05.5 | TODO |
| ST-08.1 | EP-08 | As an associate, I can start a fresh tenant-scoped Mirror-lite session and select only approved inventory. | WR-075, WR-079, WR-083, WR-086, WR-089, WR-150, WR-152–153 | QA-004, QA-012–014, QA-019–020 | ST-04.2–04.4, ST-06.4 | TODO |
| ST-08.2 | EP-08 | As an in-store customer, I can consent, preview an exact item with approximation warnings, and finish without exposing my session to the next shopper. | WR-076, WR-077, WR-086, WR-089, WR-093, WR-120–126 | QA-003, QA-005, QA-014, QA-020–021, QA-032 | ST-03.4, ST-06.3–06.5, ST-08.1 | BLOCKED |
| ST-08.3 | EP-08 | As an opted-in customer, I can share contact for the exact item and know the receiving merchant/follow-up channel. | WR-084, WR-092, WR-110, WR-113, WR-119 | QA-015, QA-019 | ST-08.2 | TODO |
| ST-08.4 | EP-08 | As a merchant owner, I see bounded aggregate usage, item-interest, and enquiry metrics without guest photos. | WR-096, WR-134, WR-176, WR-187 | QA-023 | ST-08.1–08.3 | TODO |
| ST-09.1 | EP-09 | As an authorized admin, I can activate/suspend tenants and offerings with a reason and immutable audit trail. | WR-177, WR-189 | QA-017 | ST-02.4, ST-02.5 | TODO |
| ST-09.2 | EP-09 | As an authorized admin, I can effective-date packs and select approved active model versions for future work. | WR-178, WR-181, WR-182, WR-189 | QA-017 | ST-05.2, ST-06.4 | BLOCKED |
| ST-09.3 | EP-09 | As an authorized admin, I can view reconcilable period/segment metrics without raw private imagery. | WR-176, WR-187 | QA-023 | ST-05.3, ST-06.5, ST-08.4 | TODO |
| ST-09.4 | EP-09 | As an operations user, I can review abuse, failures, payment discrepancies, support complaints, and data requests with traceable disposition. | WR-173, WR-188, WR-191, WR-192, WR-193 | QA-009, QA-016–018, QA-024 | ST-03.3–03.4, ST-05.3, ST-06.5 | TODO |
| ST-10.1 | EP-10 | As a release owner, I can run automated unit, contract, integration, security, concurrency, accessibility, and E2E gates. | All selected WRs | QA-001–036 | All implementation stories | TODO |
| ST-10.2 | EP-10 | As Product/AI/Privacy/Finance/Ops, we can approve pilot evidence without enabling unresolved categories or policies. | All selected WRs | QA-001–036 plus golden set | ST-10.1; DEC-01–10 as applicable | BLOCKED |

## Story readiness rule

A story can move from `TODO` to `IN_PROGRESS` only when every dependency is `DONE`, every referenced decision needed for its behavior is approved, and its API/data/test contracts are sufficiently defined. `BLOCKED` here means a known unresolved product/vendor/legal/quality decision prevents correct completion; it does not imply invented defaults.
