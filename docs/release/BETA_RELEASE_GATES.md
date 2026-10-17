# Simplified beta release gates

The local implementation and automated contracts are not permission to process real customer photos. Production enablement remains fail-closed until every item below has evidence.

## External activation

- Select one provider and store its credential in the production secret manager. OpenAI uses the
  Images edit endpoint with an approved `gpt-image-2.5-*` or `gpt-image-2` model; the retained
  Google alternative uses Vertex `virtual-try-on-001` in `asia-southeast1`.
- Verify the selected provider's applicable terms/DPA, image retention/training controls and
  organization verification requirements. Record Security/Privacy approval.
- Configure a private encrypted object-store backend and lifecycle rules; prove public listing/read is impossible and deletion completes within 24 hours.
- Configure an email delivery provider, verified sending domain and secret storage; pass delivery, throttle and abuse tests without logging codes.

## Quality evidence

- Supply at least 50 rights-cleared person/item pairs matching DEC-08 coverage.
- Run the golden evaluation against the exact selected provider/model. Require at least 90%
  acceptable results and no unresolved hard failure.
- Store the immutable evaluation report and Product/AI approval. Jewellery remains unavailable.

## Deployment evidence

- Local wiring is complete for PostgreSQL repositories, private filesystem storage, SMTP delivery,
  authenticated/CSRF-protected HTTP handlers, the same-origin web flow, durable work leasing,
  retry recovery, quota settlement/release and scheduled retention purge. Production still requires
  the managed object-store and provider configuration above.
- Run browser E2E, accessibility, cross-account isolation, queue replay, timeout, retention and restore tests in staging.
- Configure DEC-09 metrics/alerts and rehearse route shutdown, rollback and incident communication.
- Complete the final security/privacy release review before enabling real customer traffic.
