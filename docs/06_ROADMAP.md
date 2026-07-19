# Roadmap

This combines the local UC plan with code currently present on <code>develop</code>. It is a planning reference, not a commitment to deploy unimplemented integrations.

## Completed

| Range | Outcome |
| --- | --- |
| UC-00–UC-03 | Addon foundation, store setup, webhook receipt/audit, signature/rate-limit/integration-user gate. |
| UC-04–UC-08 | External-order staging, Salla order-created mapping, customer/product matching, validation. |
| UC-09–UC-11 | Store policies, Mock Lab, sale-order creation. |
| UC-12 | Database-backed duplicate protection and idempotent import. |
| UC-13 | Error queue, retry audit trail, manual retry via standard import path. |

## Next

### UC-14 — External Order Status Updates and Event Ordering

Implement Salla order-update handling for known staged orders while preserving safe behavior for unknown or out-of-order events.

Expected focus from the local plan:

- parse supported status/update fields;
- link updates to the correct staged order;
- handle cancellation, payment, fulfilment, products, and totals safely;
- record unknown/unsafe updates for review rather than destructively changing records;
- define ordering/idempotency rules and focused tests.

## Future

| UC | Theme | Current evidence |
| --- | --- | --- |
| UC-15 | OAuth authorization and secure token ingest | Store token fields and authorize mock payload exist; parser defers. |
| UC-16 | Token refresh locking/expiry warnings | Lock/timestamp fields exist; no refresh workflow. |
| UC-17 | Salla API client and optional enrichment | Abstract client boundary exists; live calls defer. |
| UC-18 | Stock readiness | Store policy exists; no stock behavior. |
| UC-19 | Reporting | Records support reporting; dedicated reporting absent. |
| UC-20 | Demo data/scripts | Mock payloads/wizard exist; full demo bootstrap absent. |
| UC-21 | Documentation/release polish | Durable docs now exist; release work remains. |

## Nice-to-have

- CI that installs modules and runs targeted tests.
- Controller signature/rate-limit/redaction and matching edge-case tests.
- Documented local database bootstrap and demo walkthrough.
- README and TEST_CASES refresh through the current UC.
- Repeatable upgrade/migration checklist for database constraints.

## Long-term improvements

- Additional platform addons using the base connector contract.
- Production topology: TLS/reverse proxy, monitoring, backups, and operational alerting.
- Queue/worker design if webhook volume makes synchronous processing unsuitable.
- Formal external-payload schema/version compatibility strategy using captured payload tests.
- Country-aware phone normalization, only after explicit business rules.
- Reporting/dashboard definitions tied to business adoption metrics.

## Guardrails

- Do not pursue outbound stock synchronization before the scoped stock-readiness work.
- Do not implement live API calls ahead of OAuth/token safety work.
- Do not treat order updates as harmless; preserve audit trail and avoid destructive out-of-order changes.
- Keep Mock Mode functional as external integration features are added.
